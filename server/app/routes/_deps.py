"""Shared dependencies for route modules."""

import os
import uuid
import logging
from typing import Optional
from collections import deque
from datetime import datetime

from fastapi import Header, HTTPException

from ..cognito_auth import UserContext, extract_user_context
from ..auth import get_current_user  # noqa: F401 — re-exported for routes
from ..admin_auth import get_admin_user, verify_tenant_admin  # noqa: F401

logger = logging.getLogger("eagle")

# ── Feature Flags ────────────────────────────────────────────────────
USE_PERSISTENT_SESSIONS = os.getenv("USE_PERSISTENT_SESSIONS", "true").lower() == "true"
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "false").lower() == "true"

# ── S3 bucket (single source of truth) ───────────────────────────────
S3_BUCKET = os.getenv("S3_BUCKET", "eagle-documents-dev")

# ── Telemetry ring buffer ────────────────────────────────────────────
TELEMETRY_LOG: deque = deque(maxlen=500)


def log_telemetry(entry: dict):
    import json
    entry.setdefault("timestamp", datetime.utcnow().isoformat())
    TELEMETRY_LOG.append(entry)
    logger.info(json.dumps(entry, default=str))


# ── Auth Helpers ─────────────────────────────────────────────────────

async def get_user_from_header(authorization: Optional[str] = Header(None)) -> UserContext:
    """Extract user from Authorization header (EAGLE Cognito auth)."""
    user, error = extract_user_context(authorization)
    if REQUIRE_AUTH and user.user_id == "anonymous":
        raise HTTPException(status_code=401, detail=error or "Authentication required")
    return user


def get_session_context(user: UserContext, session_id: Optional[str] = None) -> tuple:
    """Get tenant_id, user_id, and session_id from user context."""
    tenant_id = user.tenant_id
    user_id = user.user_id
    sid = session_id or str(uuid.uuid4())
    return tenant_id, user_id, sid
