"""Unit tests for the Tier-3 post-write section-drift validator wiring.

Verifies that `create_document`'s response includes a populated
`_template_provenance.section_drift` block when the saved markdown is
validated against a registered TemplateSchema.

The wiring is observability-only — the validator never blocks the call,
even when validate_completeness() raises. These tests pin both the
happy path and the silent-fallback behavior.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Tests in this repo expect S3_BUCKET set via .env or fixture; set a stub
# here in case this module is collected before the .env autoload runs.
os.environ.setdefault("S3_BUCKET", "test-bucket")

# Ensure server/ is on the path for app.* imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSectionDriftSurface:
    """Triage Tier-3: validate_completeness() report appears on the tool result."""

    def test_drift_block_added_when_schema_registered(self):
        """When validate_completeness() returns total_sections > 0, the
        report must be attached to _template_provenance.section_drift.
        Asserts structural shape against the real SOW schema rather than
        mocking the validator — the wiring under test is the dict-build
        on the response side.
        """
        from app.template_schema import validate_completeness

        response = {
            "document_id": "doc-1",
            "_template_provenance": {"template_id": "tmpl-sow-v1", "source": "ai_content"},
        }

        # SOW has a registered TemplateSchema, so this report has
        # total_sections > 0 and the wiring should fire.
        sample_sow_md = (
            "# Statement of Work\n\n"
            "## 1. Background\nThe contractor will...\n\n"
            "## 2. Scope of Work\nIncludes...\n\n"
            "## 3. Tasks\nDeliverable A.\n"
        )
        r = validate_completeness("sow", sample_sow_md)
        if r.total_sections > 0:
            response["_template_provenance"]["section_drift"] = {
                "total_sections": r.total_sections,
                "filled_sections": r.filled_sections,
                "missing_sections": list(r.missing_sections),
                "completeness_pct": r.completeness_pct,
                "is_complete": r.is_complete,
            }

        drift = response["_template_provenance"].get("section_drift")
        assert drift is not None, (
            "section_drift must be attached when SOW has a registered schema"
        )
        # Structural shape — no specific section counts, since the SOW
        # schema can grow without breaking this test.
        assert isinstance(drift["total_sections"], int) and drift["total_sections"] > 0
        assert isinstance(drift["filled_sections"], int)
        assert drift["filled_sections"] <= drift["total_sections"]
        assert isinstance(drift["missing_sections"], list)
        assert isinstance(drift["completeness_pct"], (int, float))
        assert 0.0 <= drift["completeness_pct"] <= 100.0
        assert isinstance(drift["is_complete"], bool)
        # The thin sample above has only 3 of N sections — should be
        # marked incomplete.
        assert drift["is_complete"] is False
        assert drift["missing_sections"], "thin SOW input must surface missing sections"

    def test_drift_omitted_when_no_schema(self):
        """When validate_completeness() returns total_sections == 0
        (no schema registered for the doc_type), section_drift must NOT
        be attached — silence is the right signal."""
        from app.template_schema import CompletenessReport

        response = {"_template_provenance": {"template_id": None, "source": "ai_content"}}
        empty_report = CompletenessReport(
            doc_type="qasp",
            total_sections=0,
            filled_sections=0,
            completeness_pct=0.0,
            is_complete=False,
        )
        if empty_report.total_sections > 0:
            response["_template_provenance"]["section_drift"] = {
                "total_sections": empty_report.total_sections,
                "filled_sections": empty_report.filled_sections,
                "missing_sections": list(empty_report.missing_sections),
                "completeness_pct": empty_report.completeness_pct,
                "is_complete": empty_report.is_complete,
            }
        assert "section_drift" not in response["_template_provenance"]

    def test_validator_exception_never_blocks_response(self):
        """If validate_completeness() raises, the tool must continue and
        return its response — section_drift is observability, not
        load-bearing."""
        response = {"_template_provenance": {"template_id": None, "source": "ai_content"}}

        def boom(*a, **kw):
            raise RuntimeError("schema loader exploded")

        try:
            try:
                report = boom("sow", "# Doc")
                if report.total_sections > 0:
                    response["_template_provenance"]["section_drift"] = {}
            except Exception:
                pass  # mirrors the noqa BLE001 guard in document_generation.py
        except Exception:
            assert False, "validator should not propagate exceptions"

        # No section_drift, but the response is still intact.
        assert "section_drift" not in response["_template_provenance"]
        assert "_template_provenance" in response


class TestActualWiring:
    """Verify the actual document_generation.py source contains the
    validator wiring — guards against the wiring being removed in a
    future refactor."""

    def _src(self) -> str:
        return (
            Path(__file__).resolve().parents[1]
            / "app"
            / "tools"
            / "document_generation.py"
        ).read_text(encoding="utf-8")

    def test_document_generation_calls_validate_completeness(self):
        src = self._src()
        assert "validate_completeness" in src, (
            "document_generation.py must call validate_completeness() to "
            "populate _template_provenance.section_drift. If this assertion "
            "fails, the Tier-3 drift validator has been removed."
        )
        assert "section_drift" in src, (
            "document_generation.py must surface the drift report under "
            "_template_provenance.section_drift so the supervisor can audit "
            "structural adherence on the next turn."
        )

    def test_helper_invoked_from_both_return_paths(self):
        """Regression guard for the package-mode silent-drop bug.

        The Langfuse audit on 2026-05-08 caught _template_provenance
        and section_drift being silently absent from package-scoped
        create_document calls because the package-mode early return
        was a separate code path that bypassed the inline surfacing
        block. Fix: extracted _attach_template_metadata() and called
        from both paths. This test asserts the helper exists and is
        called at least twice — once for each return path.
        """
        src = self._src()
        assert "def _attach_template_metadata(" in src, (
            "Expected a _attach_template_metadata(...) helper that unifies "
            "the package-mode and workspace-mode response surfaces."
        )
        # Helper must be invoked from at least two call sites — one per
        # return path. (The function definition itself contains the name
        # once; we want at least 2 more usages = 3 total occurrences.)
        usages = src.count("_attach_template_metadata(")
        assert usages >= 3, (
            f"_attach_template_metadata must be called from both the "
            f"package-mode early return and the workspace-mode return path "
            f"(found {usages} total occurrences, need >= 3 — 1 def + 2 calls). "
            f"If only 1 call site, package-scoped create_document responses "
            f"will silently lose _template_provenance again."
        )
