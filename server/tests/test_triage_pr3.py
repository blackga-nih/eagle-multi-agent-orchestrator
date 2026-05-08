"""Unit tests for triage PR3 patches.

Covers three issues from the 04-28 → 05-04 nightly triage sweep:
- #6: estimated_value parsing ("$280", "1.8M") + Decimal coercion
- #7: teams_notifier per-call AsyncClient (no module singleton)
- #8: knowledge_tools _salvage_partial_ranking_json regex recovery

All tests are pure-Python — no AWS, no model calls, no fixtures.
"""

from __future__ import annotations

import os
from decimal import Decimal

# Tests in this repo expect S3_BUCKET set via .env or fixture; set a stub here
# in case this module is collected before the .env autoload runs.
os.environ.setdefault("S3_BUCKET", "test-bucket")


class TestEstimatedValueCoercion:
    """Triage #6: AI returns '$280' / '1.8M' / '$1,200,000' — must parse to float."""

    def _model(self):
        from app.ai_document_schema import IgceDocumentData
        return IgceDocumentData

    def test_dollar_prefix(self):
        m = self._model()(estimated_value="$280")
        assert m.estimated_value == 280.0

    def test_dollar_with_commas(self):
        m = self._model()(estimated_value="$1,200,000")
        assert m.estimated_value == 1_200_000.0

    def test_magnitude_suffix_m(self):
        m = self._model()(estimated_value="1.8M")
        assert m.estimated_value == 1_800_000.0

    def test_magnitude_suffix_k(self):
        m = self._model()(estimated_value="850k")
        assert m.estimated_value == 850_000.0

    def test_native_float_passes_through(self):
        m = self._model()(estimated_value=42.5)
        assert m.estimated_value == 42.5

    def test_native_int_passes_through(self):
        m = self._model()(estimated_value=100)
        assert m.estimated_value == 100

    def test_unparseable_returns_none(self):
        # Graceful fallback — IGCE generation tolerates a missing value.
        m = self._model()(estimated_value="not a number")
        assert m.estimated_value is None

    def test_empty_string_returns_none(self):
        m = self._model()(estimated_value="")
        assert m.estimated_value is None

    def test_whitespace_stripped(self):
        m = self._model()(estimated_value="  $1,000  ")
        assert m.estimated_value == 1000.0


class TestDynamoSafeCoercion:
    """Triage #6 (boundary): floats must be Decimal before DynamoDB put_item."""

    def _fn(self):
        from app.document_service import _to_dynamo_safe
        return _to_dynamo_safe

    def test_float_to_decimal(self):
        assert self._fn()(1.5) == Decimal("1.5")

    def test_int_unchanged(self):
        assert self._fn()(42) == 42

    def test_string_unchanged(self):
        assert self._fn()("hello") == "hello"

    def test_dict_recurses(self):
        out = self._fn()({"a": 1.5, "b": "x"})
        assert out == {"a": Decimal("1.5"), "b": "x"}

    def test_nested_list_recurses(self):
        out = self._fn()({"prices": [1.0, 2.5, 3.14]})
        assert out["prices"] == [Decimal("1.0"), Decimal("2.5"), Decimal("3.14")]

    def test_deep_nesting(self):
        out = self._fn()({"a": {"b": [{"c": 9.99}]}})
        assert out["a"]["b"][0]["c"] == Decimal("9.99")

    def test_none_unchanged(self):
        assert self._fn()(None) is None


class TestRankingJsonSalvage:
    """Triage #8: Haiku occasionally truncates mid-object on 100-doc batches."""

    def _fn(self):
        from app.tools.knowledge_tools import _salvage_partial_ranking_json
        return _salvage_partial_ranking_json

    def test_truncated_mid_object_salvages_complete_entries(self):
        truncated = (
            '[{"i":5,"r":"sole source J&A"}, '
            '{"i":12,"r":"PMR checklist"}, '
            '{"i":7,"r":"unfini'
        )
        out = self._fn()(truncated)
        assert out == [
            {"i": 5, "r": "sole source J&A"},
            {"i": 12, "r": "PMR checklist"},
        ]

    def test_well_formed_full_array(self):
        good = '[{"i":3,"r":"matches keyword"}, {"i":1,"r":"title hit"}]'
        out = self._fn()(good)
        assert out == [
            {"i": 3, "r": "matches keyword"},
            {"i": 1, "r": "title hit"},
        ]

    def test_no_recoverable_entries_returns_empty(self):
        # Garbage with no recognizable {"i":N,"r":"..."} blocks.
        assert self._fn()("oops the model just said sorry") == []
        assert self._fn()("[") == []

    def test_handles_escaped_quotes_in_rationale(self):
        sample = r'[{"i":4,"r":"matches \"sole source\" J&A"}]'
        out = self._fn()(sample)
        assert out == [{"i": 4, "r": 'matches "sole source" J&A'}]

    def test_preserves_order(self):
        # Order is rank — must not shuffle.
        sample = '[{"i":99,"r":"first"}, {"i":1,"r":"second"}, {"i":50,"r":"third"}]'
        out = self._fn()(sample)
        assert [e["i"] for e in out] == [99, 1, 50]


class TestTeamsNotifierImport:
    """Triage #7: module-level singleton client is gone; per-call AsyncClient instead."""

    def test_no_get_client_function(self):
        # The fix removed the _get_client() helper that constructed and reused
        # the singleton AsyncClient. Checking for the absence of `_client` as
        # a module attribute is too brittle (other tests' fixtures used to
        # mutate `mod._client = None`, leaving the attribute behind). Checking
        # for `_get_client` is the right invariant: that's the API that
        # encoded the singleton pattern, and nothing should re-introduce it.
        from app import teams_notifier
        assert not hasattr(teams_notifier, "_get_client"), (
            "_get_client() should not exist — the per-call AsyncClient pattern "
            "creates fresh clients inline via `async with httpx.AsyncClient(...)`. "
            "If this assertion fails, the singleton helper has been re-introduced."
        )

    def test_close_notifier_client_is_noop(self):
        # Compatibility shim — older callers may still await it.
        import asyncio
        from app.teams_notifier import close_notifier_client
        result = asyncio.run(close_notifier_client())
        assert result is None

    def test_send_uses_async_with(self):
        # Sanity check that the source uses `async with httpx.AsyncClient` rather
        # than `httpx.AsyncClient(...)` bare-instantiation pattern.
        from pathlib import Path
        src = (
            Path(__file__).resolve().parents[1] / "app" / "teams_notifier.py"
        ).read_text(encoding="utf-8")
        assert "async with httpx.AsyncClient" in src, (
            "teams_notifier._send must use `async with httpx.AsyncClient(...)` so "
            "the client lifetime is bound to the calling event loop. The module-"
            "level singleton pattern triggered 'Event loop is closed' on the "
            "daily-summary scheduler path (triage 05-01 to 05-03)."
        )
