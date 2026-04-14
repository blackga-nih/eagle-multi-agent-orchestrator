"""Shared AWS session factory for backend tools.

Centralizes credential acquisition so every boto3 caller goes through the
same resolution path:

    1. If ``AWS_PROFILE`` is set AND that profile exists in the local AWS
       config, use ``boto3.Session(profile_name=...)``.  This is the
       normal path for local development (``AWS_PROFILE=eagle`` in
       ``server/.env`` resolves the SSO profile).

    2. Otherwise fall through to ``boto3.Session()`` which picks up
       credentials from the default chain — container task role on
       ECS Fargate, OIDC-assumed role in GitHub Actions, IMDS on EC2,
       or raw ``AWS_ACCESS_KEY_ID``/``AWS_SECRET_ACCESS_KEY`` env vars.

Why centralize?  The default chain is implicit and silently falls back
to a broken ``[default]`` profile if the env var is unset.  By reading
``AWS_PROFILE`` explicitly we can:

    - Validate the profile exists before using it (and log a clear
      warning if it does not).
    - Log which credential path was taken at startup, which is invaluable
      when diagnosing ``400 empty body`` errors from Bedrock (those
      typically mean stale SSO tokens or a misconfigured default).
    - Have one place to add credential refresh hooks later (e.g. re-read
      SSO cache on expiry).

Production safety: on ECS this helper will see no ``AWS_PROFILE`` env
var and return a default session that transparently uses the task role.
The behavior is identical to the old ``boto3.client(...)`` calls in
that case.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import boto3

logger = logging.getLogger("eagle.aws_session")

_session_lock = threading.Lock()
_shared_session: Optional[boto3.Session] = None
_resolved_path: str = "unresolved"


def _profile_exists(profile: str) -> bool:
    """Return True if ``profile`` is defined in ``~/.aws/config`` or
    ``~/.aws/credentials``.

    Uses botocore's own config loader so the check matches what boto3
    would actually see at Session() construction time.  Returns False
    on any IO / parse error — the caller will then fall through to the
    default chain, which is the safe behavior.
    """
    try:
        # botocore exposes available_profiles on a Session
        probe = boto3.Session()
        return profile in (probe.available_profiles or [])
    except Exception:  # pragma: no cover - defensive
        return False


def get_shared_session() -> boto3.Session:
    """Return the shared, lazily-initialized ``boto3.Session``.

    Thread-safe and idempotent.  Subsequent calls return the same
    session so boto3 client caches are reused across tools.
    """
    global _shared_session, _resolved_path
    if _shared_session is not None:
        return _shared_session

    with _session_lock:
        if _shared_session is not None:
            return _shared_session

        profile = os.environ.get("AWS_PROFILE", "").strip()
        if profile:
            if _profile_exists(profile):
                _shared_session = boto3.Session(profile_name=profile)
                _resolved_path = f"profile={profile}"
                logger.info(
                    "aws_session: using AWS_PROFILE=%s (SSO / config file)",
                    profile,
                )
            else:
                # Profile env var set but config file doesn't define it —
                # this happens in container deployments where AWS_PROFILE
                # leaked from a parent env.  Silently fall through to the
                # default chain (task role) rather than crashing.
                _shared_session = boto3.Session()
                _resolved_path = f"default (AWS_PROFILE={profile} not found in config)"
                logger.info(
                    "aws_session: AWS_PROFILE=%s not found in config; "
                    "falling back to default credential chain",
                    profile,
                )
        else:
            _shared_session = boto3.Session()
            _resolved_path = "default (no AWS_PROFILE)"
            logger.info(
                "aws_session: using default credential chain "
                "(ECS task role / env vars / default profile)"
            )

        return _shared_session


def resolved_credential_path() -> str:
    """Return a short human-readable description of which credential
    path was taken when the shared session was built.  Useful for
    diagnostics / health endpoints."""
    if _shared_session is None:
        get_shared_session()
    return _resolved_path


def reset_shared_session() -> None:
    """Force the next ``get_shared_session()`` call to rebuild.

    Intended for tests and for a future credential-refresh hook — not
    called anywhere in normal production flow.
    """
    global _shared_session, _resolved_path
    with _session_lock:
        _shared_session = None
        _resolved_path = "unresolved"
