"""Tests for package, intake, FAR, docx-edit, and document generation tool handlers."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.tools.far_search import exec_search_far
from app.tools.docx_edit_tool import exec_edit_docx_document
from app.tools.intake_tools import exec_get_intake_status, exec_intake_workflow
from app.tools.package_document_tools import (
    exec_document_changelog_search,
    exec_get_latest_document,
    exec_manage_package,
)

TENANT = "test-tenant"
SESSION_ID = "test-tenant#standard#test-user#sess-001"


def _assert_keys(result: dict, *keys: str) -> None:
    for key in keys:
        assert key in result, f"Missing key '{key}' in {list(result.keys())}"


# ===========================================================================
# search_far
# ===========================================================================


class TestSearchFar:
    @patch("app.compliance_matrix.search_far")
    def test_returns_expected_schema(self, mock_search):
        mock_search.return_value = [
            {
                "part": "6",
                "section": "6.302",
                "title": "Justification",
                "summary": "J&A requirements",
                "applicability": "All",
                "s3_keys": [],
            }
        ]
        result = exec_search_far({"query": "sole source"}, TENANT)
        _assert_keys(result, "query", "parts_searched", "results_count", "clauses", "source", "note")
        assert result["query"] == "sole source"
        assert result["results_count"] == 1

    @patch("app.compliance_matrix.search_far")
    def test_empty_results_returns_fallback_clause(self, mock_search):
        mock_search.return_value = []
        result = exec_search_far({"query": "obscure query"}, TENANT)
        assert result["results_count"] == 1
        assert result["clauses"][0]["section"] == "1.102"

    @patch("app.compliance_matrix.search_far")
    def test_clauses_limited_to_15(self, mock_search):
        mock_search.return_value = [
            {"part": str(i), "section": f"{i}.1", "title": f"T{i}",
             "summary": "s", "applicability": "a", "s3_keys": []}
            for i in range(20)
        ]
        result = exec_search_far({"query": "all"}, TENANT)
        assert len(result["clauses"]) == 15

    @patch("app.compliance_matrix.search_far")
    def test_clauses_have_expected_keys(self, mock_search):
        """Frontend SearchResultPanel expects part, section, title, summary."""
        mock_search.return_value = [
            {"part": "1", "section": "1.1", "title": "T", "summary": "S",
             "applicability": "A", "s3_keys": []}
        ]
        result = exec_search_far({"query": "test"}, TENANT)
        clause = result["clauses"][0]
        _assert_keys(clause, "part", "section", "title", "summary")

    @patch("app.compliance_matrix.search_far")
    def test_parts_filter_passed_through(self, mock_search):
        mock_search.return_value = []
        result = exec_search_far({"query": "q", "parts": ["6", "12"]}, TENANT)
        assert result["parts_searched"] == ["6", "12"]
        mock_search.assert_called_once_with("q", ["6", "12"])


# ===========================================================================
# edit_docx_document
# ===========================================================================


class TestEditDocxDocument:
    @patch("app.document_ai_edit_service.edit_docx_document")
    def test_valid_edits_delegates_to_service(self, mock_edit):
        mock_edit.return_value = {
            "status": "success",
            "document_key": "doc.docx",
            "edits_applied": 2,
        }
        result = exec_edit_docx_document(
            {
                "document_key": "doc.docx",
                "edits": [
                    {"search_text": "old", "replacement_text": "new"},
                    {"search_text": "foo", "replacement_text": "bar"},
                ],
            },
            TENANT,
            SESSION_ID,
        )
        assert result["status"] == "success"
        mock_edit.assert_called_once()

    def test_missing_edits_and_checkbox_edits_returns_error(self):
        result = exec_edit_docx_document(
            {"document_key": "doc.docx"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_edits_not_array_returns_error(self):
        result = exec_edit_docx_document(
            {"document_key": "doc.docx", "edits": "not a list"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_edit_missing_search_text_returns_error(self):
        result = exec_edit_docx_document(
            {
                "document_key": "doc.docx",
                "edits": [{"replacement_text": "new"}],
            },
            TENANT,
            SESSION_ID,
        )
        assert "error" in result
        assert "search_text" in result["error"]

    def test_edit_item_not_dict_returns_error(self):
        result = exec_edit_docx_document(
            {"document_key": "doc.docx", "edits": ["not a dict"]}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_checkbox_edit_missing_label_returns_error(self):
        result = exec_edit_docx_document(
            {
                "document_key": "doc.docx",
                "checkbox_edits": [{"checked": True}],
            },
            TENANT,
            SESSION_ID,
        )
        assert "error" in result
        assert "label_text" in result["error"]

    def test_checkbox_edit_non_boolean_checked_returns_error(self):
        result = exec_edit_docx_document(
            {
                "document_key": "doc.docx",
                "checkbox_edits": [{"label_text": "Yes", "checked": "yes"}],
            },
            TENANT,
            SESSION_ID,
        )
        assert "error" in result
        assert "boolean" in result["error"]

    @patch("app.document_ai_edit_service.edit_docx_document")
    def test_valid_checkbox_edits(self, mock_edit):
        mock_edit.return_value = {"status": "success", "edits_applied": 1}
        result = exec_edit_docx_document(
            {
                "document_key": "doc.docx",
                "checkbox_edits": [{"label_text": "Approved", "checked": True}],
            },
            TENANT,
            SESSION_ID,
        )
        assert result["status"] == "success"


# ===========================================================================
# get_intake_status
# ===========================================================================


class TestGetIntakeStatus:
    @patch("app.tools.intake_tools.get_dynamodb")
    @patch("app.tools.intake_tools.get_s3")
    def test_returns_expected_schema_keys(self, mock_s3_fn, mock_ddb_fn):
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        mock_s3_fn.return_value = mock_s3

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_ddb_fn.return_value = mock_ddb

        result = exec_get_intake_status({}, TENANT, SESSION_ID)
        _assert_keys(
            result,
            "intake_id",
            "tenant_id",
            "completion_pct",
            "documents_completed",
            "documents_pending",
            "existing_files",
            "intake_records",
            "next_action",
        )

    @patch("app.tools.intake_tools.get_dynamodb")
    @patch("app.tools.intake_tools.get_s3")
    def test_s3_error_handled_gracefully(self, mock_s3_fn, mock_ddb_fn):
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "no"}}, "ListObjectsV2"
        )
        mock_s3_fn.return_value = mock_s3

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_ddb_fn.return_value = mock_ddb

        # Should not raise — handles S3 errors gracefully
        result = exec_get_intake_status({}, TENANT, SESSION_ID)
        assert "intake_id" in result

    @patch("app.tools.intake_tools.get_dynamodb")
    @patch("app.tools.intake_tools.get_s3")
    def test_dynamodb_error_handled_gracefully(self, mock_s3_fn, mock_ddb_fn):
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        mock_s3_fn.return_value = mock_s3

        mock_table = MagicMock()
        mock_table.query.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "no"}}, "Query"
        )
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_ddb_fn.return_value = mock_ddb

        result = exec_get_intake_status({}, TENANT, SESSION_ID)
        assert "intake_id" in result

    @patch("app.tools.intake_tools.get_dynamodb")
    @patch("app.tools.intake_tools.get_s3")
    def test_doc_type_detection_from_filenames(self, mock_s3_fn, mock_ddb_fn):
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "eagle/t/u/documents/sow_20260101.md",
                    "Size": 100,
                    "LastModified": datetime(2026, 1, 1),
                },
                {
                    "Key": "eagle/t/u/documents/igce_20260101.xlsx",
                    "Size": 200,
                    "LastModified": datetime(2026, 1, 1),
                },
            ]
        }
        mock_s3_fn.return_value = mock_s3

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_ddb_fn.return_value = mock_ddb

        result = exec_get_intake_status({}, TENANT, SESSION_ID)
        completed_types = {d["type"] for d in result["documents_completed"]}
        assert "sow" in completed_types
        assert "igce" in completed_types

    @patch("app.tools.intake_tools.get_dynamodb")
    @patch("app.tools.intake_tools.get_s3")
    def test_completion_pct_calculation(self, mock_s3_fn, mock_ddb_fn):
        mock_s3 = MagicMock()
        # All 5 required (non-conditional) docs present
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": f"eagle/t/u/documents/{dt}_20260101.md", "Size": 10,
                 "LastModified": datetime(2026, 1, 1)}
                for dt in ("sow", "igce", "market_research", "acquisition_plan", "cor_certification")
            ]
        }
        mock_s3_fn.return_value = mock_s3

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_ddb = MagicMock()
        mock_ddb.Table.return_value = mock_table
        mock_ddb_fn.return_value = mock_ddb

        result = exec_get_intake_status({}, TENANT, SESSION_ID)
        assert result["completion_pct"] == "100%"


# ===========================================================================
# intake_workflow
# ===========================================================================


class TestIntakeWorkflow:
    """Tests for exec_intake_workflow — all 5 actions."""

    @pytest.fixture(autouse=True)
    def _clean_workflow(self, tmp_path, monkeypatch):
        """Use tmp_path for workflow files to avoid cross-test pollution."""
        monkeypatch.setattr(
            "app.tools.intake_tools._workflow_file",
            lambda tid: str(tmp_path / f"wf_{tid}.json"),
        )

    def test_start_returns_expected_schema(self):
        result = exec_intake_workflow({"action": "start"}, TENANT)
        _assert_keys(result, "action", "intake_id", "current_stage", "next_actions")
        assert result["action"] == "started"
        assert result["current_stage"]["number"] == 1

    def test_start_output_matches_intake_workflow_panel_keys(self):
        """Frontend IntakeWorkflowPanel expects action and current_stage."""
        result = exec_intake_workflow({"action": "start"}, TENANT)
        _assert_keys(result, "action", "current_stage")
        _assert_keys(result["current_stage"], "number", "name", "description")

    def test_status_returns_progress_and_current_stage(self):
        exec_intake_workflow({"action": "start"}, TENANT)
        result = exec_intake_workflow({"action": "status"}, TENANT)
        _assert_keys(result, "intake_id", "status", "progress", "current_stage")

    def test_status_no_workflows_returns_hint(self):
        result = exec_intake_workflow({"action": "status"}, TENANT)
        assert "message" in result
        assert "start" in result["message"].lower() or "hint" in result

    def test_status_not_found_returns_error(self):
        result = exec_intake_workflow(
            {"action": "status", "intake_id": "EAGLE-nope-00000"}, TENANT
        )
        assert "error" in result

    def test_advance_returns_action_advanced(self):
        exec_intake_workflow({"action": "start"}, TENANT)
        result = exec_intake_workflow({"action": "advance"}, TENANT)
        _assert_keys(result, "action", "intake_id", "progress", "current_stage")
        assert result["action"] == "advanced"

    def test_advance_final_stage_returns_workflow_complete(self):
        exec_intake_workflow({"action": "start"}, TENANT)
        # Advance through all 4 stages
        for _ in range(3):
            exec_intake_workflow({"action": "advance"}, TENANT)
        result = exec_intake_workflow({"action": "advance"}, TENANT)
        assert result["action"] == "workflow_complete"

    def test_complete_returns_action_submitted(self):
        exec_intake_workflow({"action": "start"}, TENANT)
        result = exec_intake_workflow({"action": "complete"}, TENANT)
        _assert_keys(result, "action", "intake_id", "submitted_at", "status")
        assert result["action"] == "submitted"
        assert result["status"] == "submitted"

    def test_reset_specific_workflow(self):
        start_result = exec_intake_workflow({"action": "start"}, TENANT)
        intake_id = start_result["intake_id"]
        result = exec_intake_workflow(
            {"action": "reset", "intake_id": intake_id}, TENANT
        )
        assert result["action"] == "reset"

    def test_reset_all_workflows(self):
        exec_intake_workflow({"action": "start"}, TENANT)
        result = exec_intake_workflow({"action": "reset"}, TENANT)
        assert result["action"] == "reset"

    def test_unknown_action_returns_error(self):
        result = exec_intake_workflow({"action": "explode"}, TENANT)
        assert "error" in result
        assert "explode" in result["error"]
        _assert_keys(result, "valid_actions")


# ===========================================================================
# manage_package
# ===========================================================================

PACKAGE_ITEM = {
    "package_id": "pkg-001",
    "tenant_id": TENANT,
    "title": "Cloud Services Package",
    "requirement_type": "services",
    "status": "drafting",
    "required_documents": ["sow", "igce"],
    "completed_documents": [],
}


class TestManagePackage:
    @patch("app.tools.package_document_tools._backfill_completed_docs")
    @patch("app.package_store.create_package", return_value=PACKAGE_ITEM)
    def test_create_returns_package_with_id(self, mock_create, mock_backfill):
        result = exec_manage_package(
            {"operation": "create", "title": "Test"}, TENANT, SESSION_ID
        )
        assert "package_id" in result or "error" not in result
        mock_create.assert_called_once()

    @patch("app.package_store.get_package", return_value=PACKAGE_ITEM)
    def test_get_returns_package_data(self, mock_get):
        result = exec_manage_package(
            {"operation": "get", "package_id": "pkg-001"}, TENANT, SESSION_ID
        )
        assert result.get("package_id") == "pkg-001"

    def test_get_missing_package_id_returns_error(self):
        result = exec_manage_package(
            {"operation": "get"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.package_store.get_package", return_value=None)
    def test_get_not_found_returns_error(self, mock_get):
        result = exec_manage_package(
            {"operation": "get", "package_id": "nope"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.package_store.update_package", return_value=PACKAGE_ITEM)
    def test_update_returns_updated_package(self, mock_update):
        result = exec_manage_package(
            {"operation": "update", "package_id": "pkg-001", "title": "New Title"},
            TENANT,
            SESSION_ID,
        )
        assert "error" not in result

    def test_update_missing_package_id_returns_error(self):
        result = exec_manage_package(
            {"operation": "update", "title": "X"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_update_no_fields_returns_error(self):
        result = exec_manage_package(
            {"operation": "update", "package_id": "pkg-001"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.package_store.update_package", return_value=None)
    def test_update_not_found_returns_error(self, mock_update):
        result = exec_manage_package(
            {"operation": "update", "package_id": "nope", "title": "X"},
            TENANT,
            SESSION_ID,
        )
        assert "error" in result

    @patch("app.package_store.list_packages", return_value=[PACKAGE_ITEM])
    def test_list_returns_packages_and_count(self, mock_list):
        result = exec_manage_package(
            {"operation": "list"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "packages", "count")
        assert result["count"] == 1

    @patch(
        "app.package_store.delete_package",
        return_value={"title": "Deleted Package"},
    )
    def test_delete_returns_deleted_true(self, mock_del):
        result = exec_manage_package(
            {"operation": "delete", "package_id": "pkg-001"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "deleted", "package_id", "title")
        assert result["deleted"] is True

    def test_delete_missing_package_id_returns_error(self):
        result = exec_manage_package(
            {"operation": "delete"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.package_store.delete_package", return_value=None)
    def test_delete_not_found_returns_error(self, mock_del):
        result = exec_manage_package(
            {"operation": "delete", "package_id": "nope"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch(
        "app.package_store.get_package_checklist",
        return_value={"required_documents": ["sow"], "completed": []},
    )
    def test_checklist_returns_checklist_with_package_id(self, mock_cl):
        result = exec_manage_package(
            {"operation": "checklist", "package_id": "pkg-001"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "package_id", "required_documents")
        assert result["package_id"] == "pkg-001"

    def test_checklist_missing_package_id_returns_error(self):
        result = exec_manage_package(
            {"operation": "checklist"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.package_store.clone_package", return_value=PACKAGE_ITEM)
    def test_clone_returns_new_package(self, mock_clone):
        result = exec_manage_package(
            {"operation": "clone", "package_id": "pkg-001"}, TENANT, SESSION_ID
        )
        assert "error" not in result

    def test_clone_missing_package_id_returns_error(self):
        result = exec_manage_package(
            {"operation": "clone"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.package_store.clone_package", return_value=None)
    def test_clone_not_found_returns_error(self, mock_clone):
        result = exec_manage_package(
            {"operation": "clone", "package_id": "nope"}, TENANT, SESSION_ID
        )
        assert "error" in result

    @patch("app.export_store.list_exports", return_value=[{"export_id": "e1"}])
    def test_exports_returns_exports_and_count(self, mock_exports):
        result = exec_manage_package(
            {"operation": "exports", "package_id": "pkg-001"}, TENANT, SESSION_ID
        )
        _assert_keys(result, "exports", "count")
        assert result["count"] == 1

    def test_exports_missing_package_id_returns_error(self):
        result = exec_manage_package(
            {"operation": "exports"}, TENANT, SESSION_ID
        )
        assert "error" in result

    def test_unknown_operation_returns_error(self):
        result = exec_manage_package(
            {"operation": "nuke"}, TENANT, SESSION_ID
        )
        assert "error" in result
        assert "nuke" in result["error"]


# ===========================================================================
# document_changelog_search
# ===========================================================================


class TestDocumentChangelogSearch:
    @patch(
        "app.changelog_store.list_changelog_entries",
        return_value=[
            {
                "change_type": "create",
                "change_source": "agent_tool",
                "change_summary": "Created SOW",
                "doc_type": "sow",
                "version": 1,
                "actor_user_id": "test-user",
                "created_at": "2026-01-01T00:00:00",
            }
        ],
    )
    def test_returns_package_id_doc_type_count_entries(self, mock_list):
        result = exec_document_changelog_search(
            {"package_id": "pkg-001", "doc_type": "sow"}, TENANT
        )
        _assert_keys(result, "package_id", "doc_type", "count", "entries")
        assert result["package_id"] == "pkg-001"
        assert result["count"] == 1

    def test_missing_package_id_returns_error(self):
        result = exec_document_changelog_search({}, TENANT)
        assert "error" in result
        assert "package_id" in result["error"]

    @patch(
        "app.changelog_store.list_changelog_entries",
        return_value=[
            {
                "change_type": "create",
                "change_source": "agent",
                "change_summary": "Test",
                "doc_type": "sow",
                "version": 1,
                "actor_user_id": "u",
                "created_at": "2026-01-01",
            }
        ],
    )
    def test_entries_have_expected_keys(self, mock_list):
        result = exec_document_changelog_search(
            {"package_id": "pkg-001"}, TENANT
        )
        entry = result["entries"][0]
        _assert_keys(
            entry,
            "change_type",
            "change_source",
            "change_summary",
            "doc_type",
            "version",
            "actor_user_id",
            "created_at",
        )


# ===========================================================================
# get_latest_document
# ===========================================================================


class TestGetLatestDocument:
    @patch("app.changelog_store.list_changelog_entries", return_value=[])
    @patch(
        "app.package_document_store.get_document",
        return_value={
            "doc_type": "sow",
            "version": 2,
            "title": "SOW v2",
            "status": "draft",
            "created_at": "2026-01-01",
            "s3_key": "eagle/t/u/sow_v2.md",
        },
    )
    def test_returns_document_and_recent_changes(self, mock_doc, mock_cl):
        result = exec_get_latest_document(
            {"package_id": "pkg-001", "doc_type": "sow"}, TENANT
        )
        _assert_keys(result, "document", "recent_changes")
        _assert_keys(result["document"], "doc_type", "version", "title", "s3_key")

    def test_missing_params_returns_error(self):
        result = exec_get_latest_document({"package_id": "p"}, TENANT)
        assert "error" in result
        result2 = exec_get_latest_document({"doc_type": "sow"}, TENANT)
        assert "error" in result2

    @patch("app.changelog_store.list_changelog_entries", return_value=[])
    @patch("app.package_document_store.get_document", return_value=None)
    def test_document_not_found_returns_error(self, mock_doc, mock_cl):
        result = exec_get_latest_document(
            {"package_id": "pkg-001", "doc_type": "sow"}, TENANT
        )
        assert "error" in result


# ===========================================================================
# create_document (schema tests only — complex branching tested elsewhere)
# ===========================================================================


class TestCreateDocument:
    """Lightweight schema tests for exec_create_document.

    The full document pipeline is covered in test_document_pipeline.py.
    These tests focus on return schema, error paths, and JSON serializability.
    """

    @patch("app.tools.document_generation.get_s3")
    @patch("app.template_service.TemplateService")
    @patch("app.tools.document_generation._augment_document_data_from_context", return_value={})
    @patch("app.template_registry.normalize_field_names", side_effect=lambda d, _: d)
    def test_returns_expected_schema_keys(
        self, mock_norm, mock_aug, mock_ts_cls, mock_s3_fn
    ):
        # TemplateService.generate_document fails → falls back to markdown
        mock_ts = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "no template"
        mock_ts.generate_document.return_value = mock_result
        mock_ts_cls.return_value = mock_ts

        mock_s3 = MagicMock()
        mock_s3_fn.return_value = mock_s3

        from app.tools.document_generation import exec_create_document

        result = exec_create_document(
            {"doc_type": "sow", "title": "Test SOW", "data": {}},
            TENANT,
            SESSION_ID,
        )
        # Should have standard response keys
        _assert_keys(result, "document_type", "title", "status", "s3_key", "content")
        _assert_keys(result, "file_type", "source", "word_count", "generated_at", "note")

    def test_unknown_doc_type_returns_error(self):
        from app.tools.document_generation import exec_create_document

        result = exec_create_document(
            {"doc_type": "alien_artifact", "title": "X"}, TENANT, SESSION_ID
        )
        assert "error" in result
        assert "alien_artifact" in result["error"]

    @patch("app.tools.document_generation.get_s3")
    @patch("app.template_service.TemplateService")
    @patch("app.tools.document_generation._augment_document_data_from_context", return_value={})
    @patch("app.template_registry.normalize_field_names", side_effect=lambda d, _: d)
    def test_result_is_json_serializable(
        self, mock_norm, mock_aug, mock_ts_cls, mock_s3_fn
    ):
        mock_ts = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "no template"
        mock_ts.generate_document.return_value = mock_result
        mock_ts_cls.return_value = mock_ts
        mock_s3_fn.return_value = MagicMock()

        from app.tools.document_generation import exec_create_document

        result = exec_create_document(
            {"doc_type": "sow", "title": "Test", "data": {}},
            TENANT,
            SESSION_ID,
        )
        # Must survive the same serialization path as execute_tool
        raw = json.dumps(result, indent=2, default=str)
        parsed = json.loads(raw)
        assert isinstance(parsed, dict)

    @patch("app.tools.document_generation._update_document_content")
    def test_update_existing_key_delegates(self, mock_update):
        mock_update.return_value = {"status": "updated", "document_key": "k"}

        from app.tools.document_generation import exec_create_document

        result = exec_create_document(
            {"update_existing_key": "eagle/t/u/doc.md", "content": "new content"},
            TENANT,
            SESSION_ID,
        )
        mock_update.assert_called_once()
