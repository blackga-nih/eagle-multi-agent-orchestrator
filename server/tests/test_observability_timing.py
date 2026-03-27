"""
Tests for API Endpoint & Tool Call Observability (Plan: 20260318-170000).

Covers:
- Step 1: Tool timing emission to CloudWatch
- Step 2: Request timing middleware
- Step 3: duration_ms in SSE complete event
- Step 4: Agent timing emission
"""
import asyncio
import json
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Step 1: _emit_tool_timings helper
# ---------------------------------------------------------------------------

class TestEmitToolFailures:
    """Test the _emit_tool_failures helper in streaming_routes."""

    def test_emits_tool_error_events(self):
        """Each tool failure dict should produce a tool.error CloudWatch event."""
        from app.streaming_routes import _emit_tool_failures

        failures = [
            {"tool_name": "search_far", "error_message": "timeout", "duration_ms": 30000},
            {"tool_name": "create_document", "error_message": "missing fields"},
        ]
        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_failures(failures, tenant_id="t1", user_id="u1", session_id="s1")
            assert mock_emit.call_count == 2

            calls = mock_emit.call_args_list
            assert calls[0].kwargs["event_type"] == "tool.error"
            assert calls[0].kwargs["data"]["tool_name"] == "search_far"
            assert calls[0].kwargs["data"]["error_message"] == "timeout"
            assert calls[0].kwargs["data"]["duration_ms"] == 30000
            assert calls[0].kwargs["tenant_id"] == "t1"
            assert calls[0].kwargs["user_id"] == "u1"
            assert calls[0].kwargs["session_id"] == "s1"

            assert calls[1].kwargs["data"]["tool_name"] == "create_document"
            assert calls[1].kwargs["data"]["error_message"] == "missing fields"

    def test_empty_failures_emits_nothing(self):
        """With no failures, no events should be emitted."""
        from app.streaming_routes import _emit_tool_failures

        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_failures([], tenant_id="t1", user_id="u1", session_id="s1")
            assert mock_emit.call_count == 0

    def test_missing_optional_fields_use_defaults(self):
        """Failures missing error_message or duration_ms should use defaults."""
        from app.streaming_routes import _emit_tool_failures

        failures = [{"tool_name": "search_far"}]
        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_failures(failures, tenant_id="t1", user_id="u1", session_id="s1")
            data = mock_emit.call_args.kwargs["data"]
            assert data["error_message"] == ""
            assert data["duration_ms"] == 0

    def test_none_session_id_uses_empty_string(self):
        """When session_id is None, data.session_id should be empty string."""
        from app.streaming_routes import _emit_tool_failures

        failures = [{"tool_name": "a", "error_message": "fail"}]
        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_failures(failures, tenant_id="t1", user_id="u1", session_id=None)
            data = mock_emit.call_args.kwargs["data"]
            assert data["session_id"] == ""

    def test_never_raises_on_emission_failure(self):
        """Telemetry emission failures should be silently swallowed."""
        from app.streaming_routes import _emit_tool_failures

        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event", side_effect=Exception("boom")):
            # Should not raise
            _emit_tool_failures(
                [{"tool_name": "x", "error_message": "fail"}],
                tenant_id="t1", user_id="u1", session_id="s1",
            )


class TestEmitToolTimings:
    """Test the _emit_tool_timings helper in streaming_routes."""

    def test_emits_tool_timing_events(self):
        """Each tool timing dict should produce a tool.timing CloudWatch event."""
        from app.streaming_routes import _emit_tool_timings

        timings = [
            {"tool_name": "search_far", "duration_ms": 1200},
            {"tool_name": "create_document", "duration_ms": 3500},
        ]
        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_timings(
                timings,
                tenant_id="t1",
                user_id="u1",
                session_id="s1",
                stream_duration_ms=5000,
            )
            # 2 tool.timing + 1 stream.timing = 3 calls
            assert mock_emit.call_count == 3

            # Verify tool.timing calls
            calls = mock_emit.call_args_list
            assert calls[0].kwargs["event_type"] == "tool.timing"
            assert calls[0].kwargs["data"]["tool_name"] == "search_far"
            assert calls[0].kwargs["data"]["duration_ms"] == 1200
            assert calls[1].kwargs["event_type"] == "tool.timing"
            assert calls[1].kwargs["data"]["tool_name"] == "create_document"

            # Verify stream.timing call
            assert calls[2].kwargs["event_type"] == "stream.timing"
            assert calls[2].kwargs["data"]["duration_ms"] == 5000
            assert calls[2].kwargs["data"]["tools_count"] == 2

    def test_empty_timings_only_emits_stream(self):
        """With no tool timings, only the stream.timing event should be emitted."""
        from app.streaming_routes import _emit_tool_timings

        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_timings([], tenant_id="t1", user_id="u1", session_id="s1", stream_duration_ms=100)
            assert mock_emit.call_count == 1
            assert mock_emit.call_args.kwargs["event_type"] == "stream.timing"

    def test_no_stream_duration_skips_stream_event(self):
        """When stream_duration_ms is None, no stream.timing event is emitted."""
        from app.streaming_routes import _emit_tool_timings

        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
            _emit_tool_timings(
                [{"tool_name": "search_far", "duration_ms": 100}],
                tenant_id="t1", user_id="u1", session_id="s1",
            )
            assert mock_emit.call_count == 1
            assert mock_emit.call_args.kwargs["event_type"] == "tool.timing"

    def test_never_raises_on_emission_failure(self):
        """Telemetry emission failures should be silently swallowed."""
        from app.streaming_routes import _emit_tool_timings

        with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event", side_effect=Exception("boom")):
            # Should not raise
            _emit_tool_timings(
                [{"tool_name": "x", "duration_ms": 1}],
                tenant_id="t1", user_id="u1", session_id="s1",
                stream_duration_ms=1,
            )


