from unittest import mock


def test_select_relevant_attachment_context_prefers_requirements_for_sow():
    from app.package_attachment_context import select_relevant_attachment_context

    attachments = [
        {
            "attachment_id": "att-1",
            "title": "Technical Requirements",
            "category": "requirements_evidence",
            "usage": "reference",
            "doc_type": None,
            "extracted_text": "System shall support secure data exchange and reporting.",
        },
        {
            "attachment_id": "att-2",
            "title": "Legacy SOW",
            "category": "prior_artifact",
            "usage": "official_candidate",
            "doc_type": "sow",
            "extracted_text": "Prior statement of work for a related cloud migration effort.",
        },
        {
            "attachment_id": "att-3",
            "title": "Pricing Sheet",
            "category": "pricing_evidence",
            "usage": "reference",
            "doc_type": None,
            "extracted_text": "Labor categories and loaded hourly rates.",
        },
    ]

    selected = select_relevant_attachment_context(attachments, target_doc_type="sow", limit=2)

    assert len(selected) == 2
    assert selected[0]["attachment_id"] == "att-2"
    assert selected[1]["attachment_id"] == "att-1"
    assert "cloud migration" in selected[0]["excerpt"]


def test_enrich_generation_data_from_attachments_uses_excerpt_defaults():
    from app.package_attachment_context import enrich_generation_data_from_attachments

    with mock.patch(
        "app.package_attachment_context.list_package_attachments",
        return_value=[
            {
                "attachment_id": "att-1",
                "title": "Requirements Doc",
                "category": "requirements_evidence",
                "usage": "reference",
                "doc_type": None,
                "extracted_text": (
                    "Contractor shall provide help desk services, incident response, "
                    "and monthly reporting for the research platform."
                ),
            }
        ],
    ):
        enriched = enrich_generation_data_from_attachments(
            tenant_id="test-tenant",
            package_id="PKG-1",
            target_doc_type="sow",
            data={},
        )

    assert "source_attachments" in enriched
    assert enriched["source_attachments"][0]["attachment_id"] == "att-1"
    assert "help desk services" in enriched["description"]
    assert "help desk services" in enriched["scope"]


def test_select_relevant_attachment_context_prefers_linked_checklist_support():
    from app.package_attachment_context import select_relevant_attachment_context

    attachments = [
        {
            "attachment_id": "att-1",
            "title": "Requirements Workbook",
            "category": "requirements_evidence",
            "usage": "reference",
            "doc_type": None,
            "linked_doc_type": None,
            "extracted_text": "Workbook with features and acceptance criteria.",
        },
        {
            "attachment_id": "att-2",
            "title": "Checklist Support Memo",
            "category": "technical_evidence",
            "usage": "checklist_support",
            "doc_type": None,
            "linked_doc_type": "sow",
            "extracted_text": "This memo supports the package SOW and defines service scope.",
        },
    ]

    selected = select_relevant_attachment_context(attachments, target_doc_type="sow", limit=1)

    assert selected[0]["attachment_id"] == "att-2"
    assert selected[0]["linked_doc_type"] == "sow"
