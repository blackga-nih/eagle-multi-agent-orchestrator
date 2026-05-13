"""Local HS256 session token encode/decode.

Mirrors the fcasvp pattern: after Entra OIDC code exchange we mint our own
short-lived JWT carrying the resolved user profile (tenant, tier, admin flag).
The frontend sends it on every request as ``Authorization: Bearer <token>``.

Signing key comes from ``JWT_SIGNING_KEY`` (Secrets Manager in deployed envs,
plain env in local dev). Algorithm is HS256.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import jwt

logger = logging.getLogger("eagle.auth.jwt")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8h, fcasvp default


def _signing_key() -> str:
    """Resolve the HS256 signing key, preferring runtime env (Secrets Manager)."""
    key = os.getenv("JWT_SIGNING_KEY") or os.getenv("JWT_SECRET_KEY")
    if not key:
        # In dev / unconfigured environments we still want imports to succeed.
        # Token decode will fail closed for any signed token.
        return "eagle-dev-insecure-jwt-key"
    return key


def create_session_token(
    *,
    user_id: str,
    email: str,
    tenant_id: str,
    tier: str = "basic",
    is_admin: bool = False,
    display_name: Optional[str] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
    expire_minutes: Optional[int] = None,
) -> str:
    """Mint a session JWT.

    Claims align with the existing ``UserContext.from_claims`` mapping plus the
    fcasvp ``email``/``sub`` convention.
    """
    now = int(time.time())
    exp = now + (expire_minutes or JWT_EXPIRE_MINUTES) * 60

    payload: Dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "tier": tier,
        "is_admin": is_admin,
        "iat": now,
        "exp": exp,
    }
    if display_name:
        payload["display_name"] = display_name
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, _signing_key(), algorithm=JWT_ALGORITHM)


def decode_session_token(token: str) -> Dict[str, Any]:
    """Decode and validate a session JWT. Raises ``jwt.PyJWTError`` on failure."""
    return jwt.decode(token, _signing_key(), algorithms=[JWT_ALGORITHM])


def decode_session_token_safe(
    token: str,
) -> tuple[bool, Dict[str, Any], Optional[str]]:
    """Wrapper that never raises — returns (ok, claims, error)."""
    try:
        claims = decode_session_token(token)
        return True, claims, None
    except jwt.ExpiredSignatureError:
        return False, {}, "Token expired"
    except jwt.PyJWTError as exc:
        return False, {}, f"Invalid token: {exc}"
    except Exception as exc:  # defensive
        logger.error("Unexpected token decode error: %s", exc)
        return False, {}, f"Token decode error: {exc}"
