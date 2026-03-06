#!/usr/bin/env python3
"""
Backfill missing summaries in eagle-document-metadata DynamoDB table.

Tests the extraction logic locally before updating the Lambda.
Uses tool_use for guaranteed valid JSON output from Claude.
"""

import argparse
import io
import json
import logging
import sys
from datetime import datetime, timezone

import boto3

# Optional: python-docx for .docx files
try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
    print("Warning: python-docx not installed. Run: pip install python-docx")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# AWS clients
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
s3 = boto3.client("s3", region_name="us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

TABLE_NAME = "eagle-document-metadata-dev"
BEDROCK_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


# ─────────────────────────────────────────────────────────────
# Text extraction
# ─────────────────────────────────────────────────────────────

def extract_text(body_bytes: bytes, file_ext: str) -> str:
    """Extract text from document bytes based on file type."""
    if file_ext in ("txt", "md"):
        return body_bytes.decode("utf-8", errors="replace")

    if file_ext == "docx":
        if not HAS_DOCX:
            logger.warning("python-docx not installed, cannot extract .docx")
            return ""
        try:
            doc = DocxDocument(io.BytesIO(body_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            logger.error("DOCX extraction failed: %s", e)
            return ""

    if file_ext == "pdf":
        # Could add PyPDF2 or pdfplumber here
        logger.warning("PDF extraction not implemented in this script")
        return ""

    return ""


# ─────────────────────────────────────────────────────────────
# Bedrock extraction with tool_use (guaranteed JSON)
# ─────────────────────────────────────────────────────────────

EXTRACTION_TOOL = {
    "name": "save_document_metadata",
    "description": "Save extracted metadata for a federal acquisition document",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Document title"},
            "summary": {"type": "string", "description": "2-3 sentence summary, max 500 chars"},
            "document_type": {
                "type": "string",
                "enum": ["regulation", "guidance", "policy", "template", "memo", "checklist", "reference", "unknown"]
            },
            "primary_topic": {
                "type": "string",
                "enum": ["funding", "acquisition_packages", "contract_types", "compliance", "legal",
                         "market_research", "socioeconomic", "labor", "intellectual_property",
                         "termination", "modifications", "closeout", "performance", "subcontracting", "general"]
            },
            "keywords": {"type": "array", "items": {"type": "string"}, "description": "5-15 search terms"},
            "far_references": {"type": "array", "items": {"type": "string"}, "description": "FAR citations"},
            "confidence_score": {"type": "number", "description": "0.0 to 1.0"}
        },
        "required": ["title", "summary", "document_type", "primary_topic", "keywords", "confidence_score"]
    }
}

EXTRACTION_PROMPT = """You are a federal acquisition document analyst. Extract metadata from this document.

## Document
Filename: {file_name}
Content (first 30000 chars):
---
{document_text}
---

Use the save_document_metadata tool to record the extracted metadata. Focus on:
- A clear, informative title
- A 2-3 sentence summary capturing the key purpose and requirements
- Accurate document type and topic classification
- Relevant FAR references if present
"""


def extract_metadata_with_tool(document_text: str, file_name: str) -> dict:
    """Call Claude via Bedrock using tool_use for guaranteed valid JSON."""
    prompt = EXTRACTION_PROMPT.format(
        file_name=file_name,
        document_text=document_text[:30000],
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "temperature": 0.1,
        "tools": [EXTRACTION_TOOL],
        "tool_choice": {"type": "tool", "name": "save_document_metadata"},
        "messages": [{"role": "user", "content": prompt}],
    })

    response = bedrock.invoke_model(modelId=BEDROCK_MODEL, body=body)
    result = json.loads(response["body"].read())

    # Extract tool_use input (guaranteed valid JSON by API)
    for block in result.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "save_document_metadata":
            return block.get("input", {})

    logger.error("No tool_use block in response")
    return {}


# ─────────────────────────────────────────────────────────────
# DynamoDB operations
# ─────────────────────────────────────────────────────────────

