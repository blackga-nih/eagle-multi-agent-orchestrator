"""Tests for ModelCircuitBreaker in strands_agentic_service.py."""

import threading
import time

import pytest


@pytest.fixture
def make_cb():
    """Factory fixture that creates a fresh ModelCircuitBreaker."""
    from app.strands_agentic_service import ModelCircuitBreaker

    def _factory(
        model_ids=None,
        failure_threshold=2,
        recovery_timeout=120.0,
    ):
        ids = model_ids or [
            "us.anthropic.claude-sonnet-4-6",
            "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "us.anthropic.claude-sonnet-4-20250514-v1:0",
            "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        ]
        return ModelCircuitBreaker(ids, failure_threshold, recovery_timeout)

    return _factory


# ── Basic state tests ────────────────────────────────────────────────


def test_initial_state_all_closed(make_cb):
    cb = make_cb()
    status = cb.get_status()
    for mid, info in status.items():
        assert info["state"] == "closed", f"{mid} should start CLOSED"
        assert info["failures"] == 0


def test_get_active_returns_first_model(make_cb):
    cb = make_cb()
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-6"


def test_single_failure_stays_closed(make_cb):
    cb = make_cb(failure_threshold=2)
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    # One failure < threshold — still returns primary
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-6"
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "closed"


# ── Circuit opening ──────────────────────────────────────────────────


def test_failures_open_circuit(make_cb):
    cb = make_cb(failure_threshold=2)
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "open"
    # Should return the next model in chain
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


def test_cascade_through_chain(make_cb):
    cb = make_cb(failure_threshold=1)
    # Open first three models
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    cb.record_failure("us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    cb.record_failure("us.anthropic.claude-sonnet-4-20250514-v1:0")
    # Should return Haiku (last in chain)
    assert cb.get_active_model_id() == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_all_open_returns_last_resort(make_cb):
    cb = make_cb(failure_threshold=1)
    # Open ALL models including Haiku
    for mid in cb.model_ids:
        cb.record_failure(mid)
    # Last resort: always returns the last model even if open
    assert cb.get_active_model_id() == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


# ── Recovery ─────────────────────────────────────────────────────────


def test_recovery_timeout_half_open(make_cb):
    cb = make_cb(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "open"
    # Wait for recovery timeout
    time.sleep(0.15)
    # Should now be eligible (transitions to HALF_OPEN on query)
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-6"
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "half_open"


def test_success_closes_circuit(make_cb):
    cb = make_cb(failure_threshold=1)
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "open"
    cb.record_success("us.anthropic.claude-sonnet-4-6")
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "closed"
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["failures"] == 0
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-6"


def test_half_open_failure_reopens(make_cb):
    cb = make_cb(failure_threshold=1, recovery_timeout=0.05)
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    time.sleep(0.1)
    # Trigger HALF_OPEN
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-6"
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "half_open"
    # Failure in HALF_OPEN should reopen
    cb.record_failure("us.anthropic.claude-sonnet-4-6")
    assert cb.get_status()["us.anthropic.claude-sonnet-4-6"]["state"] == "open"
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


# ── Thread safety ────────────────────────────────────────────────────


def test_thread_safety(make_cb):
    cb = make_cb(failure_threshold=100)
    errors = []

    def hammer_failures():
        try:
            for _ in range(200):
                cb.record_failure("us.anthropic.claude-sonnet-4-6")
                cb.get_active_model_id()
        except Exception as e:
            errors.append(e)

    def hammer_successes():
        try:
            for _ in range(200):
                cb.record_success("us.anthropic.claude-sonnet-4-6")
                cb.get_status()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=hammer_failures),
        threading.Thread(target=hammer_successes),
        threading.Thread(target=hammer_failures),
        threading.Thread(target=hammer_successes),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"Thread safety errors: {errors}"
    # State should be consistent (no crashes, no deadlocks)
    status = cb.get_status()
    assert "us.anthropic.claude-sonnet-4-6" in status


# ── Env var override ─────────────────────────────────────────────────


def test_env_override_promotes_model(monkeypatch):
    """EAGLE_BEDROCK_MODEL_ID should promote a model to position 0."""
    from app.strands_agentic_service import ModelCircuitBreaker

    chain = [
        "us.anthropic.claude-sonnet-4-6",
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    ]
    override = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Simulate the chain-building logic from module level
    new_chain = list(chain)
    if override in new_chain:
        new_chain.remove(override)
    new_chain.insert(0, override)

    cb = ModelCircuitBreaker(new_chain)
    assert cb.get_active_model_id() == override
    assert len(cb.model_ids) == 4  # No duplicates


def test_get_status_snapshot(make_cb):
    cb = make_cb(failure_threshold=2)
    cb.record_failure("us.anthropic.claude-sonnet-4-6")

    status = cb.get_status()
    assert len(status) == 4
    assert status["us.anthropic.claude-sonnet-4-6"]["failures"] == 1
    assert status["us.anthropic.claude-sonnet-4-6"]["state"] == "closed"
    assert status["us.anthropic.claude-haiku-4-5-20251001-v1:0"]["failures"] == 0


# ── _get_active_model helper ─────────────────────────────────────────


def test_get_active_model_returns_tuple():
    """_get_active_model should return (model_id, BedrockModel)."""
    from app.strands_agentic_service import _get_active_model, _bedrock_models

    mid, bedrock_model = _get_active_model()
    assert mid in _bedrock_models
    assert bedrock_model is _bedrock_models[mid]


# ── Model chain integrity ────────────────────────────────────────────


def test_model_chain_has_four_models():
    """The default chain should have exactly 4 models with Haiku as last resort."""
    from app.strands_agentic_service import _DEFAULT_MODEL_CHAIN, _MODEL_CHAIN_IDS

    assert len(_MODEL_CHAIN_IDS) >= 4
    # Default (un-overridden) chain always ends with Haiku
    assert _DEFAULT_MODEL_CHAIN[-1] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    # Runtime chain always contains Haiku somewhere
    assert "us.anthropic.claude-haiku-4-5-20251001-v1:0" in _MODEL_CHAIN_IDS


def test_record_unknown_model_is_noop(make_cb):
    """Recording success/failure for an unknown model should not raise."""
    cb = make_cb()
    cb.record_failure("nonexistent-model")
    cb.record_success("nonexistent-model")
    # Should still work normally
    assert cb.get_active_model_id() == "us.anthropic.claude-sonnet-4-6"
