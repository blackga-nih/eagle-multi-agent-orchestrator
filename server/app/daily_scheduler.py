"""
Daily scheduler for EAGLE Teams notifications.

Runs an asyncio background loop that triggers send_daily_summary()
at a configurable UTC hour (default: 13 = ~8-9am ET).

Config via environment variables:
    TEAMS_DAILY_SUMMARY_HOUR    — UTC hour for digest (default: "13")
    TEAMS_DAILY_SUMMARY_ENABLED — on/off (default: "true")
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("eagle.daily_scheduler")

SUMMARY_HOUR: int = int(os.getenv("TEAMS_DAILY_SUMMARY_HOUR", "13"))
SUMMARY_ENABLED: bool = os.getenv("TEAMS_DAILY_SUMMARY_ENABLED", "true").lower() == "true"

_task: asyncio.Task | None = None


def _seconds_until_next(hour: int) -> float:
    """Calculate seconds from now until the next occurrence of ``hour`` UTC."""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _daily_loop() -> None:
    """Infinite loop: sleep until target hour, send summary, repeat."""
    from .teams_notifier import send_daily_summary

    while True:
        wait = _seconds_until_next(SUMMARY_HOUR)
        logger.info("Daily scheduler: next summary in %.0f seconds (hour=%d UTC)", wait, SUMMARY_HOUR)
        await asyncio.sleep(wait)

        try:
            await send_daily_summary()
            logger.info("Daily scheduler: summary sent")
        except Exception:
            logger.warning("Daily scheduler: summary failed", exc_info=True)

        # Guard against tight loops if clock skew makes wait ≈ 0
        await asyncio.sleep(60)


def start_scheduler() -> None:
    """Start the daily scheduler background task. Call from FastAPI startup."""
    global _task
    if not SUMMARY_ENABLED:
        logger.info("Daily scheduler disabled (TEAMS_DAILY_SUMMARY_ENABLED=false)")
        return
    if _task is not None:
        return

    try:
        loop = asyncio.get_running_loop()
        _task = loop.create_task(_daily_loop())
        logger.info("Daily scheduler started, target hour=%d UTC", SUMMARY_HOUR)
    except RuntimeError:
        logger.warning("Daily scheduler: no event loop, skipping start")


def stop_scheduler() -> None:
    """Cancel the daily scheduler background task. Call from FastAPI shutdown."""
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("Daily scheduler stopped")
