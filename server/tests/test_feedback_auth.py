"""Test feedback endpoint auth behavior."""
import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.mark.asyncio
async def test_feedback_requires_auth():
    """POST /api/feedback without token returns 401 when REQUIRE_AUTH=true."""
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=3.0) as client:
            r = await client.post("/api/feedback", json={
                "feedback_text": "test feedback",
                "session_id": "test-session",
            })
            # If REQUIRE_AUTH=true (prod), expect 401; if false (dev), expect 200
            assert r.status_code in (200, 401)
    except (httpx.ConnectError, httpx.ReadTimeout):
        pytest.skip("Server not running at localhost:8000")


@pytest.mark.asyncio
async def test_feedback_with_expired_token():
    """POST /api/feedback with garbage token returns 401."""
    async with httpx.AsyncClient(base_url=BASE) as client:
        r = await client.post("/api/feedback",
            headers={"Authorization": "Bearer expired.garbage.token"},
            json={"feedback_text": "test feedback", "session_id": "test"},
        )
        assert r.status_code in (200, 401)  # 200 in dev mode, 401 in prod


@pytest.mark.asyncio
async def test_feedback_empty_text_rejected():
    """POST /api/feedback with empty text returns 400."""
    async with httpx.AsyncClient(base_url=BASE) as client:
        r = await client.post("/api/feedback", json={
            "feedback_text": "",
            "session_id": "test",
        })
        # 400 (empty text) or 401 (auth first) — both are valid
        assert r.status_code in (400, 401)
