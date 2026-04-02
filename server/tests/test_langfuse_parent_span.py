"""
Tests for Langfuse parent span wrapping (Plan: vectorized-sprouting-boole).

Verifies that:
- Langfuse SDK client initializes when credentials are present
- Langfuse SDK client is None when credentials are missing
- sdk_query() opens a parent span via start_as_current_observation
- sdk_query_streaming() opens a parent span that stays open during streaming
- Invocations proceed gracefully when Langfuse is unavailable
- _build_trace_attrs includes langfuse.session.id and langfuse.user.id
"""
import contextlib
import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Test 1: Langfuse client initialized when credentials present
# ---------------------------------------------------------------------------

class TestLangfuseClientInit:
    """Verify _ensure_langfuse_exporter() sets up _langfuse_client."""

    def test_langfuse_client_initialized_when_credentials_present(self):
        """When LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set,
        _langfuse_client should be initialized via get_client()."""
        import app.strands_agentic_service as svc

        # Reset module state
        svc._langfuse_injected = False
        svc._langfuse_client = None

        mock_client = MagicMock()
        mock_provider = MagicMock()
        mock_telemetry = MagicMock()
        mock_telemetry.tracer_provider = mock_provider

        mock_probe_response = MagicMock()
        mock_probe_response.status_code = 200

        with (
            patch.dict(os.environ, {
                "LANGFUSE_PUBLIC_KEY": "pk-test-123",
                "LANGFUSE_SECRET_KEY": "sk-test-456",
            }),
            patch("app.strands_agentic_service.StrandsTelemetry", return_value=mock_telemetry) if hasattr(svc, "StrandsTelemetry") else patch("strands.telemetry.StrandsTelemetry", return_value=mock_telemetry),
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
            patch("opentelemetry.sdk.trace.export.SimpleSpanProcessor"),
            patch("httpx.post", return_value=mock_probe_response),
            patch("langfuse.get_client", return_value=mock_client) as mock_get_client,
        ):
            svc._ensure_langfuse_exporter()

            mock_get_client.assert_called_once()
            assert svc._langfuse_client is mock_client
            assert svc._langfuse_injected is True

        # Cleanup
        svc._langfuse_injected = False
        svc._langfuse_client = None

    def test_langfuse_client_none_when_credentials_missing(self):
        """When Langfuse env vars are missing, _langfuse_client stays None."""
        import app.strands_agentic_service as svc

        svc._langfuse_injected = False
        svc._langfuse_client = None

        with patch.dict(os.environ, {}, clear=False):
            # Remove Langfuse keys if present
            os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            svc._ensure_langfuse_exporter()

        assert svc._langfuse_client is None
        # Reset
        svc._langfuse_injected = False


# ---------------------------------------------------------------------------
# Test 2: _build_trace_attrs includes Langfuse fields
# ---------------------------------------------------------------------------

class TestBuildTraceAttrs:
    """Verify _build_trace_attrs() includes Langfuse-specific span attributes."""

    def test_build_trace_attrs_includes_langfuse_fields(self):
        from app.strands_agentic_service import _build_trace_attrs

        attrs = _build_trace_attrs(
            tenant_id="t1",
            user_id="u1",
            tier="basic",
            session_id="s123",
            username="alice",
        )

        assert attrs["langfuse.session.id"] == "s123"
        assert attrs["langfuse.user.id"] == "alice"
        assert attrs["session.id"] == "s123"
        assert attrs["eagle.tenant_id"] == "t1"
        assert attrs["eagle.tier"] == "basic"

    def test_build_trace_attrs_user_id_fallback(self):
        """When username is empty, langfuse.user.id falls back to user_id."""
        from app.strands_agentic_service import _build_trace_attrs

        attrs = _build_trace_attrs(
            tenant_id="t1",
            user_id="u1",
            tier="basic",
            session_id="s123",
        )

        assert attrs["langfuse.user.id"] == "u1"

    def test_build_trace_attrs_eval_tags(self):
        """Eval runs should get eagle.eval=true and eagle.eval_tags."""
        from app.strands_agentic_service import _build_trace_attrs

        attrs = _build_trace_attrs(
            tenant_id="test-tenant",
            user_id="test-user",
            tier="advanced",
            session_id="s123",
            eval_tags=["langfuse", "tracing"],
        )

        assert attrs.get("eagle.eval") == "true"
        assert attrs["eagle.eval_tags"] == "langfuse,tracing"


