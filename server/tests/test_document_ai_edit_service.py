"""Tests for DOCX-aware AI editing helpers."""

import io
import os
import sys
import zipfile
from unittest.mock import MagicMock, patch

# Ensure server/ is on sys.path so "app.*" resolves
_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from app.document_ai_edit_service import (
    DocxCheckboxEdit,
    DocxEdit,
    apply_docx_block_edits,
    apply_docx_edits,
    edit_docx_document,
    extract_docx_preview,
    extract_docx_preview_payload,
)


def _build_sample_docx() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("Statement of Work", level=1)
    doc.add_paragraph("Original scope paragraph.")
    table = doc.add_table(rows=1, cols=1)
    table.rows[0].cells[0].text = "Original table text."
    section = doc.sections[0]
    section.header.paragraphs[0].text = "Original header text."
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


def _build_checkbox_docx(label: str = "Needs review", checked: bool = False) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_paragraph("CHECKBOX_PLACEHOLDER")
    output = io.BytesIO()
    doc.save(output)

    checkbox_xml = (
        '<w:r><w:fldChar w:fldCharType="begin"><w:ffData><w:name w:val="Check1"/>'
        '<w:enabled/><w:calcOnExit w:val="0"/><w:checkBox><w:sizeAuto/>'
        f'<w:checked w:val="{"1" if checked else "0"}"/></w:checkBox></w:ffData></w:fldChar></w:r>'
        '<w:r><w:instrText xml:space="preserve"> FORMCHECKBOX </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        '<w:r><w:tab/></w:r>'
        f'<w:r><w:t>{label}</w:t></w:r>'
    )

    src = io.BytesIO(output.getvalue())
    dst = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                text = data.decode("utf-8")
                text = text.replace(
                    "<w:r><w:t>CHECKBOX_PLACEHOLDER</w:t></w:r>",
                    checkbox_xml,
                )
                data = text.encode("utf-8")
            zout.writestr(item, data)
    return dst.getvalue()


def test_apply_docx_edits_replaces_body_header_and_table_text():
    updated_bytes, applied_count, missing = apply_docx_edits(
        _build_sample_docx(),
        [
            DocxEdit(search_text="Original scope paragraph.", replacement_text="Updated scope paragraph."),
            DocxEdit(search_text="Original table text.", replacement_text="Updated table text."),
            DocxEdit(search_text="Original header text.", replacement_text="Updated header text."),
        ],
    )

    from docx import Document

    doc = Document(io.BytesIO(updated_bytes))
    assert applied_count == 3
    assert missing == []
    assert any("Updated scope paragraph." in para.text for para in doc.paragraphs)
    assert doc.tables[0].rows[0].cells[0].text == "Updated table text."
    assert doc.sections[0].header.paragraphs[0].text == "Updated header text."


def test_extract_docx_preview_renders_checkbox_fields_as_markdown_tasks():
    preview = extract_docx_preview(_build_checkbox_docx(label="A new requirement", checked=False))

    assert preview is not None
    assert "- [ ] A new requirement" in preview


def test_extract_docx_preview_falls_back_to_markdown_text_for_misnamed_artifact():
    preview = extract_docx_preview(b"# Purchase Request\n\nThis is markdown saved with a .docx name.\n")

    assert preview is not None
    assert "# Purchase Request" in preview
    assert "This is markdown saved with a .docx name." in preview


def test_extract_docx_preview_payload_returns_structured_blocks():
    payload = extract_docx_preview_payload(_build_checkbox_docx(label="A new requirement", checked=False))

    assert payload["preview_mode"] == "docx_blocks"
    assert payload["content"] is not None
    assert any(block["kind"] == "checkbox" and block["text"] == "A new requirement" for block in payload["preview_blocks"])