def get_documents_missing_summary(limit: int = 10) -> list:
    """Scan for documents with empty summary."""
    table = dynamodb.Table(TABLE_NAME)

    response = table.scan(
        FilterExpression="attribute_not_exists(summary) OR summary = :empty",
        ExpressionAttributeValues={":empty": ""},
        Limit=limit * 5,  # Over-fetch since filter is post-scan
    )

    items = [item for item in response.get("Items", []) if not item.get("summary")]
    return items[:limit]


def update_document_summary(document_id: str, metadata: dict, dry_run: bool = False) -> bool:
    """Update DynamoDB record with extracted metadata."""
    table = dynamodb.Table(TABLE_NAME)
    now = datetime.now(timezone.utc).isoformat()

    update_expr = "SET summary = :summary, title = :title, last_updated = :updated"
    expr_values = {
        ":summary": metadata.get("summary", ""),
        ":title": metadata.get("title", ""),
        ":updated": now,
    }

    # Add optional fields if present
    if metadata.get("document_type"):
        update_expr += ", document_type = :doc_type"
        expr_values[":doc_type"] = metadata["document_type"]
    if metadata.get("primary_topic"):
        update_expr += ", primary_topic = :topic"
        expr_values[":topic"] = metadata["primary_topic"]
    if metadata.get("keywords"):
        update_expr += ", keywords = :keywords"
        expr_values[":keywords"] = metadata["keywords"]
    if metadata.get("far_references"):
        update_expr += ", far_references = :far_refs"
        expr_values[":far_refs"] = metadata["far_references"]

    if dry_run:
        logger.info("[DRY RUN] Would update %s with: %s", document_id, metadata.get("summary", "")[:100])
        return True

    try:
        table.update_item(
            Key={"document_id": document_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
        return True
    except Exception as e:
        logger.error("Failed to update %s: %s", document_id, e)
        return False


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def process_document(item: dict, dry_run: bool = False) -> bool:
    """Process a single document: download, extract text, get summary, update."""
    document_id = item.get("document_id", "")
    s3_bucket = item.get("s3_bucket", "")
    s3_key = item.get("s3_key", document_id)
    file_name = item.get("file_name", s3_key.split("/")[-1])
    file_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    logger.info("Processing: %s", file_name)

    # Skip unsupported types
    if file_ext not in ("txt", "md", "docx"):
        logger.warning("Skipping unsupported file type: %s", file_ext)
        return False

    # Download from S3
    try:
        response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        body_bytes = response["Body"].read()
    except Exception as e:
        logger.error("S3 download failed for %s: %s", s3_key, e)
        return False

    # Extract text
    text = extract_text(body_bytes, file_ext)
    if not text.strip():
        logger.warning("No text extracted from %s", file_name)
        return False

    logger.info("Extracted %d chars from %s", len(text), file_name)

    # Call Bedrock for metadata
    try:
        metadata = extract_metadata_with_tool(text, file_name)
    except Exception as e:
        logger.error("Bedrock call failed: %s", e)
        return False

    if not metadata.get("summary"):
        logger.warning("No summary returned for %s", file_name)
        return False

    logger.info("Summary: %s", metadata.get("summary", "")[:150])

    # Update DynamoDB
    return update_document_summary(document_id, metadata, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description="Backfill missing document summaries")
    parser.add_argument("--limit", type=int, default=5, help="Max documents to process")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DynamoDB")
    parser.add_argument("--document-id", type=str, help="Process a specific document by ID")
    args = parser.parse_args()

    if not HAS_DOCX:
        logger.warning("Install python-docx for .docx support: pip install python-docx")

    if args.document_id:
        # Process specific document
        table = dynamodb.Table(TABLE_NAME)
        response = table.get_item(Key={"document_id": args.document_id})
        item = response.get("Item")
        if not item:
            logger.error("Document not found: %s", args.document_id)
            sys.exit(1)
        success = process_document(item, dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    # Process batch
    documents = get_documents_missing_summary(limit=args.limit)
    logger.info("Found %d documents missing summaries", len(documents))

    success_count = 0
    for item in documents:
        if process_document(item, dry_run=args.dry_run):
            success_count += 1

    logger.info("Completed: %d/%d successful", success_count, len(documents))


if __name__ == "__main__":
    main()