# ---------------------------------------------------------------------------
# Helpers for mocking the sdk_query / sdk_query_streaming pipelines
# ---------------------------------------------------------------------------

def _sdk_query_patches(mock_agent_instance):
    """Return a list of patches needed to run sdk_query without real AWS/DB."""
    mock_preload = AsyncMock(return_value={})
    return [
        patch("app.strands_agentic_service._maybe_fast_path_document_generation",
              new_callable=AsyncMock, return_value=None),
        patch("app.strands_agentic_service.build_skill_tools", return_value=[]),
        patch("app.strands_agentic_service._build_service_tools", return_value=[]),
        patch("app.strands_agentic_service.build_supervisor_prompt", return_value="test prompt"),
        patch("app.strands_agentic_service._build_conversation_manager",
              return_value=MagicMock(get_state=MagicMock(return_value={}))),
        patch("app.strands_agentic_service._to_strands_messages", return_value=[]),
        patch("app.strands_agentic_service.Agent", return_value=mock_agent_instance),
        patch("app.strands_agentic_service._ensure_create_document_for_direct_request",
              new_callable=AsyncMock, return_value=None),
        patch("app.session_preloader.preload_session_context", mock_preload),
        patch("app.session_preloader.format_context_for_prompt", return_value=""),
    ]


def _sdk_streaming_patches(mock_agent_instance):
    """Return a list of patches needed to run sdk_query_streaming without real AWS/DB."""
    return _sdk_query_patches(mock_agent_instance) + [
        patch("app.strands_agentic_service._build_end_of_turn_state", return_value=[]),
    ]


# ---------------------------------------------------------------------------
# Test 3: sdk_query opens parent span
# ---------------------------------------------------------------------------

class TestSdkQueryParentSpan:
    """Verify sdk_query() wraps invocation in a Langfuse parent span."""

    @pytest.mark.asyncio
    async def test_sdk_query_opens_parent_span(self):
        """sdk_query() should call start_as_current_observation and propagate_attributes."""
        import app.strands_agentic_service as svc

        mock_root_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_root_span)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        mock_lf_client = MagicMock()
        mock_lf_client.start_as_current_observation.return_value = mock_ctx

        # Mock Agent to avoid real Bedrock calls
        mock_result = MagicMock()
        mock_result.__str__ = lambda self: "test response"
        mock_result.metrics = MagicMock()
        mock_result.metrics.tool_metrics = {}

        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_instance.trace_span = None

        original_client = svc._langfuse_client
        original_injected = svc._langfuse_injected
        try:
            svc._langfuse_client = mock_lf_client
            svc._langfuse_injected = True

            with contextlib.ExitStack() as stack:
                for p in _sdk_query_patches(mock_agent_instance):
                    stack.enter_context(p)

                results = []
                async for msg in svc.sdk_query(
                    prompt="test",
                    tenant_id="t1",
                    user_id="u1",
                    session_id="sess-1234-abcd",
                    username="alice",
                    workspace_id="ws-1",
                ):
                    results.append(msg)

                # Verify parent span was opened
                mock_lf_client.start_as_current_observation.assert_called_once()
                call_kwargs = mock_lf_client.start_as_current_observation.call_args
                assert call_kwargs.kwargs.get("as_type") == "span"
                assert "eagle-query-" in call_kwargs.kwargs.get("name", "")

                # Verify attributes propagated
                mock_lf_client.propagate_attributes.assert_called_once()
                prop_kwargs = mock_lf_client.propagate_attributes.call_args.kwargs
                assert prop_kwargs["session_id"] == "sess-1234-abcd"
                assert prop_kwargs["user_id"] == "alice"

                # Verify span was closed
                mock_ctx.__exit__.assert_called_once()

                # Verify output was set on root span
                mock_root_span.update.assert_called()
        finally:
            svc._langfuse_client = original_client
            svc._langfuse_injected = original_injected

    @pytest.mark.asyncio
    async def test_sdk_query_graceful_when_langfuse_unavailable(self):
        """sdk_query() should work fine when _langfuse_client is None."""
        import app.strands_agentic_service as svc

        mock_result = MagicMock()
        mock_result.__str__ = lambda self: "test response"
        mock_result.metrics = MagicMock()
        mock_result.metrics.tool_metrics = {}

        mock_agent_instance = MagicMock()
        mock_agent_instance.return_value = mock_result
        mock_agent_instance.trace_span = None

        original_client = svc._langfuse_client
        original_injected = svc._langfuse_injected
        try:
            svc._langfuse_client = None
            svc._langfuse_injected = True

            with contextlib.ExitStack() as stack:
                for p in _sdk_query_patches(mock_agent_instance):
                    stack.enter_context(p)

                results = []
                async for msg in svc.sdk_query(
                    prompt="test",
                    tenant_id="t1",
                    user_id="u1",
                    session_id="sess-1234-abcd",
                    workspace_id="ws-1",
                ):
                    results.append(msg)

                # Should have produced results without error
                assert len(results) > 0
        finally:
            svc._langfuse_client = original_client
            svc._langfuse_injected = original_injected


