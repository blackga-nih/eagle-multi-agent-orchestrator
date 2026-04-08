"""Session Preloader — parallel DynamoDB reads for session-start context.

Fetches user preferences, active package status, document progress,
and feature flags concurrently.  Results are formatted as a terse
block injected into the supervisor system prompt so the agent is
context-aware from the very first message.

All fetches are wrapped in a 500ms timeout — on failure or timeout,
defaults are returned so the agent functions identically to before.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("eagle.session_preloader")


@dataclass
class PreloadedContext:
    """Container for session-start preloaded data."""

    preferences: dict = field(default_factory=dict)
    package: Optional[dict] = None  # package metadata
    checklist: Optional[dict] = None  # required / completed / missing
    documents: list[dict] = field(default_factory=list)
    feature_flags: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal fetch helpers (sync — run via asyncio.to_thread)
# ---------------------------------------------------------------------------


def _fetch_preferences(tenant_id: str, user_id: str) -> dict:
    from .pref_store import get_prefs

    return get_prefs(tenant_id, user_id)


def _fetch_package_and_docs(tenant_id: str, package_id: str) -> dict:
    from .package_store import get_package, get_package_checklist
    from .package_document_store import list_package_documents

    pkg = get_package(tenant_id, package_id)
    checklist = get_package_checklist(tenant_id, package_id)
    docs = list_package_documents(tenant_id, package_id)
    return {"package": pkg, "checklist": checklist, "documents": docs}


def _fetch_feature_flags() -> dict:
    from .config_store import get_feature_flags

    return get_feature_flags()


def _warm_template_cache(
    tenant_id: str,
    user_id: str,
    missing_doc_types: list[str],
) -> None:
    """Pre-resolve templates for missing documents to warm the 60s cache."""
    from .template_store import resolve_template

    for doc_type in missing_doc_types:
        try:
            resolve_template(tenant_id, user_id, doc_type)
        except Exception:
            pass  # best-effort cache warming


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def preload_session_context(
    tenant_id: str,
    user_id: str,
    package_id: Optional[str] = None,
    timeout_ms: int = 2000,
) -> PreloadedContext:
    """Fetch preferences, package state, and feature flags in parallel.

    Returns a populated PreloadedContext.  On timeout or error, returns
    a context with sensible defaults (empty prefs, no package, default flags).
    """
    ctx = PreloadedContext()

    async def _load_prefs() -> None:
        ctx.preferences = await asyncio.to_thread(
            _fetch_preferences,
            tenant_id,
            user_id,
        )

    async def _load_package() -> None:
        if not package_id:
            return
        result = await asyncio.to_thread(
            _fetch_package_and_docs,
            tenant_id,
            package_id,
        )
        ctx.package = result["package"]
        ctx.checklist = result["checklist"]
        ctx.documents = result["documents"]

    async def _warm_templates() -> None:
        """Warm template cache — separate from package fetch so it doesn't
        consume the timeout budget for the critical path."""
        if not package_id:
            return
        # Wait for package to load first so we have the checklist
        await _load_package_task
        missing = (ctx.checklist or {}).get("missing", [])
        if missing:
            await asyncio.to_thread(
                _warm_template_cache,
                tenant_id,
                user_id,
                missing,
            )

    async def _load_flags() -> None:
        ctx.feature_flags = await asyncio.to_thread(_fetch_feature_flags)

    try:
        _load_package_task = asyncio.ensure_future(_load_package())
        await asyncio.wait_for(
            asyncio.gather(_load_prefs(), _load_package_task, _load_flags()),
            timeout=timeout_ms / 1000,
        )
        # Template warming is best-effort, separate timeout
        asyncio.ensure_future(_warm_templates())
    except asyncio.TimeoutError:
        logger.warning(
            "session_preloader: timed out after %dms — returning partial context",
            timeout_ms,
        )
    except Exception:
        logger.exception("session_preloader: unexpected error during preload")

    return ctx


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def format_context_for_prompt(ctx: PreloadedContext) -> str:
    """Render PreloadedContext as a terse block for the system prompt.

    Returns an empty string when there is nothing meaningful to add.
    """
    parts: list[str] = []

    # Preferences
    prefs = ctx.preferences
    if prefs:
        pref_items: list[str] = []
        if prefs.get("default_doc_format"):
            pref_items.append(f"doc_format={prefs['default_doc_format']}")
        if prefs.get("preferred_vehicle"):
            pref_items.append(f"vehicle={prefs['preferred_vehicle']}")
        far = prefs.get("show_far_citations")
        if far is not None:
            pref_items.append(f"far_citations={'on' if far else 'off'}")
        if pref_items:
            parts.append(f"Preferences: {', '.join(pref_items)}")

    # Active package
    pkg = ctx.package
    if pkg and ctx.checklist:
        title = pkg.get("title", "Untitled")
        pathway = pkg.get("acquisition_pathway", "unknown")
        value = pkg.get("estimated_value", "N/A")
        pkg_id = pkg.get("package_id", "")
        status = pkg.get("status", "drafting")

        completed = ctx.checklist.get("completed", [])
        missing = ctx.checklist.get("missing", [])

        # Add version + s3_key info from preloaded documents
        doc_info: dict[str, dict] = {}
        for doc in ctx.documents:
            dt = doc.get("doc_type", "")
            doc_info[dt] = {
                "version": doc.get("version", 1),
                "s3_key": doc.get("s3_key", ""),
            }

        def _fmt_doc(d: str) -> str:
            info = doc_info.get(d, {})
            v = info.get("version", "?")
            key = info.get("s3_key", "")
            return f"{d} (v{v}, key={key})" if key else f"{d} (v{v})"

        completed_str = (
            ", ".join(_fmt_doc(d) for d in completed) if completed else "none"
        )
        missing_str = ", ".join(missing) if missing else "none"

        parts.append(
            f'Active Package: {pkg_id} "{title}" ({pathway}, ${value})\n'
            f"  Completed: {completed_str}\n"
            f"  Missing: {missing_str}\n"
            f"  Status: {status}"
        )

    if not parts:
        return ""

    return "--- USER CONTEXT ---\n" + "\n".join(parts)