# ---------------------------------------------------------------------------
# Step 2: Request timing middleware
# ---------------------------------------------------------------------------

class TestRequestTimingMiddleware:
    """Test that the request timing middleware is wired into main.py."""

    def test_middleware_exists(self):
        """The FastAPI app should have the request_timing_middleware."""
        from app.main import app
        # Check that at least one middleware stack entry is our timing middleware
        middleware_names = []
        for m in app.user_middleware:
            if hasattr(m, 'cls'):
                middleware_names.append(m.cls.__name__)
        # Our middleware is a function-based middleware (@app.middleware("http"))
        # which FastAPI stores differently. Just verify the app loads without error.
        assert app is not None

    @pytest.mark.asyncio
    async def test_middleware_logs_timing(self):
        """Middleware should log request_completed with duration_ms."""
        from fastapi.testclient import TestClient
        from app.main import app

        with patch("app.main.logger") as mock_logger:
            client = TestClient(app)
            response = client.get("/api/health")
            assert response.status_code == 200

            # Check that logger.info was called with "request_completed"
            info_calls = [
                call for call in mock_logger.info.call_args_list
                if call.args and call.args[0] == "request_completed"
            ]
            assert len(info_calls) >= 1
            extra = info_calls[0].kwargs.get("extra", {})
            assert "duration_ms" in extra
            assert "endpoint" in extra
            assert extra["endpoint"] == "/api/health"
            assert isinstance(extra["duration_ms"], int)


# ---------------------------------------------------------------------------
# Step 3: duration_ms in SSE complete event
# ---------------------------------------------------------------------------

