"""Shared helpers for parsing scoped session identifiers.

Composite session format:
``{tenant_id}#{tier}#{user_id}#{session}``
"""

from __future__ import annotations


def extract_tenant_id(session_id: str | None = None) -> str:
    """Extract tenant_id from scoped session context."""
    if not session_id:
        return "demo-tenant"
    if "#" in session_id:
        return session_id.split("#", 3)[0]
    return "demo-tenant"


def extract_user_id(session_id: str | None = None) -> str:
    """Extract user_id from scoped session context."""
    if not session_id:
        return "demo-user"
    if "#" in session_id:
        parts = session_id.split("#", 3)
        if len(parts) >= 3:
            return parts[2]
    if session_id.startswith("ws-"):
        return session_id
    return "demo-user"


def extract_leaf_session_id(session_id: str | None = None) -> str | None:
    """Extract raw leaf session id from scoped session context."""
    if not session_id:
        return None
    if "#" in session_id:
        parts = session_id.split("#", 3)
        if len(parts) >= 4 and parts[3]:
            return parts[3]
        return None
    return session_id
