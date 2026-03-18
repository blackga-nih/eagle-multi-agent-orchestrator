"""
Document Classification Service — Classify uploaded documents by type.

Provides filename-based heuristics with optional content-based AI fallback
for ambiguous cases. Supports text extraction from PDF, DOCX, and plain text.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("eagle.document_classification")

# Valid document types for the EAGLE system
VALID_DOC_TYPES = {
    "sow",
    "igce",
    "market_research",
    "justification",
    "acquisition_plan",
}

# Filename patterns for quick classification (most specific first)
FILENAME_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Statement of Work
    (re.compile(r"\b(sow|statement[-_\s]?of[-_\s]?work)\b", re.IGNORECASE), "sow"),
    # IGCE / Cost Estimate
    (
        re.compile(
            r"\b(igce|ige|independent[-_\s]?government[-_\s]?(?:cost[-_\s]?)?estimate|cost[-_\s]?estimate)\b",
            re.IGNORECASE,
        ),
        "igce",
    ),
    # Market Research
    (re.compile(r"\b(market[-_\s]?research|mrr)\b", re.IGNORECASE), "market_research"),
    # Justification
    (
        re.compile(
            r"\b(j[&]?a|justification(?:[-_\s]?(?:&|and)[-_\s]?approval)?|sole[-_\s]?source)\b",
            re.IGNORECASE,
        ),
        "justification",
    ),
    # Acquisition Plan
    (re.compile(r"\b(ap|acquisition[-_\s]?plan)\b", re.IGNORECASE), "acquisition_plan"),
]

# Content patterns for AI fallback (keywords found in document body)
CONTENT_PATTERNS: list[tuple[re.Pattern[str], str, float]] = [
    # SOW indicators
    (re.compile(r"\bstatement\s+of\s+work\b", re.IGNORECASE), "sow", 0.9),
    (re.compile(r"\bperiod\s+of\s+performance\b", re.IGNORECASE), "sow", 0.7),
    (re.compile(r"\bdeliverables?\b.*\btasks?\b", re.IGNORECASE | re.DOTALL), "sow", 0.6),
    (re.compile(r"\bscope\s+of\s+work\b", re.IGNORECASE), "sow", 0.8),
    # IGCE indicators
    (re.compile(r"\bindependent\s+government\s+(?:cost\s+)?estimate\b", re.IGNORECASE), "igce", 0.95),
    (re.compile(r"\bigce\b", re.IGNORECASE), "igce", 0.9),
    (re.compile(r"\blabor\s+(?:hours?|rates?)\b.*\bcost\b", re.IGNORECASE | re.DOTALL), "igce", 0.7),
    (re.compile(r"\btotal\s+estimated\s+(?:cost|price)\b", re.IGNORECASE), "igce", 0.75),
    # Market Research indicators
    (re.compile(r"\bmarket\s+research\b", re.IGNORECASE), "market_research", 0.9),
    (re.compile(r"\bvendor\s+analysis\b", re.IGNORECASE), "market_research", 0.8),
    (re.compile(r"\bcompetitive\s+landscape\b", re.IGNORECASE), "market_research", 0.7),
    # Justification indicators
    (re.compile(r"\bjustification\s+(?:&|and)\s+approval\b", re.IGNORECASE), "justification", 0.95),
    (re.compile(r"\bsole\s+source\s+justification\b", re.IGNORECASE), "justification", 0.9),
    (re.compile(r"\bfar\s+6\.3", re.IGNORECASE), "justification", 0.8),
    # Acquisition Plan indicators
    (re.compile(r"\bacquisition\s+plan\b", re.IGNORECASE), "acquisition_plan", 0.9),
    (re.compile(r"\bacquisition\s+strategy\b", re.IGNORECASE), "acquisition_plan", 0.85),
    (re.compile(r"\bcontract\s+type\s+selection\b", re.IGNORECASE), "acquisition_plan", 0.75),
]


@dataclass
class ClassificationResult:
    """Result of document classification."""

    doc_type: str
    confidence: float
    method: str  # "filename" | "content" | "unknown"
    suggested_title: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "confidence": self.confidence,
            "method": self.method,
            "suggested_title": self.suggested_title,
        }


def classify_by_filename(filename: str) -> Optional[ClassificationResult]:
    """Classify document based on filename patterns."""
    if not filename:
        return None

    for pattern, doc_type in FILENAME_PATTERNS:
        if pattern.search(filename):
            # Generate suggested title from filename
            suggested = _clean_filename_for_title(filename)
            return ClassificationResult(
                doc_type=doc_type,
                confidence=0.95,
                method="filename",
                suggested_title=suggested,
            )
    return None


def classify_by_content(content: str) -> Optional[ClassificationResult]:
    """Classify document based on content patterns."""
    if not content or len(content) < 50:
        return None

    # Score each doc type by matching patterns
    scores: dict[str, float] = {}
    for pattern, doc_type, weight in CONTENT_PATTERNS:
        if pattern.search(content):
            scores[doc_type] = max(scores.get(doc_type, 0), weight)

    if not scores:
        return None

    # Return highest scoring type
    best_type = max(scores, key=lambda k: scores[k])
    return ClassificationResult(
        doc_type=best_type,
        confidence=scores[best_type],
        method="content",
        suggested_title=None,
    )


def classify_document(
    filename: str,
    content_preview: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify a document by type.

    First attempts filename-based classification (fast path).
    Falls back to content-based classification if filename is ambiguous.

    Args:
        filename: Original filename of the uploaded document
        content_preview: Optional extracted text content for fallback classification

    Returns:
        ClassificationResult with doc_type, confidence, and method
    """
    # Try filename first (fast path)
    result = classify_by_filename(filename)
    if result:
        logger.info("Classified %s as %s via filename (confidence=%.2f)", filename, result.doc_type, result.confidence)
        return result

    # Fall back to content analysis
    if content_preview:
        result = classify_by_content(content_preview)
        if result:
            result.suggested_title = _clean_filename_for_title(filename)
            logger.info("Classified %s as %s via content (confidence=%.2f)", filename, result.doc_type, result.confidence)
            return result

    # Unknown type
    logger.info("Could not classify %s, defaulting to unknown", filename)
    return ClassificationResult(
        doc_type="unknown",
        confidence=0.0,
        method="unknown",
        suggested_title=_clean_filename_for_title(filename),
    )


