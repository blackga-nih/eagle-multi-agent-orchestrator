"""Test upload endpoint with a REAL PDF file.

Uses the sample Market Research Report PDF to exercise the full
classification + markdown conversion pipeline. Only S3 and DynamoDB are mocked.

TestRealPdfUpload — Local parsing (Bedrock disabled): pypdf + regex classification
TestBedrockUploadPipeline — Real Bedrock parsing: Converse API + AI classification
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.cognito_auth import UserContext

PDF_PATH = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "Market_Research_Report___NCI_Bioinformatics_ML_Pipeline_Development_and_Clinical_Data_Analysis_R_D_Services___3_5M_CPFF_.pdf",
)


def _make_user(
    tenant_id: str = "test-tenant", user_id: str = "test-user"
) -> UserContext:
    return UserContext(
        user_id=user_id,
        tenant_id=tenant_id,
        email=f"{user_id}@example.com",
    )


@pytest.fixture()
def mock_user() -> UserContext:
    return _make_user()


@pytest.fixture()
def client(mock_user: UserContext):
    import app.main as _main

    _main.app.dependency_overrides[_main.get_user_from_header] = lambda: mock_user
    with TestClient(_main.app, raise_server_exceptions=False) as c:
        yield c
    _main.app.dependency_overrides.clear()


@pytest.fixture()
def pdf_bytes():
    if not os.path.exists(PDF_PATH):
        pytest.skip(f"Sample PDF not found at {PDF_PATH}")
    with open(PDF_PATH, "rb") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Group 1: Local-only parsing (Bedrock PDF parsing DISABLED)
# ---------------------------------------------------------------------------


class TestRealPdfUpload:
    """Upload a real Market Research Report PDF with local parsing only.

    Bedrock PDF parsing is disabled so we test the pypdf + regex path.
    """

    def test_upload_classifies_as_market_research(self, client, pdf_bytes):
        """The filename contains 'Market_Research_Report' — classifier should detect it."""
        mock_doc = {"document_id": "doc-real-1", "doc_type": "market_research"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ) as mock_create,
            patch("app.bedrock_document_parser.parse_pdf_with_bedrock", side_effect=Exception("disabled")),
            patch("app.template_standardizer.standardize_template", side_effect=Exception("skip")),
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market_Research_Report.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Classification should detect market research from filename
        assert data["classification"]["doc_type"] == "market_research"
        assert data["classification"]["confidence"] >= 0.8

        # create_document should have been called with the correct doc_type
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["doc_type"] == "market_research"

    def test_upload_extracts_markdown_from_pdf(self, client, pdf_bytes):
        """The PDF should be converted to markdown and stored as a sibling."""
        mock_doc = {"document_id": "doc-real-2", "doc_type": "market_research"}

        mock_s3 = MagicMock()

        with (
            patch("app.routers.documents.get_s3", return_value=mock_s3),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ) as mock_create,
            patch("app.bedrock_document_parser.parse_pdf_with_bedrock", side_effect=Exception("disabled")),
            patch("app.template_standardizer.standardize_template", side_effect=Exception("skip")),
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market_Research_Report.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200

        # Markdown sibling should have been uploaded to S3
        call_kwargs = mock_create.call_args.kwargs
        md_key = call_kwargs.get("markdown_s3_key")
        assert md_key is not None, "Expected markdown_s3_key to be set"
        assert md_key.endswith(".content.md")

        # S3 should have received at least 2 put_object calls: original + markdown
        put_calls = mock_s3.put_object.call_args_list
        assert len(put_calls) >= 2, f"Expected 2+ S3 puts, got {len(put_calls)}"

        # The markdown body should contain actual content (not empty)
        md_put = [c for c in put_calls if "content.md" in str(c)]
        assert len(md_put) == 1
        md_body = md_put[0].kwargs.get("Body") or md_put[0][1].get("Body", b"")
        if isinstance(md_body, bytes):
            md_body = md_body.decode("utf-8")
        assert len(md_body) > 100, f"Markdown content too short ({len(md_body)} chars)"

    def test_upload_content_preview_extracted(self, client, pdf_bytes):
        """extract_text_preview should pull real text from the PDF."""
        from app.document_classification_service import extract_text_preview

        preview = extract_text_preview(pdf_bytes, "application/pdf")
        assert preview is not None, "PDF text extraction returned None"
        assert len(preview) > 50, f"Preview too short: {len(preview)} chars"
        # The Market Research Report should mention something about NCI/bioinformatics
        preview_lower = preview.lower()
        assert any(
            term in preview_lower
            for term in ["market", "research", "nci", "bioinformatics", "pipeline"]
        ), f"Preview didn't contain expected terms: {preview[:200]}"

    def test_upload_returns_quality_score(self, client, pdf_bytes):
        """quality_score should be present in the response."""
        mock_doc = {"document_id": "doc-real-3", "doc_type": "market_research"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ),
            patch("app.bedrock_document_parser.parse_pdf_with_bedrock", side_effect=Exception("disabled")),
            patch("app.template_standardizer.standardize_template", side_effect=Exception("skip")),
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market_Research_Report.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "quality_score" in data

    def test_upload_filename_sanitized(self, client, pdf_bytes):
        """Filenames with special characters should be sanitized."""
        mock_doc = {"document_id": "doc-real-4", "doc_type": "market_research"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ),
            patch("app.bedrock_document_parser.parse_pdf_with_bedrock", side_effect=Exception("disabled")),
            patch("app.template_standardizer.standardize_template", side_effect=Exception("skip")),
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market Research Report (NCI) $3.5M.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200
        data = response.json()
        filename = data["filename"]
        # No spaces, parens, or dollar signs in sanitized name
        assert " " not in filename
        assert "(" not in filename
        assert "$" not in filename
        assert filename.endswith(".pdf")


# ---------------------------------------------------------------------------
# Group 2: Bedrock pipeline (REAL Bedrock, mocked S3/DynamoDB)
# ---------------------------------------------------------------------------


class TestBedrockUploadPipeline:
    """Upload pipeline with real Bedrock PDF parsing enabled."""

    def test_bedrock_classifies_market_research(self, client, pdf_bytes):
        """Full pipeline: Bedrock parses PDF, classifies as market_research."""
        mock_doc = {"document_id": "doc-br-1", "doc_type": "market_research"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ) as mock_create,
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market_Research_Report.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Should be classified correctly (by filename or Bedrock)
        assert data["classification"]["doc_type"] == "market_research"
        # quality_score should exist (from assess_quality on Bedrock markdown)
        assert "quality_score" in data

        # create_document should have been called
        assert mock_create.called
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["doc_type"] == "market_research"
        # Markdown should be present and substantial (Bedrock output)
        md_key = call_kwargs.get("markdown_s3_key")
        assert md_key is not None

    def test_bedrock_produces_quality_markdown(self, client, pdf_bytes):
        """Bedrock markdown should have tables, headings, and structure."""
        mock_doc = {"document_id": "doc-br-2", "doc_type": "market_research"}

        mock_s3 = MagicMock()

        with (
            patch("app.routers.documents.get_s3", return_value=mock_s3),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ),
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market_Research_Report.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200

        # Extract the markdown content from the S3 put calls
        put_calls = mock_s3.put_object.call_args_list
        md_puts = [c for c in put_calls if "content.md" in str(c)]
        assert len(md_puts) == 1, f"Expected 1 markdown put, got {len(md_puts)}"

        md_body = md_puts[0].kwargs.get("Body") or md_puts[0][1].get("Body", b"")
        if isinstance(md_body, bytes):
            md_body = md_body.decode("utf-8")

        # Bedrock markdown should be substantially richer than pypdf
        assert len(md_body) > 500, f"Markdown too short: {len(md_body)} chars"
        # Should have proper headings
        assert "# " in md_body, "No headings in Bedrock markdown"
        # Should have tables (pipe format)
        assert "|" in md_body, "No tables in Bedrock markdown"

    def test_bedrock_quality_score_populated(self, client, pdf_bytes):
        """When Bedrock parsing succeeds, quality_score should be numeric."""
        mock_doc = {"document_id": "doc-br-3", "doc_type": "market_research"}

        with (
            patch("app.routers.documents.get_s3", return_value=MagicMock()),
            patch(
                "app.user_document_store.create_document", return_value=mock_doc
            ),
        ):
            response = client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        "Market_Research_Report.pdf",
                        pdf_bytes,
                        "application/pdf",
                    )
                },
            )

        assert response.status_code == 200
        data = response.json()
        # Bedrock path runs assess_quality which should return a numeric score
        assert data["quality_score"] is not None
        assert isinstance(data["quality_score"], (int, float))
        assert data["quality_score"] >= 0
