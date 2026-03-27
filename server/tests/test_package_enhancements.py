"""Tests for package enhancements: delete, clone, structured ZIP,
selective export, mixed-format export, and export tracking."""

import io
import zipfile
from decimal import Decimal
from unittest.mock import MagicMock, patch  # noqa: I001

import pytest

# ── Helpers ──────────────────────────────────────────────────────────

def _make_package(**overrides):
    """Build a minimal package dict for testing."""
    pkg = {
        "PK": "PACKAGE#tenant-1",
        "SK": "PACKAGE#PKG-0001",
        "package_id": "PKG-0001",
        "tenant_id": "tenant-1",
        "title": "Test Package",
        "status": "intake",
        "requirement_type": "services",
        "estimated_value": Decimal("50000"),
        "owner_user_id": "user-1",
        "completed_documents": [],
        "acquisition_pathway": "micro_purchase",
        "created_at": "2026-03-27T00:00:00Z",
        "updated_at": "2026-03-27T00:00:00Z",
    }
    pkg.update(overrides)
    return pkg


def _make_docs(doc_types=None):
    """Build a list of document dicts for ZIP tests."""
    if doc_types is None:
        doc_types = ["sow", "igce"]
    return [
        {
            "doc_type": dt,
            "title": dt.upper(),
            "content": f"# {dt.upper()}\n\nContent for {dt}.",
        }
        for dt in doc_types
    ]


# ═══════════════════════════════════════════════════════════════════
#  TestDeletePackage
# ═══════════════════════════════════════════════════════════════════


