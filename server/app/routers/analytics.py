"""
Analytics API Router

Provides endpoint for frontend analytics event ingestion.
"""

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analytics"])


@router.post("/analytics/events")
async def api_analytics_events(request: Request):
    """Ingest batched analytics events — writes to CloudWatch."""
    try:
        body = await request.json()
        events = body.get("events", [])
        if not events:
            return {"status": "ok", "ingested": 0}

        from ..telemetry.cloudwatch_emitter import emit_telemetry_event
        for event in events[:100]:  # Cap at 100 per batch
            emit_telemetry_event(
                event_type=f"analytics.{event.get('event', 'unknown')}",
                tenant_id="frontend",
                data={
                    "page": event.get("page", ""),
                    "metadata": event.get("metadata", {}),
                    "client_timestamp": event.get("timestamp", 0),
                },
            )
        return {"status": "ok", "ingested": len(events)}
    except Exception as e:
        logger.warning("Analytics ingestion error: %s", e)
        return {"status": "ok", "ingested": 0}
