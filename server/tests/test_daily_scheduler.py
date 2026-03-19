"""Tests for app.daily_scheduler."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

import pytest


# ── _seconds_until_next tests ────────────────────────────────────────

def test_seconds_until_next_future_today():
    """If target hour is later today, returns positive seconds < 24h."""
    from app.daily_scheduler import _seconds_until_next

    # Mock "now" to 10:00 UTC, target hour = 13 → ~3h away
    mock_now = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc)
    with patch("app.daily_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        result = _seconds_until_next(13)

    assert 10700 < result < 10900


def test_seconds_until_next_past_today():
    """If target hour already passed today, returns seconds until tomorrow."""
    from app.daily_scheduler import _seconds_until_next

    # Mock "now" to 15:00 UTC, target hour = 13 → ~22h away
    mock_now = datetime(2026, 3, 19, 15, 0, 0, tzinfo=timezone.utc)
    with patch("app.daily_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        result = _seconds_until_next(13)

    assert 79100 < result < 79300


def test_seconds_until_next_exact_hour():
    """At exactly the target hour, schedules for tomorrow (~24h)."""
    from app.daily_scheduler import _seconds_until_next

    mock_now = datetime(2026, 3, 19, 13, 0, 0, tzinfo=timezone.utc)
    with patch("app.daily_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

        result = _seconds_until_next(13)

    assert 86300 < result < 86500


# ── start_scheduler / stop_scheduler lifecycle ───────────────────────

@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    """start_scheduler creates a task, stop_scheduler cancels it."""
    import app.daily_scheduler as mod

    mod._task = None

    with patch("app.daily_scheduler.SUMMARY_ENABLED", True), \
         patch("app.daily_scheduler._daily_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = None
        mod.start_scheduler()

        assert mod._task is not None
        task = mod._task

        mod.stop_scheduler()
        assert mod._task is None
        assert task.cancelling() or task.cancelled() or task.done()


@pytest.mark.asyncio
async def test_start_scheduler_disabled():
    """start_scheduler is a no-op when SUMMARY_ENABLED is False."""
    import app.daily_scheduler as mod
    mod._task = None

    with patch("app.daily_scheduler.SUMMARY_ENABLED", False):
        mod.start_scheduler()

    assert mod._task is None


@pytest.mark.asyncio
async def test_start_scheduler_idempotent():
    """Calling start_scheduler twice does not create a second task."""
    import app.daily_scheduler as mod
    mod._task = None

    with patch("app.daily_scheduler.SUMMARY_ENABLED", True), \
         patch("app.daily_scheduler._daily_loop", new_callable=AsyncMock):
        mod.start_scheduler()
        first_task = mod._task

        mod.start_scheduler()
        assert mod._task is first_task

    mod.stop_scheduler()
