from app.strands_tools import list_specialist_metadata, resolve_tools_for_specialist


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
