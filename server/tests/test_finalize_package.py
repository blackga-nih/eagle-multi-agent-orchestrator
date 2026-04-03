"""Tests for finalize_package / validate_package_completeness (Feature 5)."""
import pytest
from unittest.mock import patch, MagicMock


class TestValidatePackageCompleteness:
    """Test validate_package_completeness in package_store."""

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.get_package")
    def test_all_docs_present_and_final_returns_ready_true(self, mock_get, mock_list):
        """When all required docs are present and finalized, ready=True."""
        from app.package_store import validate_package_completeness

        mock_get.return_value = {
            "package_id": "PKG-0001",
            "required_documents": ["sow", "igce"],
            "completed_documents": ["sow", "igce"],
            "estimated_value": "500000",
        }
        mock_list.return_value = [
            {"doc_type": "sow", "status": "final", "content": "# SOW\nContent"},
            {"doc_type": "igce", "status": "final", "content": "# IGCE\nContent"},
        ]

        result = validate_package_completeness("tenant", "PKG-0001")
        assert result["ready"] is True
        assert result["missing_documents"] == []
        assert result["draft_documents"] == []
        assert result["unfilled_templates"] == []

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.get_package")
    def test_missing_documents_detected(self, mock_get, mock_list):
        """Missing documents should be reported."""
        from app.package_store import validate_package_completeness

        mock_get.return_value = {
            "package_id": "PKG-0001",
            "required_documents": ["sow", "igce", "market_research"],
            "completed_documents": ["sow"],
            "estimated_value": "500000",
        }
        mock_list.return_value = [
            {"doc_type": "sow", "status": "final", "content": "# SOW"},
        ]

        result = validate_package_completeness("tenant", "PKG-0001")
        assert result["ready"] is False
        assert "igce" in result["missing_documents"]
        assert "market_research" in result["missing_documents"]

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.get_package")
    def test_draft_documents_detected(self, mock_get, mock_list):
        """Documents still in draft status should be flagged."""
        from app.package_store import validate_package_completeness

        mock_get.return_value = {
            "package_id": "PKG-0001",
            "required_documents": ["sow", "igce"],
            "completed_documents": ["sow", "igce"],
            "estimated_value": "500000",
        }
        mock_list.return_value = [
            {"doc_type": "sow", "status": "final", "content": "# SOW"},
            {"doc_type": "igce", "status": "draft", "content": "# IGCE Draft"},
        ]

        result = validate_package_completeness("tenant", "PKG-0001")
        assert result["ready"] is False
        assert "igce" in result["draft_documents"]

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.get_package")
    def test_unfilled_template_markers_detected(self, mock_get, mock_list):
        """Documents with {{PLACEHOLDER}} markers should be flagged."""
        from app.package_store import validate_package_completeness

        mock_get.return_value = {
            "package_id": "PKG-0001",
            "required_documents": ["sow"],
            "completed_documents": ["sow"],
            "estimated_value": "500000",
        }
        mock_list.return_value = [
            {"doc_type": "sow", "status": "final", "content": "# SOW\n\n{{PROJECT_NAME}} description for {{AGENCY_NAME}}"},
        ]

        result = validate_package_completeness("tenant", "PKG-0001")
        assert result["ready"] is False
        assert len(result["unfilled_templates"]) == 1
        assert result["unfilled_templates"][0]["doc_type"] == "sow"
        assert "{{PROJECT_NAME}}" in result["unfilled_templates"][0]["markers"]

    @patch("app.package_document_store.list_package_documents")
    @patch("app.package_store.get_package")
    def test_compliance_warnings_included(self, mock_get, mock_list):
        """When method/type available, compliance warnings should be included."""
        from app.package_store import validate_package_completeness

        mock_get.return_value = {
            "package_id": "PKG-0001",
            "required_documents": ["sow"],
            "completed_documents": ["sow"],
            "estimated_value": "500000",
            "acquisition_method": "negotiated",
            "contract_type": "tm",
            "flags": {"is_services": True},
        }
        mock_list.return_value = [
            {"doc_type": "sow", "status": "final", "content": "# SOW\nContent"},
        ]

        result = validate_package_completeness("tenant", "PKG-0001")
        # T&M contracts should trigger warnings
        assert len(result["compliance_warnings"]) > 0

    def test_package_not_found_returns_error(self):
        """Non-existent package should return error dict."""
        from app.package_store import validate_package_completeness

        with patch("app.package_store.get_package", return_value=None):
            result = validate_package_completeness("tenant", "PKG-NONE")
            assert result["ready"] is False
            assert "error" in result


class TestExecFinalizePackage:
    """Test the _exec_finalize_package tool handler."""

    @patch("app.package_store.validate_package_completeness")
    @patch("app.package_store.submit_package")
    def test_auto_submit_submits_when_ready(self, mock_submit, mock_validate):
        """auto_submit=True should call submit_package when ready."""
        from app.tools.package_document_tools import exec_finalize_package as _exec_finalize_package

        mock_validate.return_value = {
            "ready": True,
            "missing_documents": [],
            "draft_documents": [],
            "unfilled_templates": [],
            "compliance_warnings": [],
            "recommendation": "Package is complete.",
            "total_required": 2,
            "total_completed": 2,
        }
        mock_submit.return_value = {"status": "review"}

        result = _exec_finalize_package(
            {"package_id": "PKG-0001", "auto_submit": True},
            "tenant",
        )
        assert result["submitted"] is True
        assert result["status"] == "review"
        mock_submit.assert_called_once_with("tenant", "PKG-0001")

    @patch("app.package_store.validate_package_completeness")
    @patch("app.package_store.submit_package")
    def test_auto_submit_skips_when_not_ready(self, mock_submit, mock_validate):
        """auto_submit=True should NOT submit when package is not ready."""
        from app.tools.package_document_tools import exec_finalize_package as _exec_finalize_package

        mock_validate.return_value = {
            "ready": False,
            "missing_documents": ["igce"],
            "draft_documents": [],
            "unfilled_templates": [],
            "compliance_warnings": [],
            "recommendation": "1 missing document.",
            "total_required": 2,
            "total_completed": 1,
        }

        result = _exec_finalize_package(
            {"package_id": "PKG-0001", "auto_submit": True},
            "tenant",
        )
        assert result["ready"] is False
        mock_submit.assert_not_called()

    def test_missing_package_id_returns_error(self):
        """Missing package_id param should return error."""
        from app.tools.package_document_tools import exec_finalize_package as _exec_finalize_package

        result = _exec_finalize_package({}, "tenant")
        assert "error" in result
