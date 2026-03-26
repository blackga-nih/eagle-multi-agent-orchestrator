"""Tests for ZIP package export (Feature 4)."""
import asyncio
import pytest
import zipfile
import io
from unittest.mock import patch, MagicMock, AsyncMock


class TestExportPackageZip:
    """Test export_package_zip function."""

    def test_valid_zip_with_two_docs(self):
        """ZIP should contain 2 files when given 2 documents."""
        from app.document_export import export_package_zip

        documents = [
            {"doc_type": "sow", "title": "Statement of Work", "content": "# SOW\n\nTest content"},
            {"doc_type": "igce", "title": "Cost Estimate", "content": "# IGCE\n\nCost breakdown"},
        ]

        result = export_package_zip(documents, "Test Package", "md")

        assert result["content_type"] == "application/zip"
        assert result["size_bytes"] > 0

        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        assert len(names) == 2
        assert any("sow" in n for n in names)
        assert any("igce" in n for n in names)

    def test_export_failure_adds_error_txt(self):
        """If one doc fails to export, a fallback error .txt should be included."""
        from app.document_export import export_package_zip

        documents = [
            {"doc_type": "sow", "title": "SOW", "content": "# SOW\nContent"},
            {"doc_type": "bad", "title": "Bad Doc", "content": "# Bad\nContent"},
        ]

        # Patch export_document to fail on one doc
        original_export = None
        import app.document_export as de
        original_export = de.export_document

        call_count = [0]

        def patched_export(content, fmt, title, metadata=None):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Export failed for bad doc")
            return original_export(content, fmt, title, metadata)

        with patch.object(de, "export_document", side_effect=patched_export):
            result = export_package_zip(documents, "Test", "md")

        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        names = zf.namelist()
        error_files = [n for n in names if "ERROR" in n]
        assert len(error_files) == 1

    def test_empty_docs_returns_empty_zip(self):
        """Empty document list should produce a valid but empty ZIP."""
        from app.document_export import export_package_zip

        result = export_package_zip([], "Empty Package")

        assert result["content_type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(result["data"]))
        assert len(zf.namelist()) == 0


class TestZipEndpoint:
    """Test the /api/packages/{id}/export/zip endpoint."""

    def test_returns_404_for_missing_package(self):
        """Should return 404 when package doesn't exist."""
        async def _run():
            from httpx import AsyncClient, ASGITransport
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("app.main.get_package", return_value=None):
                    response = await client.get(
                        "/api/packages/PKG-9999/export/zip",
                        headers={"X-Tenant-Id": "test", "X-User-Id": "user1"},
                    )
                    assert response.status_code == 404

        asyncio.run(_run())

    def test_returns_404_for_no_documents(self):
        """Should return 404 when package has no documents with content."""
        async def _run():
            from httpx import AsyncClient, ASGITransport
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("app.main.get_package", return_value={"title": "Test"}), \
                     patch("app.main.list_package_documents", return_value=[]):
                    response = await client.get(
                        "/api/packages/PKG-0001/export/zip",
                        headers={"X-Tenant-Id": "test", "X-User-Id": "user1"},
                    )
                    assert response.status_code == 404

        asyncio.run(_run())

    def test_returns_zip_content_type(self):
        """Should return application/zip content type on success."""
        async def _run():
            from httpx import AsyncClient, ASGITransport
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("app.main.get_package", return_value={"title": "Test"}), \
                     patch("app.main.list_package_documents", return_value=[
                         {"doc_type": "sow", "title": "SOW", "content": "# SOW\nContent"}
                     ]), \
                     patch("app.document_export.export_package_zip", return_value={
                         "data": b"PK\x03\x04fake",
                         "filename": "test.zip",
                         "content_type": "application/zip",
                         "size_bytes": 10,
                     }):
                    response = await client.get(
                        "/api/packages/PKG-0001/export/zip",
                        headers={"X-Tenant-Id": "test", "X-User-Id": "user1"},
                    )
                    assert response.status_code == 200
                    assert response.headers["content-type"] == "application/zip"

        asyncio.run(_run())
