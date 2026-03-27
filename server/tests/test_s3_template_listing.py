"""Unit tests for S3 template listing and inference functions.

Covers:
  - list_s3_templates: pagination, caching, refresh, phase filter, file-type guard
  - _infer_doc_type_from_filename: exact registry match, form match, fuzzy fallback, unknown
  - _infer_category_from_filename: pattern matches and no-match case
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest


# ── Cache reset fixture ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_cache():
    """Reset S3 template cache globals before every test."""
    import app.template_registry as tr

    tr._s3_template_cache.clear()
    tr._s3_cache_expiry = 0.0
    yield
    tr._s3_template_cache.clear()
    tr._s3_cache_expiry = 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_s3_object(key: str, size: int = 1024) -> Dict[str, Any]:
    """Return a minimal S3 object dict as returned by list_objects_v2."""
    return {
        "Key": key,
        "Size": size,
        "LastModified": datetime(2026, 1, 15, 12, 0, 0),
    }


def _build_paginator_mock(pages: List[List[Dict[str, Any]]]) -> MagicMock:
    """Build a mock paginator that yields the supplied pages."""
    page_dicts = [{"Contents": p} for p in pages]
    paginator = MagicMock()
    paginator.paginate.return_value = page_dicts
    return paginator


# ── TestListS3Templates ───────────────────────────────────────────────────────

class TestListS3Templates:
    """Tests for list_s3_templates()."""

    def _patch_s3(self, paginator: MagicMock) -> MagicMock:
        """Return a mock boto3 S3 client backed by *paginator*."""
        client = MagicMock()
        client.get_paginator.return_value = paginator
        return client

    def test_lists_all_templates_from_s3(self):
        """Returns one template entry per valid document file found in S3."""
        from app.template_registry import (
            TEMPLATE_BUCKET,
            TEMPLATE_PREFIX,
            list_s3_templates,
        )

        prefix = TEMPLATE_PREFIX
        objects = [
            _make_s3_object(f"{prefix}/statement-of-work-template-eagle-v2.docx"),
            _make_s3_object(f"{prefix}/01.D_IGCE_for_Commercial_Organizations.xlsx"),
        ]
        paginator = _build_paginator_mock([objects])

        with patch("app.template_registry.get_s3") as mock_get_s3:
            mock_get_s3.return_value = self._patch_s3(paginator)
            results = list_s3_templates()

        assert len(results) == 2
        filenames = {t["filename"] for t in results}
        assert "statement-of-work-template-eagle-v2.docx" in filenames
        assert "01.D_IGCE_for_Commercial_Organizations.xlsx" in filenames

        # Check structure of a result entry
        sow = next(t for t in results if "statement-of-work" in t["filename"])
        assert sow["s3_key"] == f"{prefix}/statement-of-work-template-eagle-v2.docx"
        assert sow["file_type"] == "docx"
        assert sow["size_bytes"] == 1024
        assert sow["doc_type"] == "sow"
        assert sow["registered"] is True

    def test_caches_results_for_5_minutes(self):
        """Calling list_s3_templates twice without refresh hits S3 only once."""
        from app.template_registry import TEMPLATE_PREFIX, list_s3_templates

        prefix = TEMPLATE_PREFIX
        objects = [_make_s3_object(f"{prefix}/statement-of-work-template-eagle-v2.docx")]
        paginator = _build_paginator_mock([objects])

        with patch("app.template_registry.get_s3") as mock_get_s3:
            mock_get_s3.return_value = self._patch_s3(paginator)

            list_s3_templates()
            list_s3_templates()

            # get_s3 should have been called only once (cached)
            assert mock_get_s3.call_count == 1

    def test_refresh_bypasses_cache(self):
        """Calling list_s3_templates(refresh=True) re-fetches from S3."""
        from app.template_registry import TEMPLATE_PREFIX, list_s3_templates

        prefix = TEMPLATE_PREFIX
        objects = [_make_s3_object(f"{prefix}/statement-of-work-template-eagle-v2.docx")]
        paginator = _build_paginator_mock([objects])

        with patch("app.template_registry.get_s3") as mock_get_s3:
            mock_get_s3.return_value = self._patch_s3(paginator)

            list_s3_templates()
            list_s3_templates(refresh=True)

            # Second call with refresh=True should re-fetch
            assert mock_get_s3.call_count == 2

    def test_phase_filter_works(self):
        """phase_filter='planning' returns only templates whose category phase is 'planning'."""
        from app.template_registry import TEMPLATE_PREFIX, list_s3_templates

        prefix = TEMPLATE_PREFIX
        # SOW → planning phase (registered)
        # Quotation Abstract → solicitation phase (form template, inferred)
        objects = [
            _make_s3_object(f"{prefix}/statement-of-work-template-eagle-v2.docx"),
            _make_s3_object(f"{prefix}/Quotation Abstract.docx"),
        ]
        paginator = _build_paginator_mock([objects])

        with patch("app.template_registry.get_s3") as mock_get_s3:
            mock_get_s3.return_value = self._patch_s3(paginator)
            results = list_s3_templates(phase_filter="planning")

        # Only the SOW (planning phase) should survive the filter
        assert all(t["category"]["phase"] == "planning" for t in results), (
            f"Got non-planning templates: {[t['filename'] for t in results if t.get('category', {}).get('phase') != 'planning']}"
        )
        filenames = [t["filename"] for t in results]
        assert "statement-of-work-template-eagle-v2.docx" in filenames

    def test_skips_non_document_files(self):
        """Files with non-document extensions (e.g., .txt) are excluded from results."""
        from app.template_registry import TEMPLATE_PREFIX, list_s3_templates

        prefix = TEMPLATE_PREFIX
        objects = [
            _make_s3_object(f"{prefix}/statement-of-work-template-eagle-v2.docx"),
            _make_s3_object(f"{prefix}/readme.txt"),
            _make_s3_object(f"{prefix}/HHS_AP_Structure_Guide.txt"),
        ]
        paginator = _build_paginator_mock([objects])

        with patch("app.template_registry.get_s3") as mock_get_s3:
            mock_get_s3.return_value = self._patch_s3(paginator)
            results = list_s3_templates()

        filenames = [t["filename"] for t in results]
        assert "readme.txt" not in filenames
        assert "HHS_AP_Structure_Guide.txt" not in filenames
        assert "statement-of-work-template-eagle-v2.docx" in filenames


# ── TestInferDocTypeFromFilename ───────────────────────────────────────────────

class TestInferDocTypeFromFilename:
    """Tests for _infer_doc_type_from_filename()."""

    def test_exact_match_registered_template(self):
        """Primary s3_filename match returns the correct doc_type."""
        from app.template_registry import _infer_doc_type_from_filename

        result = _infer_doc_type_from_filename("statement-of-work-template-eagle-v2.docx")
        assert result == "sow"

    def test_exact_match_form_template(self):
        """Filename that matches a FORM_TEMPLATES entry returns the form doc_type."""
        from app.template_registry import _infer_doc_type_from_filename

        result = _infer_doc_type_from_filename("Quotation Abstract.docx")
        assert result == "quotation_abstract"

    def test_fallback_to_classify_document(self):
        """Unregistered filenames fall back to classify_document in the classification service.

        _infer_doc_type_from_filename imports classify_document at call time via a
        relative import from document_classification_service, so the patch target is
        the canonical location: app.document_classification_service.classify_document.
        """
        from app.template_registry import _infer_doc_type_from_filename

        mock_result = MagicMock()
        mock_result.doc_type = "sow"
        mock_result.confidence = 0.85

        with patch(
            "app.document_classification_service.classify_document",
            return_value=mock_result,
        ):
            result = _infer_doc_type_from_filename("SOW_Project_Alpha.docx")

        assert result == "sow"

    def test_unknown_filename_returns_none(self):
        """Filenames that fail exact matching and return low-confidence classification yield None.

        Patches the same canonical location as test_fallback_to_classify_document.
        """
        from app.template_registry import _infer_doc_type_from_filename

        mock_result = MagicMock()
        mock_result.doc_type = "unknown"
        mock_result.confidence = 0.2

        with patch(
            "app.document_classification_service.classify_document",
            return_value=mock_result,
        ):
            result = _infer_doc_type_from_filename("random_file_xyz.docx")

        assert result is None


# ── TestInferCategoryFromFilename ──────────────────────────────────────────────

class TestInferCategoryFromFilename:
    """Tests for _infer_category_from_filename()."""

    def test_justification_pattern(self):
        """Filenames matching the j&a pattern return planning/sole_source category."""
        from app.template_registry import _infer_category_from_filename

        result = _infer_category_from_filename("j&a_template.docx")
        assert result is not None
        assert result["phase"] == "planning"
        assert result["use_case"] == "sole_source"

    def test_acquisition_plan_pattern(self):
        """Filenames matching the acquisition plan pattern return planning phase."""
        from app.template_registry import _infer_category_from_filename

        result = _infer_category_from_filename("acquisition_plan_v2.docx")
        assert result is not None
        assert result["phase"] == "planning"

    def test_unknown_pattern_returns_none(self):
        """Filenames that match no known pattern return None."""
        from app.template_registry import _infer_category_from_filename

        result = _infer_category_from_filename("random_notes.txt")
        assert result is None
