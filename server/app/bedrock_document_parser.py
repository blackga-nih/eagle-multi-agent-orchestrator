"""Bedrock Document Parser — Native PDF parsing via Converse API.

Sends raw PDF bytes to Claude via the Converse API document content block,
getting high-quality markdown + classification in a single round trip.
Replaces the lossy pypdf text extraction for PDFs.

Uses Haiku by default for cost efficiency (~$0.005/upload vs $0.02-0.05 Sonnet).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

from .config import (
    DEFAULT_BEDROCK_HAIKU_MODEL,
    resolve_model_id,
)
from .doc_type_registry import ALL_DOC_TYPES, normalize_doc_type

logger = logging.getLogger("eagle.bedrock_document_parser")

# ── Configuration ───────────────────────────────────────────────────────

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Max pages for Converse API document blocks
_MAX_PDF_PAGES = 100


def _get_model_id() -> str:
    return resolve_model_id(
        "EAGLE_PDF_PARSING_MODEL",
        "EAGLE_BEDROCK_MODEL_ID",
        default=DEFAULT_BEDROCK_HAIKU_MODEL,
    )


# ── Lazy Bedrock Client ────────────────────────────────────────────────

_client = None


def _get_client():
    global _client  # noqa: PLW0603
    if _client is None:
        _client = boto3.client(
            "bedrock-runtime",
            region_name=AWS_REGION,
            config=BotoConfig(
                connect_timeout=int(
                    os.getenv("EAGLE_BEDROCK_CONNECT_TIMEOUT", "60")
                ),
                read_timeout=int(
                    os.getenv("EAGLE_BEDROCK_READ_TIMEOUT", "300")
                ),
                retries={
                    "max_attempts": 2,
                    "mode": "adaptive",
                },
            ),
        )
    return _client


# ── Data Models ─────────────────────────────────────────────────────────


@dataclass
class BedrockParseResult:
    """Result from Bedrock PDF parsing."""

    success: bool
    markdown: str = ""
    classification: str = "unknown"
    confidence: float = 0.0
    suggested_title: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None


# ── System Prompt ───────────────────────────────────────────────────────

_VALID_TYPES_STR = ", ".join(sorted(ALL_DOC_TYPES))

_SYSTEM_PROMPT = f"""You are a federal acquisition document parser for the National Cancer Institute (NCI).

You will receive a PDF document. Your job is to:

1. **Convert** the PDF content to clean, well-structured markdown:
   - Preserve ALL content faithfully — do not omit or summarize anything
   - Use proper markdown headings (# ## ###) matching the document's hierarchy
   - Reproduce tables using markdown pipe format with header separator rows
   - Convert bullet points and numbered lists to markdown format
   - Preserve bold/italic emphasis where apparent
   - Use `---` horizontal rules between major sections
   - Do NOT add content that wasn't in the original document

2. **Classify** the document into one of these EAGLE document types:
   {_VALID_TYPES_STR}
   If none match well, use "unknown".

3. **Return** your response in this exact format:
   - First, output the full markdown conversion
   - Then, on the very last line, output a JSON metadata block like this:
   <!-- EAGLE_META {{"doc_type": "market_research", "confidence": 0.95, "title": "Market Research Report — Cloud Services"}} -->

The confidence should reflect how certain you are about the classification (0.0-1.0).
The title should be a clean, descriptive title for the document."""


# ── Core Function ───────────────────────────────────────────────────────


def parse_pdf_with_bedrock(
    body: bytes,
    filename: str,
    doc_type_hint: Optional[str] = None,
) -> BedrockParseResult:
    """Parse a PDF using Bedrock Converse API with native document understanding.

    Args:
        body: Raw PDF bytes
        filename: Original filename (used for context)
        doc_type_hint: Optional classification hint from filename regex

    Returns:
        BedrockParseResult with markdown content and classification.
    """
    if not body:
        return BedrockParseResult(success=False, error="Empty document body")

    # Sanitize filename for Converse API name field
    # Allowed: alphanumeric, whitespace, hyphens, parens, brackets
    safe_name = re.sub(r"[^A-Za-z0-9\s\-\(\)\[\]]", " ", filename or "document")
    safe_name = re.sub(r"\s+", " ", safe_name).strip()[:200]
    if not safe_name:
        safe_name = "document"

    hint_text = ""
    if doc_type_hint and doc_type_hint != "unknown":
        hint_text = f"\n\nNote: The filename suggests this may be a '{doc_type_hint}' document, but classify based on the actual content."

    model_id = _get_model_id()
    logger.info(
        "Parsing PDF %s (%d bytes) with Bedrock %s",
        filename,
        len(body),
        model_id,
    )

    try:
        client = _get_client()
        response = client.converse(
            modelId=model_id,
            system=[{"text": _SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": f"Parse and classify this PDF document: {filename}{hint_text}",
                        },
                        {
                            "document": {
                                "name": safe_name,
                                "format": "pdf",
                                "source": {"bytes": body},
                            },
                        },
                    ],
                }
            ],
            inferenceConfig={
                "maxTokens": 16384,
                "temperature": 0.1,
            },
        )
    except Exception as e:
        logger.error("Bedrock Converse failed for %s: %s", filename, e)
        return BedrockParseResult(success=False, error=str(e))

    # Extract usage
    usage = response.get("usage", {})
    input_tokens = usage.get("inputTokens", 0)
    output_tokens = usage.get("outputTokens", 0)

    # Extract text from response
    output = response.get("output", {})
    message = output.get("message", {})
    content_blocks = message.get("content", [])

    full_text = ""
    for block in content_blocks:
        if "text" in block:
            full_text += block["text"]

    if not full_text.strip():
        return BedrockParseResult(
            success=False,
            error="Bedrock returned empty response",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    # Parse out the metadata block from the end
    markdown, classification, confidence, title = _parse_response(full_text)

    logger.info(
        "Parsed %s: doc_type=%s confidence=%.2f markdown=%d chars (%d in / %d out tokens)",
        filename,
        classification,
        confidence,
        len(markdown),
        input_tokens,
        output_tokens,
    )

    return BedrockParseResult(
        success=True,
        markdown=markdown,
        classification=classification,
        confidence=confidence,
        suggested_title=title,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _parse_response(
    text: str,
) -> tuple[str, str, float, str]:
    """Extract markdown and metadata from Bedrock response.

    Returns:
        (markdown, classification, confidence, title)
    """
    # Look for <!-- EAGLE_META {...} --> at end of response
    meta_pattern = r"<!--\s*EAGLE_META\s*(\{.*?\})\s*-->"
    match = re.search(meta_pattern, text, re.DOTALL)

    classification = "unknown"
    confidence = 0.0
    title = ""

    if match:
        # Strip the metadata line from the markdown
        markdown = text[: match.start()].rstrip()
        try:
            meta = json.loads(match.group(1))
            raw_type = meta.get("doc_type", "unknown")
            classification = normalize_doc_type(raw_type)
            if classification not in ALL_DOC_TYPES:
                classification = "unknown"
            confidence = float(meta.get("confidence", 0.0))
            title = meta.get("title", "")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to parse EAGLE_META block: %s", e)
    else:
        # No metadata block — use the full text as markdown
        markdown = text.rstrip()
        logger.warning("No EAGLE_META block found in Bedrock response")

    # Strip markdown code fences if Claude wrapped the output
    if markdown.startswith("```"):
        first_nl = markdown.find("\n")
        if first_nl > 0:
            markdown = markdown[first_nl + 1 :]
    if markdown.endswith("```"):
        markdown = markdown[: markdown.rfind("```")]

    return markdown.strip(), classification, confidence, title
