"""``/api/auth/*`` endpoints — Microsoft Entra OIDC code flow.

Ported from ``backend/fcasvp/routers/auth.py`` (nci-oasys-fcas) with EAGLE-
specific changes:

  * User profile lookup hits DynamoDB ``USER#<email>`` instead of an Oracle
    ``PortalIdentity`` join.
  * No multi-DUNS disambiguation in v1 (single profile row per user).
  * Response shape includes EAGLE's ``tenant_id`` / ``tier`` / ``is_admin``
    so the frontend can drive subscription gating.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from .dependencies import DEV_MODE, UserContext, extract_user_context
from .jwt_utils import create_session_token
from .user_directory import get_user_profile

logger = logging.getLogger("eagle.auth.router")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Settings (read at request time so secrets injected late still work) ──────


def _entra_settings() -> Dict[str, str]:
    tenant_id = os.getenv("ENTRA_TENANT_ID", "")
    return {
        "tenant_id": tenant_id,
        "client_id": os.getenv("ENTRA_CLIENT_ID", ""),
        "client_secret": os.getenv("ENTRA_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv(
            "ENTRA_REDIRECT_URI", "http://localhost:8000/api/auth/callback"
        ),
        "post_login_path": os.getenv("ENTRA_POST_LOGIN_PATH", "/chat"),
        # Where the browser ends up after callback. Defaults to localhost:3000
        # for dev; in deployed envs set FRONTEND_BASE_URL to the frontend ALB.
        "frontend_base_url": os.getenv("FRONTEND_BASE_URL", "http://localhost:3000"),
        "authority": f"https://login.microsoftonline.com/{tenant_id}",
    }


# ── /login ──────────────────────────────────────────────────────────────────


@router.get("/login")
async def login() -> RedirectResponse:
    """302 redirect to the Entra authorize endpoint."""
    if DEV_MODE:
        return RedirectResponse("/api/auth/dev-login")

    s = _entra_settings()
    if not s["client_id"] or not s["tenant_id"]:
        raise HTTPException(
            status_code=503, detail="Entra OIDC is not configured on this server"
        )
    params = {
        "client_id": s["client_id"],
        "response_type": "code",
        "redirect_uri": s["redirect_uri"],
        "scope": "openid email profile",
        "response_mode": "query",
    }
    url = f"{s['authority']}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


# ── /callback ───────────────────────────────────────────────────────────────


@router.get("/callback")
async def callback(code: str, request: Request) -> RedirectResponse:
    """Exchange the OIDC code for tokens, mint a local session JWT, redirect."""
    s = _entra_settings()
    if not s["client_id"] or not s["client_secret"]:
        raise HTTPException(
            status_code=503, detail="Entra OIDC is not configured on this server"
        )

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(
            f"{s['authority']}/oauth2/v2.0/token",
            data={
                "client_id": s["client_id"],
                "client_secret": s["client_secret"],
                "code": code,
                "redirect_uri": s["redirect_uri"],
                "grant_type": "authorization_code",
                "scope": "openid email profile",
            },
        )

    if token_resp.status_code != 200:
        logger.warning("Entra token exchange failed: %s", token_resp.text)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token exchange failed",
        )

    id_token = token_resp.json().get("id_token")
    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No id_token in Entra response",
        )

    # The id_token came back from Entra's token endpoint over a back-channel
    # HTTPS POST authenticated with our client_secret, so we trust it without
    # verifying the JWS signature here (matches fcasvp behavior).
    claims = jwt.get_unverified_claims(id_token) if hasattr(jwt, "get_unverified_claims") else jwt.decode(  # type: ignore[attr-defined]
        id_token, options={"verify_signature": False}
    )
    email = claims.get("email") or claims.get("preferred_username")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No email claim in id_token",
        )

    profile = get_user_profile(email)
    if profile is None or not profile.authorized:
        # Issue a "not authorized" token-less redirect to the frontend page.
        return RedirectResponse(
            f"{s['frontend_base_url']}/not-authorized?email={urllib.parse.quote(email)}"
        )

    session_token = create_session_token(
        user_id=str(claims.get("oid") or claims.get("sub") or email),
        email=email,
        tenant_id=profile.tenant_id,
        tier=profile.tier,
        is_admin=profile.is_admin,
        display_name=profile.display_name or claims.get("name"),
    )

    return RedirectResponse(
        f"{s['frontend_base_url']}{s['post_login_path']}?token={session_token}"
    )


# ── /authenticate ───────────────────────────────────────────────────────────


@router.get("/authenticate")
async def authenticate(request: Request) -> Dict[str, Any]:
    """Resolve the current session token to user info + permissions.

    Mirrors fcasvp's ``/api/auth/authenticate``. The frontend calls this on
    page load to decide whether to render the app or redirect to login.
    """
    auth_header = request.headers.get("Authorization", "")
    user, error = extract_user_context(auth_header or None)

    if user.user_id == "anonymous":
        return {"result": "Needs Login", "allow_login": True, "error": error}

    return {
        "result": "Success",
        "user_id": user.user_id,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "tier": user.tier,
        "is_admin": user.is_admin(),
        "display_name": user.display_name,
        "allow_login": False,
    }


# ── /logout ─────────────────────────────────────────────────────────────────


@router.get("/logout")
async def logout() -> RedirectResponse:
    """Redirect to Entra's OIDC logout endpoint to end the SSO session.

    Entra requires ``post_logout_redirect_uri`` to be a URL registered on the
    app registration. We send the user back to the frontend root after Entra
    finishes logging them out (not the FastAPI root, which has no UI).
    """
    s = _entra_settings()
    if not s["tenant_id"]:
        return RedirectResponse(s["frontend_base_url"])
    params = {"post_logout_redirect_uri": s["frontend_base_url"]}
    return RedirectResponse(
        f"{s['authority']}/oauth2/v2.0/logout?{urllib.parse.urlencode(params)}"
    )


# ── /dev-login ──────────────────────────────────────────────────────────────


@router.get("/dev-login")
async def dev_login() -> RedirectResponse:
    """Mint a dev session JWT without going through Entra. ``DEV_MODE`` only."""
    if not DEV_MODE:
        raise HTTPException(status_code=404, detail="Not found")

    user = UserContext.dev_user()
    token = create_session_token(
        user_id=user.user_id,
        email=user.email or f"{user.user_id}@example.com",
        tenant_id=user.tenant_id,
        tier=user.tier,
        is_admin=True,
        display_name=user.display_name,
    )
    s = _entra_settings()
    return RedirectResponse(
        f"{s['frontend_base_url']}{s['post_login_path']}?token={token}"
    )


# ── /me — convenience for diagnostics ───────────────────────────────────────


@router.get("/me")
async def me(request: Request) -> JSONResponse:
    auth_header = request.headers.get("Authorization", "")
    user, _ = extract_user_context(auth_header or None)
    return JSONResponse(user.to_dict())


# ── Optional: refresh token endpoint placeholder ────────────────────────────
# Frontend doesn't refresh tokens silently in v1; users re-login when the
# session JWT expires (default 8h, matches fcasvp). Re-authentication is one
# redirect. Documenting here so it's not mistaken for a missing feature.
