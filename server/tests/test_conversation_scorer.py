"""Tests for telemetry/conversation_scorer.py — heuristic quality scoring.

Covers:
  - Perfect conversation → 100
  - Incomplete conversation → low score + "incomplete" flag
  - Completed with errors → partial completion + error penalty
  - Tool failures → reduced tool_success points + flag
  - Document requested but not generated → 0 doc points + flag
  - Document requested and generated → full doc points
  - Response length edge cases (empty, short, long, very long)
  - Duration edge cases (fast, normal, slow, timeout)
  - Score clamping to [0, 100]
"""

import pytest

from app.telemetry.conversation_scorer import score_conversation


class TestPerfectConversation:
    """A normal successful conversation should score near 100."""

    def test_perfect_score_with_doc(self):
        """Max score = 30+20+15+10+15 = 90 when doc is requested and generated."""
        result = score_conversation(
            completed=True,
            error_count=0,
            tool_timings=[{"tool_name": "create_document", "duration_ms": 500}],
            tool_failures=[],
            response_text="A" * 200,
            tools_called=["create_document"],
            user_message="Generate a SOW for me",
            duration_ms=5000,
        )
        assert result["score"] == 90
        assert result["breakdown"]["completion"] == 30
        assert result["breakdown"]["tool_success"] == 20
        assert result["breakdown"]["document_delivery"] == 15
        assert result["breakdown"]["response_quality"] == 10
        assert result["breakdown"]["duration"] == 15
        assert "error_penalty" not in result["breakdown"]
        assert result["flags"] == []

    def test_non_doc_conversation_scores_85(self):
        """Without doc generation, max = 30+20+10+10+15 = 85."""
        result = score_conversation(
            completed=True,
            error_count=0,
            tool_timings=[{"tool_name": "search_far", "duration_ms": 500}],
            tool_failures=[],
            response_text="A" * 200,
            tools_called=["search_far"],
            user_message="What is FAR 15.4?",
            duration_ms=5000,
        )
        assert result["score"] == 85
        assert result["breakdown"]["document_delivery"] == 10  # not requested
        assert result["flags"] == []

    def test_returns_required_keys(self):
        result = score_conversation()
        assert "score" in result
        assert "breakdown" in result
        assert "flags" in result


