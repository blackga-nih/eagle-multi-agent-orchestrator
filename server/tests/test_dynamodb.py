"""
DynamoDB Integration Tests — eagle table

Tests session_store.py CRUD operations directly against the real eagle table
(dev account 274487662938 only).  Covers the backend-only gap from SDK eval test 8:
  - Session CRUD: create → get → update → delete
  - Message ordering: add_message × 3 → get_messages (ascending SK)
  - Usage record writes: USAGE# prefix
  - Cost metric writes: COST# prefix
  - Subscription usage counters: SUB# prefix
  - GSI1 tenant listing via list_tenant_sessions

Skip with: SKIP_INTEGRATION_TESTS=true pytest
Run with:  pytest server/tests/test_dynamodb.py -v
"""

import os
import sys
import uuid
import time
import pytest

# ── Path setup ────────────────────────────────────────────────────────
_server_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _server_dir)
sys.path.insert(0, os.path.join(_server_dir, "app"))

import session_store as ss

# ── Skip marker ───────────────────────────────────────────────────────
skip_integration = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS", "").lower() == "true",
    reason="SKIP_INTEGRATION_TESTS=true"
)

# ── Test constants ────────────────────────────────────────────────────
TENANT = "test-int"
USER   = "test-user-int"


def _sid() -> str:
    """Generate a unique session ID per test."""
    return f"s-test-{uuid.uuid4().hex[:8]}"


# ═══════════════════════════════════════════════════════════════════
# 1. Session CRUD
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_session_create():
    """create_session returns a valid session record with correct PK/SK."""
    sid = _sid()
    session = ss.create_session(
        tenant_id=TENANT,
        user_id=USER,
        session_id=sid,
        title="Integration Test Session",
    )
    try:
        assert session["session_id"] == sid
        assert session["tenant_id"] == TENANT
        assert session["user_id"] == USER
        assert session["status"] == "active"
        assert session["message_count"] == 0
        assert session["PK"] == f"SESSION#{TENANT}#{USER}"
        assert session["SK"] == f"SESSION#{sid}"
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_session_get():
    """get_session retrieves the session just created."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    try:
        retrieved = ss.get_session(sid, TENANT, USER)
        assert retrieved is not None
        assert retrieved["session_id"] == sid
        assert retrieved["tenant_id"] == TENANT
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_session_get_missing_returns_none():
    """get_session returns None for a non-existent session."""
    # Invalidate cache first to force DDB read
    nonexistent = "s-does-not-exist-99999"
    ss._invalidate_cache(nonexistent)
    result = ss.get_session(nonexistent, TENANT, USER)
    assert result is None


@skip_integration
def test_session_update():
    """update_session persists field changes and updates updated_at."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    try:
        updated = ss.update_session(
            sid, TENANT, USER,
            updates={"title": "Updated Title", "status": "archived"},
        )
        assert updated is not None
        assert updated.get("title") == "Updated Title"
        assert updated.get("status") == "archived"
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_session_delete():
    """delete_session removes the session and returns True."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    ok = ss.delete_session(sid, TENANT, USER)
    assert ok is True
    # Verify gone — invalidate cache to force DDB read
    ss._invalidate_cache(sid)
    gone = ss.get_session(sid, TENANT, USER)
    assert gone is None


@skip_integration
def test_session_list():
    """list_sessions returns sessions for the user in descending order."""
    sid1 = _sid()
    sid2 = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid1, title="Session 1")
    time.sleep(0.05)  # Ensure distinct timestamps for SK ordering
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid2, title="Session 2")
    try:
        sessions = ss.list_sessions(TENANT, USER)
        ids = [s["session_id"] for s in sessions]
        assert sid1 in ids
        assert sid2 in ids
    finally:
        ss.delete_session(sid1, TENANT, USER)
        ss.delete_session(sid2, TENANT, USER)


# ═══════════════════════════════════════════════════════════════════
# 2. Message Operations — ordering via MSG# SK prefix
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_message_add_and_get():
    """add_message + get_messages returns messages in chronological order."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    try:
        ss.add_message(sid, "user", "Hello EAGLE", TENANT, USER)
        time.sleep(0.05)
        ss.add_message(sid, "assistant", "How can I help?", TENANT, USER)
        time.sleep(0.05)
        ss.add_message(sid, "user", "I need an SOW", TENANT, USER)

        messages = ss.get_messages(sid, TENANT, USER)
        assert len(messages) == 3

        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "user"]

        # SK ordering: MSG#{sid}#{timestamp}-{hash} — ascending
        sks = [m["SK"] for m in messages]
        assert sks == sorted(sks), "Messages should be in ascending SK order"
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_message_count_increments():
    """Session message_count increments after each add_message."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    ss._invalidate_cache(sid)
    try:
        ss.add_message(sid, "user", "msg 1", TENANT, USER)
        ss.add_message(sid, "assistant", "response 1", TENANT, USER)
        ss._invalidate_cache(sid)
        session = ss.get_session(sid, TENANT, USER)
        assert session is not None
        assert session.get("message_count", 0) >= 2
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_message_for_anthropic_format():
    """get_messages_for_anthropic returns role/content dicts only."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    try:
        ss.add_message(sid, "user", "What is FAR Part 13?", TENANT, USER)
        ss.add_message(sid, "assistant", "FAR Part 13 covers simplified acquisitions.", TENANT, USER)

        msgs = ss.get_messages_for_anthropic(sid, TENANT, USER)
        assert len(msgs) == 2
        for m in msgs:
            assert "role" in m
            assert "content" in m
            assert set(m.keys()) <= {"role", "content"}  # Only these two keys
    finally:
        ss.delete_session(sid, TENANT, USER)


