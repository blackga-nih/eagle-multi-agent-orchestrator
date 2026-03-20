"""
EAGLE Strands Package State Helpers

Functions for emitting package state_update events to the frontend.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("eagle.strands_agent")


def emit_package_state(
    tool_result: dict,
    tool_name: str,
    tenant_id: str,
    result_queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Emit package state_update events after tools that affect the checklist.

    Pushes ``state_update`` chunks into result_queue so the streaming_routes
    layer can forward them as SSE metadata events for ``usePackageState``.
    """
    try:
        package_id = tool_result.get("package_id")
        if not package_id:
            return

        from app.package_store import get_package_checklist

        checklist = get_package_checklist(tenant_id, package_id)

        total = len(checklist.get("required", []))
        completed = len(checklist.get("completed", []))
        progress_pct = int((completed / total) * 100) if total > 0 else 0

        if tool_name == "create_document":
            # Emit document_ready + checklist_update
            doc_type = tool_result.get("doc_type") or tool_result.get("document_type")
            loop.call_soon_threadsafe(
                result_queue.put_nowait,
                {
                    "type": "state_update",
                    "state_type": "document_ready",
                    "package_id": package_id,
                    "doc_type": doc_type,
                    "checklist": checklist,
                    "progress_pct": progress_pct,
                },
            )

        # Always emit a checklist_update
        loop.call_soon_threadsafe(
            result_queue.put_nowait,
            {
                "type": "state_update",
                "state_type": "checklist_update",
                "package_id": package_id,
                "checklist": checklist,
                "progress_pct": progress_pct,
            },
        )

        # For finalize_package, emit compliance warnings if any
        if tool_name == "finalize_package":
            warnings = tool_result.get("compliance_warnings", [])
            if warnings:
                loop.call_soon_threadsafe(
                    result_queue.put_nowait,
                    {
                        "type": "state_update",
                        "state_type": "compliance_alert",
                        "package_id": package_id,
                        "severity": "warning",
                        "items": [{"name": w, "note": ""} for w in warnings[:5]],
                    },
                )
    except Exception:
        logger.debug("emit_package_state failed (non-critical)", exc_info=True)


def build_end_of_turn_state(package_context: Any, tenant_id: str) -> list[dict]:
    """Build a checklist_update state event from the current package context.

    Called at the end of every turn so the frontend always has the latest
    package state — even when no document tool was called but user input
    changed acquisition method, flags, or other metadata.

    Returns a list of dicts (0 or 1) that can be yielded as SSE chunks.
    """
    try:
        if package_context is None:
            return []
        pkg_id = getattr(package_context, "package_id", None)
        if not pkg_id:
            return []

        from app.package_store import get_package, get_package_checklist

        # Re-fetch the package to pick up any mid-turn metadata changes
        pkg = get_package(tenant_id, pkg_id)
        if not pkg:
            return []

        checklist = get_package_checklist(tenant_id, pkg_id)
        total = len(checklist.get("required", []))
        completed = len(checklist.get("completed", []))
        progress_pct = int((completed / total) * 100) if total > 0 else 0

        return [
            {
                "type": "state_update",
                "state_type": "checklist_update",
                "package_id": pkg_id,
                "checklist": checklist,
                "progress_pct": progress_pct,
                "phase": pkg.get("status", "drafting"),
                "title": pkg.get("title", ""),
                "acquisition_method": pkg.get("acquisition_method"),
                "contract_type": pkg.get("contract_type"),
            }
        ]
    except Exception:
        logger.debug("build_end_of_turn_state failed (non-critical)", exc_info=True)
        return []


def build_state_updates(tool_result: dict, tool_name: str, tenant_id: str) -> list[dict]:
    """Build state_update dicts for yield paths (fast-path / forced-doc).

    Returns a list of dicts that can be yielded directly as SSE chunks.
    Non-critical — returns empty list on error.
    """
    try:
        package_id = tool_result.get("package_id")
        if not package_id:
            return []

        from app.package_store import get_package_checklist

        checklist = get_package_checklist(tenant_id, package_id)
        total = len(checklist.get("required", []))
        completed = len(checklist.get("completed", []))
        progress_pct = int((completed / total) * 100) if total > 0 else 0

        events: list[dict] = []

        if tool_name == "create_document":
            doc_type = tool_result.get("doc_type") or tool_result.get("document_type")
            events.append(
                {
                    "type": "state_update",
                    "state_type": "document_ready",
                    "package_id": package_id,
                    "doc_type": doc_type,
                    "checklist": checklist,
                    "progress_pct": progress_pct,
                }
            )

        events.append(
            {
                "type": "state_update",
                "state_type": "checklist_update",
                "package_id": package_id,
                "checklist": checklist,
                "progress_pct": progress_pct,
            }
        )

        return events
    except Exception:
        logger.debug("build_state_updates failed (non-critical)", exc_info=True)
        return []
