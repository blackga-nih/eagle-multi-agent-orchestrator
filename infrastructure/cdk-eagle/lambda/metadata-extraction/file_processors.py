"""Text extraction per file type (txt, md, pdf, docx)."""

from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 50_000  # Limit text sent to Gemini


def extract_text(body_bytes: bytes, file_type: str) -> str:
    """Extract text content from a document based on its file type."""
    file_type = file_type.lower().lstrip(".")

    extractors = {
        "txt": _extract_txt,
        "md": _extract_txt,
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "doc": _extract_docx,
        "xlsx": _extract_xlsx,
    }

    extractor = extractors.get(file_type)
    if not extractor:
        logger.warning("Unsupported file type: %s", file_type)
        return ""

    text = extractor(body_bytes)
    if len(text) > MAX_TEXT_LENGTH:
        logger.info("Truncating text from %d to %d chars", len(text), MAX_TEXT_LENGTH)
        text = text[:MAX_TEXT_LENGTH]

    return text


def _extract_txt(body_bytes: bytes) -> str:
    return body_bytes.decode("utf-8", errors="replace")


def _extract_pdf(body_bytes: bytes) -> str:
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(body_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n\n".join(pages)
    except Exception:
        logger.exception("Failed to extract PDF text")
        return ""


def _extract_docx(body_bytes: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(body_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception:
        logger.exception("Failed to extract DOCX text")
        return ""


def _extract_xlsx(body_bytes: bytes) -> str:
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(body_bytes), data_only=True)
        sheets = []
        for sheet in wb.worksheets:
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                if any(cells):
                    rows.append("\t".join(cells))
            if rows:
                sheets.append(f"## {sheet.title}\n" + "\n".join(rows))
        return "\n\n".join(sheets)
    except Exception:
        logger.exception("Failed to extract XLSX text")
        return ""
