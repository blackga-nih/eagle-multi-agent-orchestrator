from decimal import Decimal
from unittest.mock import MagicMock


def test_create_document_converts_nested_float_metadata(monkeypatch):
    from app.user_document_store import create_document

    mock_table = MagicMock()
    monkeypatch.setattr("app.user_document_store.get_table", lambda: mock_table)

    create_document(
        tenant_id="test-tenant",
        user_id="test-user",
        s3_bucket="test-bucket",
        s3_key="eagle/test-tenant/test-user/documents/doc-1/v1/test.pdf",
        filename="test.pdf",
        original_filename="test.pdf",
        content_type="application/pdf",
        size_bytes=123,
        doc_type="sow",
        title="Statement of Work",
        classification={
            "doc_type": "sow",
            "confidence": 0.95,
            "scores": {"filename": 0.9},
        },
    )

    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["classification"]["confidence"] == Decimal("0.95")
    assert item["classification"]["scores"]["filename"] == Decimal("0.9")


def test_create_document_preserves_caller_supplied_document_id(monkeypatch):
    from app.user_document_store import create_document

    mock_table = MagicMock()
    monkeypatch.setattr("app.user_document_store.get_table", lambda: mock_table)

    result = create_document(
        tenant_id="test-tenant",
        user_id="test-user",
        s3_bucket="test-bucket",
        s3_key="eagle/test-tenant/test-user/documents/doc-fixed/v1/test.pdf",
        filename="test.pdf",
        original_filename="test.pdf",
        content_type="application/pdf",
        size_bytes=123,
        document_id="doc-fixed",
    )

    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["document_id"] == "doc-fixed"
    assert item["SK"] == "USER_DOC#doc-fixed"
    assert result["document_id"] == "doc-fixed"