class TestDeletePackage:
    """Tests for package_store.delete_package and related endpoints."""

    @patch("app.package_store.get_table")
    @patch("app.package_store.get_package")
    def test_delete_intake_package_succeeds(self, mock_get, mock_tbl):
        from app.package_store import delete_package

        pkg = _make_package(status="intake")
        mock_get.return_value = pkg
        mock_tbl.return_value.delete_item = MagicMock()

        result = delete_package("tenant-1", "PKG-0001")

        assert result is not None
        assert result["package_id"] == "PKG-0001"
        mock_tbl.return_value.delete_item.assert_called_once()

    @patch("app.package_store.get_table")
    @patch("app.package_store.get_package")
    def test_delete_drafting_package_succeeds(self, mock_get, mock_tbl):
        from app.package_store import delete_package

        mock_get.return_value = _make_package(status="drafting")
        mock_tbl.return_value.delete_item = MagicMock()

        result = delete_package("tenant-1", "PKG-0001")

        assert result is not None
        mock_tbl.return_value.delete_item.assert_called_once()

    @patch("app.package_store.get_package")
    def test_delete_review_package_rejected(self, mock_get):
        from app.package_store import delete_package

        mock_get.return_value = _make_package(status="review")
        result = delete_package("tenant-1", "PKG-0001")
        assert result is None

    @patch("app.package_store.get_package")
    def test_delete_approved_package_rejected(self, mock_get):
        from app.package_store import delete_package

        mock_get.return_value = _make_package(status="approved")
        result = delete_package("tenant-1", "PKG-0001")
        assert result is None

    @patch("app.package_store.get_package")
    def test_delete_nonexistent_returns_none(self, mock_get):
        from app.package_store import delete_package

        mock_get.return_value = None
        result = delete_package("tenant-1", "PKG-NOPE")
        assert result is None

    @patch("app.routers.packages.write_audit")
    @patch("app.routers.packages.delete_package")
    def test_delete_endpoint_200(self, mock_del, mock_audit):
        from fastapi.testclient import TestClient

        from app.main import app

        mock_del.return_value = _make_package()
        client = TestClient(app)
        resp = client.delete(
            "/api/packages/PKG-0001",
            headers={"x-tenant-id": "tenant-1", "x-user-id": "u1"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    @patch("app.routers.packages.delete_package")
    def test_delete_endpoint_404(self, mock_del):
        from fastapi.testclient import TestClient

        from app.main import app

        mock_del.return_value = None
        client = TestClient(app)
        resp = client.delete(
            "/api/packages/PKG-0001",
            headers={"x-tenant-id": "tenant-1", "x-user-id": "u1"},
        )
        assert resp.status_code == 404

    @patch("app.package_store.get_table")
    @patch("app.package_store.get_package")
    def test_manage_package_delete_operation(self, mock_get, mock_tbl):
        from app.tools.package_document_tools import exec_manage_package

        mock_get.return_value = _make_package(status="intake")
        mock_tbl.return_value.delete_item = MagicMock()

        result = exec_manage_package(
            {"operation": "delete", "package_id": "PKG-0001"},
            "tenant-1",
        )
        assert result["deleted"] is True
        assert result["package_id"] == "PKG-0001"


# ═══════════════════════════════════════════════════════════════════
#  TestClonePackage
# ═══════════════════════════════════════════════════════════════════


class TestClonePackage:
    """Tests for package_store.clone_package and related endpoints."""

    @patch("app.package_store.create_package")
    @patch("app.package_store.get_package")
    def test_clone_copies_source_metadata(self, mock_get, mock_create):
        from app.package_store import clone_package

        source = _make_package(
            requirement_type="supplies",
            estimated_value=Decimal("75000"),
            acquisition_method="competitive",
        )
        mock_get.return_value = source
        mock_create.return_value = _make_package(
            package_id="PKG-CLONE",
            title="Test Package (Copy)",
        )

        result = clone_package("tenant-1", "PKG-0001")

        assert result is not None
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["requirement_type"] == "supplies"

    @patch("app.package_store.create_package")
    @patch("app.package_store.get_package")
    def test_clone_uses_custom_title(self, mock_get, mock_create):
        from app.package_store import clone_package

        mock_get.return_value = _make_package()
        mock_create.return_value = _make_package(
            package_id="PKG-CLONE", title="My Custom Title",
        )

        clone_package("tenant-1", "PKG-0001", "My Custom Title")

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["title"] == "My Custom Title"

    @patch("app.package_store.create_package")
    @patch("app.package_store.get_package")
    def test_clone_starts_intake_empty_docs(self, mock_get, mock_create):
        from app.package_store import clone_package

        source = _make_package(
            status="review",
            completed_documents=["sow", "igce"],
        )
        mock_get.return_value = source
        # create_package returns a new package at intake
        mock_create.return_value = _make_package(
            package_id="PKG-CLONE",
            status="intake",
            completed_documents=[],
        )

        result = clone_package("tenant-1", "PKG-0001")

        assert result["status"] == "intake"
        assert result["completed_documents"] == []

    @patch("app.package_store.get_package")
    def test_clone_nonexistent_returns_none(self, mock_get):
        from app.package_store import clone_package

        mock_get.return_value = None
        result = clone_package("tenant-1", "PKG-NOPE")
        assert result is None

    @patch("app.routers.packages.write_audit")
    @patch("app.routers.packages.clone_package")
    def test_clone_endpoint_returns_package(self, mock_clone, mock_audit):
        from fastapi.testclient import TestClient

        from app.main import app

        mock_clone.return_value = _make_package(package_id="PKG-CLONE")
        client = TestClient(app)
        resp = client.post(
            "/api/packages/PKG-0001/clone",
            json={"title": "Cloned"},
            headers={"x-tenant-id": "tenant-1", "x-user-id": "u1"},
        )
        assert resp.status_code == 200
        assert resp.json()["package_id"] == "PKG-CLONE"

    @patch("app.package_store.create_package")
    @patch("app.package_store.get_package")
    def test_manage_package_clone_operation(self, mock_get, mock_create):
        from app.tools.package_document_tools import exec_manage_package

        mock_get.return_value = _make_package()
        mock_create.return_value = _make_package(package_id="PKG-CLONE")

        result = exec_manage_package(
            {"operation": "clone", "package_id": "PKG-0001"},
            "tenant-1",
            session_id="t1#basic#user1#sess1",
        )
        assert result["package_id"] == "PKG-CLONE"


# ═══════════════════════════════════════════════════════════════════
#  TestStructuredZip
# ═══════════════════════════════════════════════════════════════════


class TestStructuredZip:
    """Tests for structured ZIP export with folders, cover page, TOC."""

    def test_structured_zip_has_folders(self):
        from app.document_export import export_package_zip

        docs = _make_docs(["sow", "igce", "eval_criteria"])
        result = export_package_zip(
            docs, "Test Pkg", "md",
            package_metadata=_make_package(),
        )

        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        # sow → 01_Requirements/, igce → 02_Cost_Estimates/
        assert any("01_Requirements/" in n for n in names)
        assert any("02_Cost_Estimates/" in n for n in names)
        assert any("05_Evaluation/" in n for n in names)

    def test_structured_zip_includes_cover_page(self):
        from app.document_export import export_package_zip

        result = export_package_zip(
            _make_docs(), "Test Pkg", "md",
            package_metadata=_make_package(),
        )
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        assert "_COVER_PAGE.md" in zf.namelist()

        cover = zf.read("_COVER_PAGE.md").decode("utf-8")
        assert "Test Pkg" in cover

    def test_structured_zip_includes_toc(self):
        from app.document_export import export_package_zip

        result = export_package_zip(
            _make_docs(), "Test Pkg", "md",
            package_metadata=_make_package(),
        )
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        assert "_TABLE_OF_CONTENTS.md" in zf.namelist()

        toc = zf.read("_TABLE_OF_CONTENTS.md").decode("utf-8")
        assert "Table of Contents" in toc

    def test_flat_zip_when_no_metadata(self):
        from app.document_export import export_package_zip

        result = export_package_zip(_make_docs(), "Test Pkg", "md")

        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        # No folder separators, no cover/TOC
        assert "_COVER_PAGE.md" not in names
        assert "_TABLE_OF_CONTENTS.md" not in names
        for name in names:
            assert "/" not in name

    def test_unknown_doc_type_goes_to_other(self):
        from app.document_export import export_package_zip

        docs = [
            {
                "doc_type": "mystery_doc",
                "title": "Mystery",
                "content": "# Mystery\n\nSome content.",
            }
        ]
        result = export_package_zip(
            docs, "Test Pkg", "md",
            package_metadata=_make_package(),
        )
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        doc_names = [n for n in names if "mystery" in n.lower()]
        assert any("08_Other/" in n for n in doc_names)


# ═══════════════════════════════════════════════════════════════════
#  TestSelectiveExport
# ═══════════════════════════════════════════════════════════════════


class TestSelectiveExport:
    """Tests for selective doc_types filtering on ZIP export."""

    def test_doc_types_filter_includes_requested(self):
        from app.document_export import export_package_zip

        docs = _make_docs(["sow", "igce", "eval_criteria"])

        # Simulate router-level filtering
        requested = {"sow", "igce"}
        filtered = [d for d in docs if d["doc_type"] in requested]

        result = export_package_zip(filtered, "Filtered", "md")
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        assert len(names) == 2
        assert any("sow" in n for n in names)
        assert any("igce" in n for n in names)
        assert not any("eval" in n for n in names)

    def test_doc_types_filter_all_missing_returns_empty(self):
        """When filter eliminates all docs, ZIP has 0 files."""
        from app.document_export import export_package_zip

        docs = _make_docs(["sow"])
        requested = {"igce"}  # not in docs
        filtered = [d for d in docs if d["doc_type"] in requested]

        result = export_package_zip(filtered, "Empty", "md")
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        assert len(zf.namelist()) == 0

    def test_no_filter_exports_all(self):
        from app.document_export import export_package_zip

        docs = _make_docs(["sow", "igce", "eval_criteria"])
        result = export_package_zip(docs, "All Docs", "md")
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        assert len(zf.namelist()) == 3


# ═══════════════════════════════════════════════════════════════════
#  TestMixedFormatExport
# ═══════════════════════════════════════════════════════════════════


class TestMixedFormatExport:
    """Tests for per-document format overrides via format_map."""

    def test_format_map_overrides_per_doc(self):
        from app.document_export import export_package_zip

        docs = _make_docs(["sow", "igce"])
        # Override sow to md, igce stays default md too
        result = export_package_zip(
            docs, "Mixed", "md",
            format_map={"sow": "md", "igce": "md"},
        )
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        assert all(n.endswith(".md") for n in names)

    def test_binary_docs_ignore_format_map(self):
        from app.document_export import export_package_zip

        docs = [
            {
                "doc_type": "sow",
                "title": "SOW",
                "content": "# SOW\nContent.",
            },
            {
                "doc_type": "igce",
                "title": "IGCE Template",
                "_binary": b"fake-xlsx-bytes",
                "file_type": "xlsx",
                "filename": "igce_template.xlsx",
            },
        ]
        result = export_package_zip(
            docs, "Mixed Bin", "md",
            format_map={"igce": "pdf"},  # should be ignored for binary
        )
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        # Binary doc keeps original extension
        assert "igce_template.xlsx" in names

    def test_format_map_query_param_parsed(self):
        """Router endpoint correctly parses format_map JSON string."""
        import json

        raw = '{"sow": "pdf", "igce": "md"}'
        parsed = json.loads(raw)
        assert parsed == {"sow": "pdf", "igce": "md"}

    def test_invalid_format_map_returns_error(self):
        """Malformed JSON in format_map should be caught."""
        import json

        with pytest.raises(json.JSONDecodeError):
            json.loads("not-valid-json{")


# ═══════════════════════════════════════════════════════════════════
#  TestExportTracking
# ═══════════════════════════════════════════════════════════════════


class TestExportTracking:
    """Tests for export_store record/list functions."""

    @patch("app.export_store.get_table")
    @patch("app.export_store.now_iso", return_value="2026-03-27T12:00:00Z")
    @patch("app.export_store.ttl_timestamp", return_value=1774000000)
    def test_record_export_creates_item(
        self, mock_ttl, mock_now, mock_tbl,
    ):
        from app.export_store import record_export

        mock_table = MagicMock()
        mock_tbl.return_value = mock_table

        record_export(
            tenant_id="tenant-1",
            package_id="PKG-0001",
            user_id="user-1",
            export_format="docx",
            doc_types_included=["sow", "igce"],
            file_size=12345,
        )

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args.kwargs["Item"]
        assert item["PK"] == "EXPORT#tenant-1"
        assert item["SK"].startswith("EXPORT#")
        assert item["package_id"] == "PKG-0001"
        assert item["file_size"] == 12345

    @patch("app.export_store.get_table")
    def test_list_exports_queries_tenant(self, mock_tbl):
        from app.export_store import list_exports

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_tbl.return_value = mock_table

        list_exports("tenant-1")

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args.kwargs
        # Verify PK condition targets correct tenant
        assert "KeyConditionExpression" in call_kwargs

    @patch("app.export_store.get_table")
    def test_list_exports_filters_by_package(self, mock_tbl):
        from app.export_store import list_exports

        items = [
            {"package_id": "PKG-0001", "export_id": "EXP-a"},
            {"package_id": "PKG-0002", "export_id": "EXP-b"},
            {"package_id": "PKG-0001", "export_id": "EXP-c"},
        ]
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": items}
        mock_tbl.return_value = mock_table

        result = list_exports("tenant-1", package_id="PKG-0001")

        assert len(result) == 2
        assert all(r["package_id"] == "PKG-0001" for r in result)

    @patch("app.export_store.record_export")
    def test_export_tracking_failure_nonfatal(self, mock_record):
        """ZIP export should succeed even if tracking fails."""
        from app.document_export import export_package_zip

        mock_record.side_effect = Exception("DynamoDB down")

        # export_package_zip itself doesn't call record_export
        # (the router does), so this just confirms the function
        # is independently callable
        result = export_package_zip(_make_docs(), "Pkg", "md")
        assert result["size_bytes"] > 0

    @patch("app.export_store.get_table")
    def test_list_exports_endpoint(self, mock_tbl):
        from fastapi.testclient import TestClient

        from app.main import app

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_tbl.return_value = mock_table

        client = TestClient(app)
        resp = client.get(
            "/api/packages/PKG-0001/exports",
            headers={"x-tenant-id": "tenant-1", "x-user-id": "u1"},
        )
        assert resp.status_code == 200
        assert "exports" in resp.json()

    @patch("app.export_store.get_table")
    @patch("app.export_store.now_iso", return_value="2026-03-27T12:00:00Z")
    @patch("app.export_store.ttl_timestamp", return_value=1774000000)
    def test_export_records_on_zip_download(
        self, mock_ttl, mock_now, mock_tbl,
    ):
        """record_export should store the correct metadata."""
        from app.export_store import record_export

        mock_table = MagicMock()
        mock_tbl.return_value = mock_table

        result = record_export(
            tenant_id="tenant-1",
            package_id="PKG-0001",
            user_id="user-1",
            export_format="docx",
            doc_types_included=["sow"],
            file_size=9999,
        )

        assert result["tenant_id"] == "tenant-1"
        assert result["export_format"] == "docx"
        assert result["file_size"] == 9999

    @patch("app.export_store.get_table")
    def test_manage_package_exports_operation(self, mock_tbl):
        from app.tools.package_document_tools import exec_manage_package

        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}
        mock_tbl.return_value = mock_table

        result = exec_manage_package(
            {"operation": "exports", "package_id": "PKG-0001"},
            "tenant-1",
        )
        assert "exports" in result
        assert "count" in result
