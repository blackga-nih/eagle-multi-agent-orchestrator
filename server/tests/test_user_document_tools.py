def test_list_user_documents_filters_package_results_to_current_user(monkeypatch):
    from app.tools.user_document_tools import list_user_documents

    monkeypatch.setattr(
        "app.user_document_store.list_package_documents",
        lambda tenant_id, package_id, limit=50: [
            {
                "document_id": "doc-1",
                "title": "Mine",
                "doc_type": "requirements",
                "owner_user_id": "test-user",
                "original_filename": "mine.pdf",
                "package_id": package_id,
                "is_deliverable": False,
                "created_at": "2026-04-01T00:00:00Z",
            },
            {
                "document_id": "doc-2",
                "title": "Other User",
                "doc_type": "requirements",
                "owner_user_id": "someone-else",
                "original_filename": "other.pdf",
                "package_id": package_id,
                "is_deliverable": False,
                "created_at": "2026-04-01T00:00:00Z",
            },
        ],
    )
    monkeypatch.setattr(
        "app.package_attachment_store.list_user_package_attachments",
        lambda tenant_id, user_id, package_id=None, limit=50: [
            {
                "attachment_id": "att-1",
                "title": "Requirement Screenshot",
                "doc_type": None,
                "owner_user_id": user_id,
                "original_filename": "screen.png",
                "package_id": package_id,
                "category": "technical_evidence",
                "usage": "reference",
                "created_at": "2026-04-02T00:00:00Z",
            }
        ],
    )

    result = list_user_documents(
        tenant_id="test-tenant",
        user_id="test-user",
        package_id="PKG-1",
    )

    assert result["success"] is True
    assert result["count"] == 2
    assert result["documents"] == [
        {
            "document_id": "att-1",
            "title": "Requirement Screenshot",
            "doc_type": "attachment",
            "filename": "screen.png",
            "package_id": "PKG-1",
            "is_deliverable": False,
            "created_at": "2026-04-02T00:00:00Z",
            "entity_type": "package_attachment",
            "category": "technical_evidence",
            "usage": "reference",
        },
        {
            "document_id": "doc-1",
            "title": "Mine",
            "doc_type": "requirements",
            "filename": "mine.pdf",
            "package_id": "PKG-1",
            "is_deliverable": False,
            "created_at": "2026-04-01T00:00:00Z",
            "entity_type": "user_document",
        }
    ]


def test_get_document_content_reads_package_attachment(monkeypatch):
    from app.tools.user_document_tools import get_document_content

    class _Body:
        def read(self):
            return b"# Requirements\n\nUse this to draft the SOW."

    class _S3:
        def get_object(self, Bucket, Key):
            return {"Body": _Body()}

    monkeypatch.setattr("app.user_document_store.get_document", lambda tenant_id, document_id: None)
    monkeypatch.setattr(
        "app.package_attachment_store.find_attachment_by_id",
        lambda tenant_id, attachment_id, owner_user_id=None: {
            "attachment_id": attachment_id,
            "owner_user_id": owner_user_id,
            "title": "Prior Requirement",
            "package_id": "PKG-1",
            "doc_type": None,
            "s3_bucket": "bucket",
            "s3_key": "key",
            "content_type": "text/markdown",
            "filename": "requirements.md",
        },
    )
    monkeypatch.setattr("app.db_client.get_s3", lambda: _S3())

    result = get_document_content(
        tenant_id="test-tenant",
        user_id="test-user",
        document_id="att-1",
    )

    assert result["success"] is True
    assert result["entity_type"] == "package_attachment"
    assert result["package_id"] == "PKG-1"
    assert "draft the SOW" in result["content"]