def extract_text_preview(
    body: bytes,
    content_type: str,
    max_chars: int = 4000,
) -> Optional[str]:
    """
    Extract text content from uploaded document for classification.

    Args:
        body: Raw file bytes
        content_type: MIME content type
        max_chars: Maximum characters to extract

    Returns:
        Extracted text or None if extraction fails
    """
    try:
        # Plain text / Markdown
        if content_type in ("text/plain", "text/markdown"):
            return body.decode("utf-8", errors="replace")[:max_chars]

        # PDF
        if content_type == "application/pdf":
            return _extract_pdf_text(body, max_chars)

        # DOCX
        if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return _extract_docx_text(body, max_chars)

        # MS Word (legacy .doc)
        if content_type == "application/msword":
            # Legacy .doc format is harder to parse; skip for now
            return None

        return None

    except Exception as e:
        logger.warning("Text extraction failed for %s: %s", content_type, e)
        return None


def _extract_pdf_text(body: bytes, max_chars: int) -> Optional[str]:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed, skipping PDF extraction")
        return None

    try:
        reader = PdfReader(io.BytesIO(body))
        text_parts: list[str] = []
        char_count = 0

        for page in reader.pages[:5]:  # Limit to first 5 pages
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            char_count += len(page_text)
            if char_count >= max_chars:
                break

        full_text = "\n".join(text_parts)
        return full_text[:max_chars]

    except Exception as e:
        logger.warning("PDF text extraction failed: %s", e)
        return None


def _extract_docx_text(body: bytes, max_chars: int) -> Optional[str]:
    """Extract text from DOCX using python-docx."""
    try:
        from docx import Document
    except ImportError:
        logger.warning("python-docx not installed, skipping DOCX extraction")
        return None

    try:
        doc = Document(io.BytesIO(body))
        text_parts: list[str] = []
        char_count = 0

        for para in doc.paragraphs:
            text_parts.append(para.text)
            char_count += len(para.text)
            if char_count >= max_chars:
                break

        full_text = "\n".join(text_parts)
        return full_text[:max_chars]

    except Exception as e:
        logger.warning("DOCX text extraction failed: %s", e)
        return None


def _clean_filename_for_title(filename: str) -> str:
    """Convert a filename to a human-readable title."""
    if not filename:
        return "Uploaded Document"

    # Remove extension
    name = filename.rsplit(".", 1)[0] if "." in filename else filename

    # Replace separators with spaces
    name = re.sub(r"[-_]+", " ", name)

    # Remove version numbers like v1, v2, _v3
    name = re.sub(r"\s*v\d+\s*", " ", name, flags=re.IGNORECASE)

    # Clean up multiple spaces
    name = re.sub(r"\s+", " ", name).strip()

    # Title case
    return name.title() if name else "Uploaded Document"
