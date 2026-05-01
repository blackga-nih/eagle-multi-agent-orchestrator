"""
Package Context Service -- Resolves active package for chat sessions.

Determines whether a chat session is operating in "package mode" (documents
route to a specific acquisition package) or "workspace mode" (standalone docs).

Context resolution order:
1. Explicit package_id in request body (highest priority)
2. active_package_id in session metadata
3. No package context (workspace mode)
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from .session_store import get_messages, get_session, update_session
from .package_store import get_package, list_packages
from .package_document_store import list_package_documents

logger = logging.getLogger("eagle.package_context")

# Canonical package IDs are PKG-{YYYY}-{NNNN} (see package_store._next_package_id).
_PACKAGE_ID_PATTERN = re.compile(r"\bPKG-\d{4}-\d{4}\b")
# Titles shorter than this are too generic to match safely (e.g. "SOW", "v1").
_MIN_TITLE_MATCH_LEN = 6


@dataclass
class PackageContext:
    """Resolved package context for a chat session."""

    mode: str  # "package" or "workspace"
    package_id: Optional[str] = None
    package_title: Optional[str] = None
    acquisition_pathway: Optional[str] = None
    required_documents: Optional[list] = None
    completed_documents: Optional[list] = None

    @property
    def is_package_mode(self) -> bool:
        return self.mode == "package" and self.package_id is not None


def resolve_context(
    tenant_id: str,
    user_id: str,
    session_id: str,
    explicit_package_id: Optional[str] = None,
) -> PackageContext:
    """Resolve the package context for a chat session.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier
        explicit_package_id: Package ID explicitly provided in request (overrides session)

    Returns:
        PackageContext with resolved mode and package details
    """
    # Priority 1: Explicit package_id in request
    if explicit_package_id:
        pkg = get_package(tenant_id, explicit_package_id)
        if pkg:
            logger.debug(
                "Package context resolved from explicit ID: %s", explicit_package_id
            )
            return _build_package_context(pkg)
        else:
            logger.warning(
                "Explicit package_id %s not found for tenant %s",
                explicit_package_id,
                tenant_id,
            )
            # Fall through to session metadata

    # Priority 2: Session metadata
    session = get_session(session_id, tenant_id, user_id)
    if session:
        metadata = session.get("metadata", {})
        session_package_id = metadata.get("active_package_id")

        if session_package_id:
            pkg = get_package(tenant_id, session_package_id)
            if pkg:
                logger.debug(
                    "Package context resolved from session metadata: %s",
                    session_package_id,
                )
                return _build_package_context(pkg)
            else:
                logger.warning(
                    "Session active_package_id %s not found, clearing from session",
                    session_package_id,
                )
                # Clear stale package reference
                clear_active_package(tenant_id, user_id, session_id)

    # Priority 3: No package context (workspace mode)
    logger.debug("No package context found, using workspace mode")
    return PackageContext(mode="workspace")


def set_active_package(
    tenant_id: str,
    user_id: str,
    session_id: str,
    package_id: str,
) -> Optional[PackageContext]:
    """Set the active package for a session.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier
        package_id: Package ID to set as active

    Returns:
        PackageContext if package exists and was set, None otherwise
    """
    # Verify package exists
    pkg = get_package(tenant_id, package_id)
    if not pkg:
        logger.warning(
            "Cannot set active package: %s not found for tenant %s",
            package_id,
            tenant_id,
        )
        return None

    # Get current session metadata
    session = get_session(session_id, tenant_id, user_id)
    if not session:
        logger.warning("Cannot set active package: session %s not found", session_id)
        return None

    # Update session metadata
    metadata = session.get("metadata", {})
    metadata["active_package_id"] = package_id

    update_session(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        updates={"metadata": metadata},
    )

    logger.info("Set active package %s for session %s", package_id, session_id)
    return _build_package_context(pkg)


def clear_active_package(
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> bool:
    """Clear the active package from a session (switch to workspace mode).

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier

    Returns:
        True if cleared successfully, False otherwise
    """
    session = get_session(session_id, tenant_id, user_id)
    if not session:
        logger.warning("Cannot clear active package: session %s not found", session_id)
        return False

    metadata = session.get("metadata", {})
    if "active_package_id" in metadata:
        del metadata["active_package_id"]
        update_session(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            updates={"metadata": metadata},
        )
        logger.info("Cleared active package for session %s", session_id)

    return True


def get_active_package_id(
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> Optional[str]:
    """Get the active package ID for a session without full resolution.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Chat session identifier

    Returns:
        Package ID if set, None otherwise
    """
    session = get_session(session_id, tenant_id, user_id)
    if not session:
        return None

    metadata = session.get("metadata", {})
    return metadata.get("active_package_id")


def detect_package_from_session(
    tenant_id: str,
    user_id: str,
    session_id: str,
) -> Optional[PackageContext]:
    """Detect the active package for a chat session by scanning history.

    Detection ladder (most-recent reference wins at each tier):

    A. Structured tool blocks — tool_use/tool_result content blocks whose
       JSON input/output carries a literal ``package_id`` field. Highest
       confidence; covers the canonical Anthropic tool-call shape.

    B. Package-ID regex — ``PKG-YYYY-NNNN`` strings appearing anywhere in
       the flattened chat text. Catches plain-text mentions ("see package
       PKG-2026-0007") that never went through a structured tool call.

    C. Title regex — package titles and previously-generated document
       titles (across the tenant's recent packages) appearing in chat
       text. Catches assistant turns that reference a doc by its title
       only ("I just generated the *FY26 GenAI Bench SOW*").

    Returns the resolved ``PackageContext`` (and persists it as the
    session's active package) or ``None`` if nothing matched.
    """
    messages = get_messages(session_id, tenant_id, user_id, limit=200)
    if not messages:
        logger.debug(
            "detect_package_from_session: no messages in session %s", session_id
        )
        return None

    # Tier A: structured tool blocks (existing high-confidence path).
    pkg_id = _scan_tool_blocks_for_package_id(tenant_id, messages)
    if pkg_id:
        return _set_and_return(tenant_id, user_id, session_id, pkg_id)

    # Tiers B + C run over flattened chat text, newest message first so the
    # *latest* reference wins.
    pkg_id = _scan_text_for_package(tenant_id, messages)
    if pkg_id:
        return _set_and_return(tenant_id, user_id, session_id, pkg_id)

    logger.debug(
        "detect_package_from_session: no package_id found in session %s", session_id
    )
    return None


def _scan_tool_blocks_for_package_id(
    tenant_id: str, messages: list
) -> Optional[str]:
    """Tier A: walk messages newest-first looking for tool_use/tool_result
    blocks that carry a literal ``package_id`` field."""
    import json as _json

    for msg in reversed(messages):
        content = msg.get("content")
        if not content:
            continue

        blocks = content
        if isinstance(content, str):
            try:
                parsed = _json.loads(content)
                if isinstance(parsed, list):
                    blocks = parsed
                else:
                    continue
            except (ValueError, TypeError):
                continue

        if not isinstance(blocks, list):
            continue

        for block in blocks:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "tool_result":
                pkg_id = _extract_package_id(block)
                if pkg_id:
                    return pkg_id

            if block.get("type") == "tool_use":
                inp = block.get("input", {})
                if isinstance(inp, dict) and inp.get("package_id"):
                    pkg_id = inp["package_id"]
                    if get_package(tenant_id, pkg_id):
                        return pkg_id

    return None


def _scan_text_for_package(tenant_id: str, messages: list) -> Optional[str]:
    """Tiers B + C: regex package-id and title matches over flattened chat
    text. Walks messages newest-first; first hit wins."""
    # Build the title → package_id index once (one DDB scan for the tenant's
    # packages plus one DOCUMENT# query per package). Bounded by the active
    # tenant's package count, which is small in practice.
    title_index = _build_title_index(tenant_id)

    for msg in reversed(messages):
        text = _flatten_message_text(msg)
        if not text:
            continue

        # Tier B: explicit package-id mention.
        match = _PACKAGE_ID_PATTERN.search(text)
        if match:
            candidate = match.group(0)
            if get_package(tenant_id, candidate):
                return candidate

        # Tier C: package title or document title mention.
        haystack = text.lower()
        for needle, pkg_id in title_index:
            if needle in haystack:
                return pkg_id

    return None


def _build_title_index(tenant_id: str) -> list[tuple[str, str]]:
    """Return [(lowercase_title, package_id)] for the tenant's packages and
    their generated documents. Sorted by descending title length so the
    most specific match wins (substring-style search)."""
    try:
        packages = list_packages(tenant_id)
    except Exception:  # pragma: no cover — defensive against store outages
        logger.exception("detect_package: list_packages failed for %s", tenant_id)
        return []

    pairs: list[tuple[str, str]] = []
    for pkg in packages:
        pkg_id = pkg.get("package_id")
        if not pkg_id:
            continue

        pkg_title = pkg.get("title") or ""
        if len(pkg_title) >= _MIN_TITLE_MATCH_LEN:
            pairs.append((pkg_title.lower(), pkg_id))

        try:
            docs = list_package_documents(tenant_id, pkg_id)
        except Exception:
            logger.debug(
                "detect_package: list_package_documents failed for %s",
                pkg_id,
                exc_info=True,
            )
            docs = []

        for doc in docs:
            doc_title = doc.get("title") or ""
            if len(doc_title) >= _MIN_TITLE_MATCH_LEN:
                pairs.append((doc_title.lower(), pkg_id))

    # Most specific (longest) needles first — avoids "Package" matching before
    # "FY26 GenAI Bench SOW v3".
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def _flatten_message_text(msg: dict) -> str:
    """Best-effort extract of human-readable text from a stored message,
    whether the content is a plain string or an Anthropic content-block list
    (possibly stored as a JSON string)."""
    import json as _json

    content = msg.get("content")
    if not content:
        return ""

    if isinstance(content, str):
        # The store may serialise list content as a JSON string. Parse if we
        # can; otherwise treat it as the user's plain-text message.
        stripped = content.lstrip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                content = _json.loads(content)
            except (ValueError, TypeError):
                return content
        else:
            return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                parts.append(str(block.get("text", "")))
            elif block_type == "tool_result":
                inner = block.get("content")
                if isinstance(inner, str):
                    parts.append(inner)
                elif isinstance(inner, list):
                    for part in inner:
                        if isinstance(part, dict) and part.get("type") == "text":
                            parts.append(str(part.get("text", "")))
        return "\n".join(p for p in parts if p)

    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text

    return ""


def _extract_package_id(block: dict) -> Optional[str]:
    """Extract package_id from a tool_result content block."""
    import json as _json

    # tool_result content can be a string (JSON) or nested blocks
    content = block.get("content")
    if isinstance(content, str):
        try:
            data = _json.loads(content)
            if isinstance(data, dict) and data.get("package_id"):
                return data["package_id"]
        except (ValueError, TypeError):
            pass
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                try:
                    data = _json.loads(part.get("text", ""))
                    if isinstance(data, dict) and data.get("package_id"):
                        return data["package_id"]
                except (ValueError, TypeError):
                    pass
    elif isinstance(content, dict) and content.get("package_id"):
        return content["package_id"]
    return None


def _set_and_return(
    tenant_id: str, user_id: str, session_id: str, package_id: str
) -> Optional[PackageContext]:
    """Set the detected package as active and return its context."""
    ctx = set_active_package(tenant_id, user_id, session_id, package_id)
    if ctx:
        logger.info(
            "detect_package_from_session: detected and set package %s for session %s",
            package_id,
            session_id,
        )
    return ctx


def _build_package_context(pkg: dict) -> PackageContext:
    """Build a PackageContext from a package record."""
    return PackageContext(
        mode="package",
        package_id=pkg.get("package_id"),
        package_title=pkg.get("title"),
        acquisition_pathway=pkg.get("acquisition_pathway"),
        required_documents=pkg.get("required_documents", []),
        completed_documents=pkg.get("completed_documents", []),
    )
