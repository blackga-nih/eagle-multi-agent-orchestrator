"""Unified tests for CloudWatch telemetry emission and reasoning capture."""
import json
from unittest.mock import patch, MagicMock
import pytest


# ── CloudWatch Emitter Tests ─────────────────────────────────────


class TestCloudWatchEmitter:

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_emits_to_eagle_app_log_group(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("trace.started", "t1", {"msg": "hi"}, "s1", "u1")
        call_args = mock_client.put_log_events.call_args
        assert call_args.kwargs["logGroupName"] == "/eagle/telemetry"

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_stream_name_uses_session_id(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, session_id="sess-abc", user_id="u1")
        call_args = mock_client.create_log_stream.call_args
        stream = call_args.kwargs.get(
            "logStreamName",
            call_args[1].get("logStreamName", "") if len(call_args) > 1 else "",
        )
        assert "sess-abc" in stream

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_stream_name_falls_back_to_tenant(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, session_id=None, user_id="u1")
        call_args = mock_client.put_log_events.call_args
        stream = call_args.kwargs.get("logStreamName", "")
        assert "t1" in stream

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_handles_already_exists(self, mock_get_client):
        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.create_log_group.side_effect = ClientError(
            {"Error": {"Code": "ResourceAlreadyExistsException"}}, "CreateLogGroup"
        )
        mock_client.create_log_stream.side_effect = ClientError(
            {"Error": {"Code": "ResourceAlreadyExistsException"}}, "CreateLogStream"
        )
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        emit_telemetry_event("test", "t1", {}, "s1", "u1")
        mock_client.put_log_events.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter._get_client")
    def test_swallows_put_failure(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.put_log_events.side_effect = Exception("CloudWatch down")
        mock_get_client.return_value = mock_client
        from app.telemetry.cloudwatch_emitter import emit_telemetry_event
        # Should not raise
        emit_telemetry_event("test", "t1", {}, "s1", "u1")

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_trace_started(self, mock_emit):
        from app.telemetry.cloudwatch_emitter import emit_trace_started
        emit_trace_started("t1", "u1", "s1", "hello world")
        mock_emit.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_tool_completed(self, mock_emit):
        from app.telemetry.cloudwatch_emitter import emit_tool_completed
        emit_tool_completed("t1", "u1", "s1", "search_far", 120, True)
        mock_emit.assert_called_once()

    @patch("app.telemetry.cloudwatch_emitter.emit_telemetry_event")
    def test_emit_feedback_submitted(self, mock_emit):
        from app.telemetry.cloudwatch_emitter import emit_feedback_submitted
        emit_feedback_submitted("t1", "u1", "s1", "bug", "fb-001")
        mock_emit.assert_called_once()


# ── Reasoning Log Tests ──────────────────────────────────────────


class TestReasoningLog:

    def test_add_entry(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add(
            "compliance_check", "query_compliance_matrix",
            "Value $85K triggers simplified", "FAR 13.5",
        )
        assert len(log.entries) == 1
        assert log.entries[0].tool_name == "query_compliance_matrix"

    def test_to_json_includes_timestamp(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("tool_call", "search_far", "Looking up FAR 13.5", "Found 3 sections")
        result = log.to_json()
        assert len(result) == 1
        assert "timestamp" in result[0]
        assert result[0]["tool_name"] == "search_far"

    def test_to_appendix_markdown(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add(
            "compliance_check", "query_compliance_matrix",
            "$85K → simplified", "FAR 13.5", confidence="high",
        )
        log.add(
            "document_generation", "create_document",
            "Generating SOW from intake", "SOW v1 created",
        )
        md = log.to_appendix_markdown()
        assert "AI Decision Rationale" in md
        assert "FAR 13.5" in md
        assert "SOW v1 created" in md

    def test_empty_log_no_appendix(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        assert log.to_appendix_markdown() == ""

    @patch("app.reasoning_store._get_table")
    def test_save_to_dynamodb(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog("sess-1", "tenant-1", "user-1")
        log.add("tool_call", "search_far", "test", "test result")
        log.save()
        mock_tbl.put_item.assert_called_once()
        item = mock_tbl.put_item.call_args.kwargs["Item"]
        assert item["PK"] == "SESSION#sess-1"
        assert item["SK"] == "REASONING#sess-1"

    @patch("app.reasoning_store._get_table")
    def test_load_from_dynamodb(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {
            "Item": {
                "PK": "SESSION#sess-1",
                "SK": "REASONING#sess-1",
                "reasoning_entries": json.dumps([{
                    "timestamp": "2026-03-10T18:00:00Z",
                    "event_type": "tool_call",
                    "tool_name": "search_far",
                    "reasoning": "test",
                    "determination": "found",
                    "data": {},
                    "confidence": "high",
                }]),
            }
        }
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog.load("sess-1", "tenant-1", "user-1")
        assert len(log.entries) == 1

    @patch("app.reasoning_store._get_table")
    def test_load_missing_returns_empty(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_tbl.get_item.return_value = {}
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog.load("no-exist", "t1", "u1")
        assert len(log.entries) == 0

    @patch("app.reasoning_store._get_table")
    def test_save_empty_log_is_noop(self, mock_table_fn):
        from app.reasoning_store import ReasoningLog
        mock_tbl = MagicMock()
        mock_table_fn.return_value = mock_tbl
        log = ReasoningLog("sess-1", "t1", "u1")
        log.save()
        mock_tbl.put_item.assert_not_called()


# ── Document Appendix Tests ──────────────────────────────────────


class TestDocumentAppendix:

    def test_appendix_renders_entries(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("s1", "t1", "u1")
        log.add(
            "compliance_check", "query_compliance_matrix",
            "$85K triggers simplified", "FAR 13.5", confidence="high",
        )
        md = log.to_appendix_markdown()
        assert "Appendix: AI Decision Rationale" in md
        assert "compliance_check" in md
        assert "$85K triggers simplified" in md

    def test_appendix_empty_when_no_entries(self):
        from app.reasoning_store import ReasoningLog
        log = ReasoningLog("s1", "t1", "u1")
        assert log.to_appendix_markdown() == ""
