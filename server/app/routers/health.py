"""
Health Check API Router

Provides backend health check endpoint for monitoring and load balancers.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter

from ..health_checks import check_knowledge_base_health

router = APIRouter(prefix="/api", tags=["health"])


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
        "git_sha": os.getenv("GIT_SHA", "unknown"),
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
