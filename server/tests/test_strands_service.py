import pytest

from app.strands_tools import list_specialist_metadata, resolve_tools_for_specialist
from app.strands_agentic_service import normalize_stream_event, _normalize_tier, _over_budget


def test_tier_gating_preserves_metadata_precedence():
    explicit = {"tools": ["Read"]}
    fallback = {"tools": []}

    assert resolve_tools_for_specialist(explicit, "premium") == ["Read"]
    assert resolve_tools_for_specialist(fallback, "advanced") == ["Read", "Glob", "Grep"]


def test_specialist_metadata_is_discoverable():
    rows = list_specialist_metadata(tier="advanced")
    assert rows
    names = {r["name"] for r in rows}
    assert "supervisor" not in names


def test_normalize_stream_event_text():
    event = {"data": "hello"}
    assert normalize_stream_event(event) == {"type": "text", "content": "hello"}


def test_normalize_stream_event_tool_use():
    event = {"current_tool_use": {"name": "oa-intake", "input": {"q": "x"}}}
    assert normalize_stream_event(event) == {
        "type": "tool_use",
        "name": "oa-intake",
        "input": {"q": "x"},
    }


def test_normalize_stream_event_complete_usage():
    event = {"result": {"usage": {"input_tokens": 12, "output_tokens": 34}, "text": "done"}}
    assert normalize_stream_event(event) == {
        "type": "complete",
        "usage": {"input_tokens": 12, "output_tokens": 34},
        "result": "done",
    }


def test_normalize_stream_event_error():
    event = {"error": "boom"}
    assert normalize_stream_event(event) == {"type": "error", "message": "boom"}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("basic", "basic"),
        ("advanced", "advanced"),
        ("premium", "premium"),
        ("free", "basic"),
        ("enterprise", "premium"),
        ("unknown", "advanced"),
    ],
)
def test_tier_normalization(raw, expected):
    assert _normalize_tier(raw) == expected


def test_budget_check_uses_shared_cost_function_shape():
    assert _over_budget({"input_tokens": 1_000_000, "output_tokens": 1_000_000}, "basic") is True
    assert _over_budget({"input_tokens": 1, "output_tokens": 1}, "premium") is False
