"""
Health Check API Router

Provides backend health check endpoint for monitoring and load balancers.
"""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from ..health_checks import check_knowledge_base_health

router = APIRouter(prefix="/api", tags=["health"])


def _resolve_git_sha() -> str:
    env_sha = os.getenv("GIT_SHA")
    if env_sha:
        return env_sha
    try:
        repo_root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            if sha:
                return sha
    except Exception:
        pass
    return "unknown"


_GIT_SHA = _resolve_git_sha()
_BACKEND_STARTED_AT = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
_BACKEND_PID = os.getpid()


@router.get("/ping")
async def ping():
    """Lightweight liveness probe — no I/O, no dependencies."""
    return {
        "status": "healthy",
        "git_sha": _GIT_SHA,
        "started_at": _BACKEND_STARTED_AT,
        "pid": _BACKEND_PID,
    }


@router.get("/health")
async def health_check():
    """Backend health check endpoint."""
    knowledge_base = check_knowledge_base_health()

    # Circuit breaker status (lazy import to avoid circular deps at module load)
    cb_status = {}
    try:
        from ..strands_agentic_service import _circuit_breaker

        cb_status = _circuit_breaker.get_status()
    except Exception:
        pass

    return {
        "status": "healthy",
        "service": "eagle-backend",
        "version": "4.0.0",
        "git_sha": _GIT_SHA,
        "started_at": _BACKEND_STARTED_AT,
        "pid": _BACKEND_PID,
        "services": {
            "bedrock": True,
            "dynamodb": True,
            "cognito": True,
            "s3": True,
            "knowledge_metadata_table": knowledge_base["metadata_table"]["ok"],
            "knowledge_document_bucket": knowledge_base["document_bucket"]["ok"],
        },
        "knowledge_base": knowledge_base,
        "circuit_breaker": cb_status,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