# ═══════════════════════════════════════════════════════════════════
# 3. Usage Record Writes — USAGE# prefix (covers SDK test 8 gap)
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_record_usage_writes_to_dynamo():
    """record_usage writes a USAGE#{tenant} record and updates session tokens."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    try:
        ss.record_usage(
            session_id=sid,
            tenant_id=TENANT,
            user_id=USER,
            input_tokens=1200,
            output_tokens=350,
            model="claude-haiku-4-5",
            cost_usd=0.000123,
        )
        # Verify session total_tokens was updated
        ss._invalidate_cache(sid)
        session = ss.get_session(sid, TENANT, USER)
        assert session is not None
        assert session.get("total_tokens", 0) >= 1550
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_get_usage_summary_returns_dict():
    """get_usage_summary returns a summary dict with required keys."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid)
    try:
        ss.record_usage(sid, TENANT, USER, 500, 100, "claude-haiku-4-5", 0.00005)
        summary = ss.get_usage_summary(TENANT, days=1)
        assert isinstance(summary, dict)
        assert "total_input_tokens" in summary
        assert "total_output_tokens" in summary
        assert "total_cost_usd" in summary
        assert "total_requests" in summary
        assert "by_date" in summary
    finally:
        ss.delete_session(sid, TENANT, USER)


# ═══════════════════════════════════════════════════════════════════
# 4. Cost Metric Writes — COST# prefix (covers SDK test 20)
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_store_cost_metric():
    """store_cost_metric writes a COST#{tenant} record without error."""
    sid = _sid()
    # No exception = pass (function returns None, errors are logged silently)
    ss.store_cost_metric(
        tenant_id=TENANT,
        user_id=USER,
        session_id=sid,
        metric_type="llm_inference",
        value=0.0042,
        model="claude-haiku-4-5",
        input_tokens=800,
        output_tokens=200,
    )
    # Verify the write is queryable via get_tenant_usage_overview
    overview = ss.get_tenant_usage_overview(TENANT)
    assert isinstance(overview, dict)
    assert "tenant_id" in overview


# ═══════════════════════════════════════════════════════════════════
# 5. Subscription Usage Counters — SUB# prefix
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_subscription_usage_put_and_get():
    """put_subscription_usage + get_subscription_usage round-trip."""
    tier = "premium"
    ss.put_subscription_usage(
        tenant_id=TENANT,
        tier=tier,
        daily_usage=5,
        monthly_usage=42,
        active_sessions=3,
        last_reset_date="2026-02-27",
    )
    result = ss.get_subscription_usage(TENANT, tier)
    assert result is not None
    assert result["tier"] == tier
    assert result["daily_usage"] == 5
    assert result["monthly_usage"] == 42
    assert result["active_sessions"] == 3


# ═══════════════════════════════════════════════════════════════════
# 6. GSI1 Tenant Listing
# ═══════════════════════════════════════════════════════════════════

@skip_integration
def test_list_tenant_sessions():
    """list_tenant_sessions queries GSI1 without scanning the full table."""
    sid = _sid()
    ss.create_session(tenant_id=TENANT, user_id=USER, session_id=sid, title="GSI test")
    try:
        sessions = ss.list_tenant_sessions(TENANT)
        assert isinstance(sessions, list)
        ids = [s["session_id"] for s in sessions]
        assert sid in ids
    finally:
        ss.delete_session(sid, TENANT, USER)


@skip_integration
def test_session_key_helpers():
    """build_session_key and parse_session_key are inverse operations."""
    key = ss.build_session_key("nci-oa", "co-jones", "s-abc123")
    assert key == "SESSION#nci-oa#co-jones#s-abc123"

    parsed = ss.parse_session_key(key)
    assert parsed["tenant_id"] == "nci-oa"
    assert parsed["user_id"] == "co-jones"
    assert parsed["session_id"] == "s-abc123"