def test_apply_docx_block_edits_updates_text_and_checkbox_blocks():
    payload = extract_docx_preview_payload(_build_checkbox_docx(label="A new requirement", checked=False))
    blocks = payload["preview_blocks"]
    checkbox_block = next(block for block in blocks if block["kind"] == "checkbox")
    checkbox_block["checked"] = True
    checkbox_block["text"] = "Updated requirement"

    updated_bytes, applied_count = apply_docx_block_edits(
        _build_checkbox_docx(label="A new requirement", checked=False),
        blocks,
        payload["preview_mode"],
    )

    assert applied_count >= 1
    preview = extract_docx_preview(updated_bytes) or ""
    assert "- [x] Updated requirement" in preview


def test_apply_docx_edits_toggles_legacy_checkbox_fields():
    updated_bytes, applied_count, missing = apply_docx_edits(
        _build_checkbox_docx(label="A new requirement", checked=False),
        [],
        [DocxCheckboxEdit(label_text="A new requirement", checked=True)],
    )

    assert applied_count == 1
    assert missing == []

    xml = zipfile.ZipFile(io.BytesIO(updated_bytes)).read("word/document.xml").decode("utf-8")
    assert 'w:checked w:val="1"' in xml
    assert "- [x] A new requirement" in (extract_docx_preview(updated_bytes) or "")


def test_edit_docx_document_versions_package_doc():
    docx_bytes = _build_sample_docx()
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(docx_bytes)}

    with patch("app.document_ai_edit_service._get_s3", return_value=s3), patch(
        "app.document_ai_edit_service.get_document",
        return_value={"title": "Statement of Work", "template_id": "tmpl-1"},
    ), patch(
        "app.document_ai_edit_service.create_package_document_version",
        return_value=MagicMock(success=True, document_id="doc-2", s3_key="eagle/dev-tenant/packages/PKG-1/sow/v2/Statement-of-Work.docx", version=2),
    ) as create_mock:
        result = edit_docx_document(
            tenant_id="dev-tenant",
            user_id="dev-user",
            doc_key="eagle/dev-tenant/packages/PKG-1/sow/v1/source.docx",
            edits=[DocxEdit(search_text="Original scope paragraph.", replacement_text="Updated scope paragraph.")],
            session_id="session-1",
            change_source="ai_edit",
        )

    assert result["success"] is True
    assert result["version"] == 2
    assert result["edits_applied"] == 1
    assert "Updated scope paragraph." in (result.get("content") or "")

    saved_bytes = create_mock.call_args.kwargs["content"]
    from docx import Document

    saved_doc = Document(io.BytesIO(saved_bytes))
    assert any("Updated scope paragraph." in para.text for para in saved_doc.paragraphs)
    assert create_mock.call_args.kwargs["file_type"] == "docx"
    assert create_mock.call_args.kwargs["change_source"] == "ai_edit"


def test_edit_docx_document_versions_package_doc_with_checkbox_toggle():
    docx_bytes = _build_checkbox_docx(label="A new requirement", checked=False)
    s3 = MagicMock()
    s3.get_object.return_value = {"Body": io.BytesIO(docx_bytes)}

    with patch("app.document_ai_edit_service._get_s3", return_value=s3), patch(
        "app.document_ai_edit_service.get_document",
        return_value={"title": "Market Research", "template_id": "tmpl-2"},
    ), patch(
        "app.document_ai_edit_service.create_package_document_version",
        return_value=MagicMock(success=True, document_id="doc-3", s3_key="eagle/dev-tenant/packages/PKG-1/market_research/v2/Market-Research.docx", version=2),
    ) as create_mock:
        result = edit_docx_document(
            tenant_id="dev-tenant",
            user_id="dev-user",
            doc_key="eagle/dev-tenant/packages/PKG-1/market_research/v1/source.docx",
            edits=[],
            checkbox_edits=[DocxCheckboxEdit(label_text="A new requirement", checked=True)],
            session_id="session-2",
            change_source="ai_edit",
        )

    assert result["success"] is True
    assert result["edits_applied"] == 1
    assert "- [x] A new requirement" in (result.get("content") or "")

    saved_bytes = create_mock.call_args.kwargs["content"]
    xml = zipfile.ZipFile(io.BytesIO(saved_bytes)).read("word/document.xml").decode("utf-8")
    assert 'w:checked w:val="1"' in xml
