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

    result = list_user_documents(
        tenant_id="test-tenant",
        user_id="test-user",
        package_id="PKG-1",
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["documents"] == [
        {
            "document_id": "doc-1",
            "title": "Mine",
            "doc_type": "requirements",
            "filename": "mine.pdf",
            "package_id": "PKG-1",
            "is_deliverable": False,
            "created_at": "2026-04-01T00:00:00Z",
        }
    ]
