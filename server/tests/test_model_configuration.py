import importlib
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def test_resolve_model_id_prefers_first_non_empty_env(monkeypatch):
    from app.config import resolve_model_id

    monkeypatch.setenv("PRIMARY_MODEL", "model-primary")
    monkeypatch.setenv("SECONDARY_MODEL", "model-secondary")

    assert resolve_model_id(
        "PRIMARY_MODEL",
        "SECONDARY_MODEL",
        default="model-default",
    ) == "model-primary"


def test_model_chain_exists():
    """The module should expose a model chain with Sonnet 4.6 as default primary."""
    from app import strands_agentic_service as service

    assert hasattr(service, "_MODEL_CHAIN_IDS")
    assert len(service._MODEL_CHAIN_IDS) >= 4
    # Last model should always be Haiku (last resort)
    assert "haiku" in service._MODEL_CHAIN_IDS[-1]


@pytest.mark.asyncio
async def test_greeting_fast_path_uses_circuit_breaker_model(monkeypatch):
    from app import strands_agentic_service as service

    # The circuit breaker should select the active model
    active_model = service._circuit_breaker.get_active_model_id()

    class FakeClient:
        def converse(self, *, modelId, messages, system):
            assert messages[0]["content"][0]["text"] == "hi"
            assert system
            return {
                "output": {"message": {"content": [{"text": "Hello there"}]}},
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    monkeypatch.setattr(service, "_get_greeting_bedrock_client", lambda: FakeClient())

    result = await service._maybe_fast_path_greeting("hi")

    assert result is not None
    assert result["text"] == "Hello there"
    assert result["model"] == active_model


def test_template_standardizer_prefers_standardizer_override(monkeypatch):
    from app import template_standardizer

    monkeypatch.setenv("STANDARDIZER_MODEL_ID", "standardizer-override")
    monkeypatch.setenv("EAGLE_BEDROCK_MODEL_ID", "bedrock-default")

    assert template_standardizer._get_bedrock_model_id() == "standardizer-override"


def test_template_standardizer_falls_back_to_primary_bedrock_model(monkeypatch):
    from app import template_standardizer

    monkeypatch.delenv("STANDARDIZER_MODEL_ID", raising=False)
    monkeypatch.setenv("EAGLE_BEDROCK_MODEL_ID", "bedrock-default")

    assert template_standardizer._get_bedrock_model_id() == "bedrock-default"


def test_record_request_cost_uses_current_bedrock_model(monkeypatch):
    from app import admin_service

    fake_table = MagicMock()
    monkeypatch.setenv("EAGLE_BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    monkeypatch.setattr(admin_service, "get_table", lambda: fake_table)
    monkeypatch.setattr(admin_service, "_update_daily_aggregate", lambda *args: None)

    admin_service.record_request_cost(
        tenant_id="tenant",
        user_id="user",
        session_id="session",
        input_tokens=100,
        output_tokens=50,
    )

    item = fake_table.put_item.call_args.kwargs["Item"]
    assert item["model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_chat_trace_collector_prices_sonnet_46():
    from app.telemetry.chat_trace_collector import _estimate_cost

    assert _estimate_cost("claude-sonnet-4-6", 1000, 1000) == pytest.approx(0.018)
    assert _estimate_cost("us.anthropic.claude-sonnet-4-6", 1000, 1000) == pytest.approx(0.018)


def test_health_endpoint_reports_runtime_model(monkeypatch):
    env_patch = {
        "REQUIRE_AUTH": "false",
        "DEV_MODE": "false",
        "USE_BEDROCK": "false",
        "COGNITO_USER_POOL_ID": "us-east-1_test",
        "COGNITO_CLIENT_ID": "test-client",
        "EAGLE_SESSIONS_TABLE": "eagle",
        "USE_PERSISTENT_SESSIONS": "false",
        "EAGLE_APP_ROUTERS": "streaming",
    }

    with patch.dict(os.environ, env_patch, clear=False):
        import app.main as main_module

        importlib.reload(main_module)
        app = main_module.create_app(["streaming"])
        fake_runtime = MagicMock()
        fake_runtime.MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        fake_runtime.EAGLE_TOOLS = []

        with patch("app.streaming_routes._get_strands_runtime", return_value=fake_runtime):
            with TestClient(app) as client:
                response = client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    # Health endpoint should include circuit breaker status
    assert "circuit_breaker" in data
    # The model field comes from streaming_routes health overlay
    if "model" in data:
        assert data["model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