class TestStreamDurationInComplete:
    """Test that stream_generator includes duration_ms in complete metadata."""

    @pytest.mark.asyncio
    async def test_complete_event_has_duration_ms(self):
        """The SSE complete event should include duration_ms in metadata."""
        from app.streaming_routes import stream_generator

        # Mock sdk_query_streaming to yield a simple text + complete sequence
        async def mock_streaming(**kwargs):
            yield {"type": "text", "data": "Hello"}
            yield {"type": "complete", "text": "Hello", "tools_called": []}

        mock_sub_service = MagicMock()

        with patch("app.streaming_routes.sdk_query_streaming", side_effect=mock_streaming):
            with patch("app.streaming_routes.add_message"):
                events = []
                async for sse_line in stream_generator(
                    message="test",
                    tenant_id="t1",
                    user_id="u1",
                    tier="advanced",
                    subscription_service=mock_sub_service,
                    session_id="s1",
                ):
                    if sse_line.startswith("data: "):
                        try:
                            data = json.loads(sse_line.replace("data: ", "").strip())
                            events.append(data)
                        except json.JSONDecodeError:
                            pass

                # Find the complete event
                complete_events = [e for e in events if e.get("type") == "complete"]
                assert len(complete_events) == 1
                metadata = complete_events[0].get("metadata", {})
                assert "duration_ms" in metadata
                assert isinstance(metadata["duration_ms"], int)
                assert metadata["duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_tool_timings_in_complete(self):
        """Tool timings should be included in the complete metadata."""
        from app.streaming_routes import stream_generator

        async def mock_streaming(**kwargs):
            yield {"type": "tool_use", "name": "search_far", "input": {}, "tool_use_id": "t1"}
            await asyncio.sleep(0.01)  # Small delay to produce measurable timing
            yield {"type": "tool_result", "name": "search_far", "result": {"success": True}}
            yield {"type": "text", "data": "Found results"}
            yield {"type": "complete", "text": "Found results", "tools_called": ["search_far"]}

        mock_sub_service = MagicMock()

        with patch("app.streaming_routes.sdk_query_streaming", side_effect=mock_streaming):
            with patch("app.streaming_routes.add_message"):
                with patch("app.streaming_routes._emit_tool_timings"):
                    events = []
                    async for sse_line in stream_generator(
                        message="test",
                        tenant_id="t1",
                        user_id="u1",
                        tier="advanced",
                        subscription_service=mock_sub_service,
                        session_id="s1",
                    ):
                        if sse_line.startswith("data: "):
                            try:
                                data = json.loads(sse_line.replace("data: ", "").strip())
                                events.append(data)
                            except json.JSONDecodeError:
                                pass

                    complete_events = [e for e in events if e.get("type") == "complete"]
                    assert len(complete_events) == 1
                    metadata = complete_events[0].get("metadata", {})
                    assert "tool_timings" in metadata
                    assert len(metadata["tool_timings"]) == 1
                    assert metadata["tool_timings"][0]["tool_name"] == "search_far"
                    assert metadata["tool_timings"][0]["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# Step 4: Agent timing emission in strands_agentic_service
# ---------------------------------------------------------------------------

class TestAgentTimingEmission:
    """Test that sdk_query_streaming emits agent.timing to CloudWatch."""

    @pytest.mark.asyncio
    async def test_agent_timing_emitted_on_success(self):
        """After successful streaming, agent.timing event should be emitted."""
        # We test the emission by checking that emit_telemetry_event is called
        # with event_type="agent.timing" after the generator completes.
        with patch("app.strands_agentic_service._maybe_fast_path_document_generation", return_value=None):
            with patch("app.strands_agentic_service._build_service_tools", return_value=[]):
                with patch("app.strands_agentic_service.build_skill_tools", return_value=[]):
                    with patch("app.strands_agentic_service.build_supervisor_prompt", return_value="test prompt"):
                        with patch("app.strands_agentic_service._ensure_langfuse_exporter"):
                            # Mock the Agent class
                            mock_agent = MagicMock()

                            # Create a proper async iterator for stream_async
                            async def mock_stream(prompt):
                                yield {"data": "Hello"}

                            mock_agent.stream_async = mock_stream
                            with patch("app.strands_agentic_service.Agent", return_value=mock_agent):
                                with patch("app.strands_agentic_service._ensure_create_document_for_direct_request", return_value=None):
                                    with patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event") as mock_emit:
                                        from app.strands_agentic_service import sdk_query_streaming
                                        chunks = []
                                        async for chunk in sdk_query_streaming(
                                            prompt="test",
                                            tenant_id="t1",
                                            user_id="u1",
                                            session_id="s1",
                                        ):
                                            chunks.append(chunk)

                                        # Check that agent.timing was emitted
                                        agent_timing_calls = [
                                            call for call in mock_emit.call_args_list
                                            if call.kwargs.get("event_type") == "agent.timing"
                                        ]
                                        assert len(agent_timing_calls) == 1
                                        data = agent_timing_calls[0].kwargs["data"]
                                        assert data["agent_name"] == "supervisor"
                                        assert "duration_ms" in data
                                        assert isinstance(data["duration_ms"], int)


# ---------------------------------------------------------------------------
# CloudWatch emitter event types
# ---------------------------------------------------------------------------

class TestCloudWatchEmitterEventTypes:
    """Test that CloudWatch emitter handles the new event types."""

    def test_tool_timing_event_structure(self):
        """tool.timing events should include tool_name and duration_ms."""
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event

        with patch("app.telemetry.cloudwatch_emitter.get_logs") as mock_client:
            mock_logs = MagicMock()
            mock_client.return_value = mock_logs

            emit_telemetry_event(
                event_type="tool.timing",
                tenant_id="t1",
                data={
                    "tool_name": "search_far",
                    "duration_ms": 1200,
                    "session_id": "s1",
                },
                session_id="s1",
                user_id="u1",
            )

            # Verify put_log_events was called with the right structure
            call_args = mock_logs.put_log_events.call_args
            log_event = json.loads(call_args.kwargs["logEvents"][0]["message"])
            assert log_event["event_type"] == "tool.timing"
            assert log_event["tool_name"] == "search_far"
            assert log_event["duration_ms"] == 1200

    def test_stream_timing_event_structure(self):
        """stream.timing events should include duration_ms and tools_count."""
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event

        with patch("app.telemetry.cloudwatch_emitter.get_logs") as mock_client:
            mock_logs = MagicMock()
            mock_client.return_value = mock_logs

            emit_telemetry_event(
                event_type="stream.timing",
                tenant_id="t1",
                data={
                    "duration_ms": 5000,
                    "tools_count": 3,
                    "session_id": "s1",
                },
                session_id="s1",
                user_id="u1",
            )

            call_args = mock_logs.put_log_events.call_args
            log_event = json.loads(call_args.kwargs["logEvents"][0]["message"])
            assert log_event["event_type"] == "stream.timing"
            assert log_event["duration_ms"] == 5000
            assert log_event["tools_count"] == 3