class TestCompletion:
    """Test completion component (30 points max)."""

    def test_incomplete_gets_zero(self):
        result = score_conversation(completed=False, response_text="A" * 100, duration_ms=5000)
        assert result["breakdown"]["completion"] == 0
        assert "incomplete" in result["flags"]

    def test_completed_with_errors_gets_partial(self):
        result = score_conversation(
            completed=True, error_count=2,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["completion"] == 15
        assert "completed_with_2_errors" in result["flags"]

    def test_completed_no_errors_gets_full(self):
        result = score_conversation(
            completed=True, error_count=0,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["completion"] == 30


class TestToolSuccess:
    """Test tool success rate component (20 points max)."""

    def test_all_tools_succeed(self):
        result = score_conversation(
            tool_timings=[{"tool_name": "a", "duration_ms": 100}, {"tool_name": "b", "duration_ms": 200}],
            tool_failures=[],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["tool_success"] == 20

    def test_half_tools_fail(self):
        result = score_conversation(
            tool_timings=[{"tool_name": "a", "duration_ms": 100}, {"tool_name": "b", "duration_ms": 200}],
            tool_failures=[{"tool_name": "b", "error_message": "fail"}],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["tool_success"] == 10
        assert "1_tool_failures" in result["flags"]

    def test_all_tools_fail(self):
        timings = [{"tool_name": "a", "duration_ms": 100}]
        failures = [{"tool_name": "a", "error_message": "fail"}]
        result = score_conversation(
            tool_timings=timings, tool_failures=failures,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["tool_success"] == 0

    def test_no_tools_gets_neutral(self):
        result = score_conversation(
            tool_timings=[], tool_failures=[],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["tool_success"] == 15

    def test_none_tools_gets_neutral(self):
        result = score_conversation(
            tool_timings=None, tool_failures=None,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["tool_success"] == 15


class TestDocumentDelivery:
    """Test document delivery component (15 points max)."""

    def test_doc_requested_and_generated(self):
        result = score_conversation(
            user_message="Please generate a SOW for me",
            tools_called=["create_document"],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["document_delivery"] == 15
        assert "document_requested_not_generated" not in result["flags"]

    def test_doc_requested_not_generated(self):
        result = score_conversation(
            user_message="Please generate an IGCE",
            tools_called=["search_far"],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["document_delivery"] == 0
        assert "document_requested_not_generated" in result["flags"]

    def test_no_doc_requested_gets_partial(self):
        result = score_conversation(
            user_message="What is the FAR citation for sole source?",
            tools_called=[],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["document_delivery"] == 10

    def test_keywords_case_insensitive(self):
        result = score_conversation(
            user_message="DRAFT a document please",
            tools_called=["create_document"],
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["document_delivery"] == 15


class TestResponseQuality:
    """Test response quality component (10 points max)."""

    def test_empty_response(self):
        result = score_conversation(response_text="", duration_ms=5000)
        assert result["breakdown"]["response_quality"] == 0
        assert "empty_response" in result["flags"]

    def test_short_response(self):
        result = score_conversation(response_text="Hi", duration_ms=5000)
        assert result["breakdown"]["response_quality"] == 5
        assert "short_response" in result["flags"]

    def test_normal_response(self):
        result = score_conversation(response_text="A" * 200, duration_ms=5000)
        assert result["breakdown"]["response_quality"] == 10

    def test_very_long_response(self):
        result = score_conversation(response_text="A" * 15000, duration_ms=5000)
        assert result["breakdown"]["response_quality"] == 7
        assert "very_long_response" in result["flags"]

    def test_boundary_50_chars(self):
        result = score_conversation(response_text="A" * 50, duration_ms=5000)
        assert result["breakdown"]["response_quality"] == 10

    def test_boundary_10000_chars(self):
        result = score_conversation(response_text="A" * 10000, duration_ms=5000)
        assert result["breakdown"]["response_quality"] == 10


class TestDuration:
    """Test duration component (15 points max)."""

    def test_normal_duration(self):
        result = score_conversation(response_text="A" * 100, duration_ms=5000)
        assert result["breakdown"]["duration"] == 15

    def test_suspiciously_fast(self):
        result = score_conversation(response_text="A" * 100, duration_ms=100)
        assert result["breakdown"]["duration"] == 5
        assert "suspiciously_fast" in result["flags"]

    def test_slow_response(self):
        result = score_conversation(response_text="A" * 100, duration_ms=200000)
        assert result["breakdown"]["duration"] == 10
        assert "slow_response" in result["flags"]

    def test_timeout_duration(self):
        result = score_conversation(response_text="A" * 100, duration_ms=400000)
        assert result["breakdown"]["duration"] == 0
        assert "timeout_duration" in result["flags"]

    def test_boundary_500ms(self):
        result = score_conversation(response_text="A" * 100, duration_ms=500)
        assert result["breakdown"]["duration"] == 15

    def test_boundary_120000ms(self):
        result = score_conversation(response_text="A" * 100, duration_ms=120000)
        assert result["breakdown"]["duration"] == 15


class TestErrorPenalty:
    """Test error deductions (-10 per error, max -30)."""

    def test_one_error(self):
        result = score_conversation(
            completed=True, error_count=1,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["error_penalty"] == -10

    def test_three_errors_max_penalty(self):
        result = score_conversation(
            completed=True, error_count=3,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["error_penalty"] == -30

    def test_five_errors_capped_at_30(self):
        result = score_conversation(
            completed=True, error_count=5,
            response_text="A" * 100, duration_ms=5000,
        )
        assert result["breakdown"]["error_penalty"] == -30

    def test_no_errors_no_penalty(self):
        result = score_conversation(
            completed=True, error_count=0,
            response_text="A" * 100, duration_ms=5000,
        )
        assert "error_penalty" not in result["breakdown"]


class TestScoreClamping:
    """Score should always be between 0 and 100."""

    def test_score_never_below_zero(self):
        result = score_conversation(
            completed=False,
            error_count=10,
            tool_timings=[{"tool_name": "a", "duration_ms": 1}],
            tool_failures=[{"tool_name": "a", "error_message": "x"}],
            response_text="",
            user_message="generate a SOW",
            tools_called=[],
            duration_ms=999999,
        )
        assert result["score"] >= 0

    def test_score_never_above_100(self):
        result = score_conversation(
            completed=True,
            error_count=0,
            tool_timings=[{"tool_name": "a", "duration_ms": 1}],
            tool_failures=[],
            response_text="A" * 200,
            tools_called=["create_document"],
            user_message="generate a SOW",
            duration_ms=5000,
        )
        assert result["score"] <= 100