# ---------------------------------------------------------------------------
# Test 4: sdk_query_streaming opens parent span
# ---------------------------------------------------------------------------

class TestSdkQueryStreamingParentSpan:
    """Verify sdk_query_streaming() wraps streaming in a Langfuse parent span."""

    @pytest.mark.asyncio
    async def test_sdk_query_streaming_opens_parent_span(self):
        """sdk_query_streaming() should open a parent span that stays active
        during streaming and is closed after all yields complete."""
        import app.strands_agentic_service as svc

        mock_root_span = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_root_span)
        mock_ctx.__exit__ = MagicMock(return_value=False)

        mock_lf_client = MagicMock()
        mock_lf_client.start_as_current_observation.return_value = mock_ctx

        # Create a mock stream that yields one text event then stops
        async def mock_stream_async(prompt):
            yield {"data": "hello"}

        mock_agent_instance = MagicMock()
        mock_agent_instance.stream_async = mock_stream_async
        mock_agent_instance.trace_span = None

        original_client = svc._langfuse_client
        original_injected = svc._langfuse_injected
        try:
            svc._langfuse_client = mock_lf_client
            svc._langfuse_injected = True

            with contextlib.ExitStack() as stack:
                for p in _sdk_streaming_patches(mock_agent_instance):
                    stack.enter_context(p)

                results = []
                async for chunk in svc.sdk_query_streaming(
                    prompt="test",
                    tenant_id="t1",
                    user_id="u1",
                    session_id="sess-5678-efgh",
                    username="bob",
                    workspace_id="ws-1",
                ):
                    results.append(chunk)

                # Verify parent span was opened
                mock_lf_client.start_as_current_observation.assert_called_once()
                call_kwargs = mock_lf_client.start_as_current_observation.call_args
                assert call_kwargs.kwargs.get("as_type") == "span"
                assert "eagle-stream-" in call_kwargs.kwargs.get("name", "")

                # Verify attributes propagated
                mock_lf_client.propagate_attributes.assert_called_once()
                prop_kwargs = mock_lf_client.propagate_attributes.call_args.kwargs
                assert prop_kwargs["session_id"] == "sess-5678-efgh"
                assert prop_kwargs["user_id"] == "bob"

                # Verify span was closed AFTER streaming completed
                mock_ctx.__exit__.assert_called_once()
        finally:
            svc._langfuse_client = original_client
            svc._langfuse_injected = original_injected
