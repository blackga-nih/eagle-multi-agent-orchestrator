"""Lambda entry point — iterates S3 records, orchestrates metadata extraction pipeline."""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import uuid
from datetime import datetime, timezone

import boto3

from catalog_manager import update_catalog
from dynamo_writer import write_metadata
from extractor import extract_metadata
from file_processors import extract_text
from models import DocumentMetadata

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client(
    "s3",
    region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
)
bedrock = boto3.client(
    "bedrock-runtime",
    region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
)
ddb = boto3.resource(
    "dynamodb",
    region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
)

_KB_PREFIX = "eagle-knowledge-base/pending/"
_MATRIX_S3_KEY = os.environ.get("MATRIX_S3_KEY", "eagle-plugin/data/matrix.json")
_METADATA_TABLE = os.environ.get("METADATA_TABLE", "eagle-document-metadata-dev")
_BEDROCK_MODEL = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")


def lambda_handler(event, context):
    """Process S3 ObjectCreated events and extract document metadata."""
    records = event.get("Records", [])
    logger.info("Processing %d S3 event record(s)", len(records))

    results = []

    for record in records:
        try:
            bucket = record["s3"]["bucket"]["name"]
            key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
            size = record["s3"]["object"].get("size", 0)

            logger.info("Processing s3://%s/%s (%d bytes)", bucket, key, size)

            # ── KB ingestion branch ───────────────────────────────────
            if key.startswith(_KB_PREFIX):
                result_entry = handle_kb_ingestion(bucket, key, size)
                results.append(result_entry)
                continue

            # ── Standard metadata extraction ──────────────────────────
            file_name = key.split("/")[-1]
            file_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

            if file_ext not in ("txt", "md", "pdf", "doc", "docx"):
                logger.warning("Skipping unsupported file type: %s", file_ext)
                continue

            # Download document from S3
            response = s3.get_object(Bucket=bucket, Key=key)
            body_bytes = response["Body"].read()

            # Extract text content
            text = extract_text(body_bytes, file_ext)
            if not text.strip():
                logger.warning("No text extracted from %s, using filename as metadata", key)

            # Call Claude via Bedrock for metadata extraction
            extracted = extract_metadata(text, file_name) if text.strip() else {}

            # Compute file metrics
            word_count = len(text.split()) if text else 0
            page_count = text.count('\f') + 1 if text else 1  # form feed = page break
            file_size_kb = round(size / 1024)

            # Build metadata model
            now = datetime.now(timezone.utc).isoformat()
            metadata = DocumentMetadata(
                # Core identifiers
                document_id=key,
                file_name=file_name,
                file_type=file_ext,
                file_size_bytes=size,
                s3_bucket=bucket,
                s3_key=key,
                # LLM-extracted: core classification
                title=extracted.get("title", file_name),
                summary=extracted.get("summary", ""),
                document_type=extracted.get("document_type", "unknown"),
                source_agency=extracted.get("source_agency", ""),
                # LLM-extracted: topic & routing
                primary_topic=extracted.get("primary_topic", "general"),
                related_topics=extracted.get("related_topics", []),
                primary_agent=extracted.get("primary_agent", "supervisor-core"),
                relevant_agents=extracted.get("relevant_agents", []),
                # LLM-extracted: content analysis
                key_requirements=extracted.get("key_requirements", []),
                section_summaries=extracted.get("section_summaries", {}),
                keywords=extracted.get("keywords", []),
                # LLM-extracted: regulatory references
                far_references=extracted.get("far_references", []),
                statute_references=extracted.get("statute_references", []),
                agency_references=extracted.get("agency_references", []),
                agencies=extracted.get("agencies", []),
                authority_level=extracted.get("authority_level", "guidance"),
                # LLM-extracted: discovery & audience
                complexity_level=extracted.get("complexity_level", "intermediate"),
                audience=extracted.get("audience", []),
                # LLM-extracted: temporal
                effective_date=extracted.get("effective_date", ""),
                expiration_date=extracted.get("expiration_date", ""),
                fiscal_year=int(extracted.get("fiscal_year", 0)),
                # Computed metrics
                word_count=word_count,
                page_count=page_count,
                file_size_kb=file_size_kb,
                # Confidence
                confidence_score=float(extracted.get("confidence_score", 0.0)),
                # Timestamps
                upload_date=now,
                last_updated=now,
                extraction_model=os.environ.get("BEDROCK_MODEL_ID", ""),
            )

            # Write to DynamoDB
            write_metadata(metadata.to_dynamo_item())

            # Update S3 catalog
            update_catalog(key, metadata.model_dump())

            results.append({"document_id": key, "status": "success"})
            logger.info("Successfully processed %s", key)

        except Exception:
            logger.exception("Failed to process record: %s", record)
            results.append({
                "document_id": record.get("s3", {}).get("object", {}).get("key", "unknown"),
                "status": "error",
            })

    return {
        "statusCode": 200,
        "body": {"processed": len(results), "results": results},
    }


def handle_kb_ingestion(bucket: str, key: str, size: int) -> dict:
    """Handle a document dropped into eagle-knowledge-base/pending/."""
    file_name = key.split("/")[-1]
    file_ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    logger.info("KB ingestion: %s", key)

    # Download and extract text
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        body_bytes = response["Body"].read()
        text = extract_text(body_bytes, file_ext) if file_ext in ("txt", "md", "pdf", "doc", "docx") else ""
    except Exception as e:
        logger.error("Failed to download KB document %s: %s", key, e)
        return {"document_id": key, "status": "error", "error": str(e)}

    if not text.strip():
        logger.warning("No text extracted from KB doc %s", key)
        text = f"[File: {file_name}, size: {size} bytes — text extraction failed]"

    # Load current matrix.json from S3 (canonical copy)
    try:
        matrix_resp = s3.get_object(Bucket=bucket, Key=_MATRIX_S3_KEY)
        matrix = json.loads(matrix_resp["Body"].read().decode("utf-8"))
    except Exception as e:
        logger.warning("Could not load matrix.json from S3 (%s); using empty baseline", e)
        matrix = {}

    matrix_summary = json.dumps(matrix, indent=2)[:4000]  # truncate for prompt

    # Prompt Claude to produce a structured diff
    prompt = f"""You are an acquisition policy analyst. A new regulatory document has been uploaded to the knowledge base.

## New Document
Filename: {file_name}
Content (truncated to 6000 chars):
{text[:6000]}

## Current matrix.json (truncated)
{matrix_summary}

## Task
Analyze the document and identify any changes it requires to the matrix.json.
Return a JSON object with exactly these keys:
- "analysis_summary": (string) 1-3 sentence plain-English summary of what changed and why
- "proposed_diff": (array) JSON Patch operations (RFC 6902) using op/path/value keys

Only include changes that are clearly supported by the document. If no changes are needed, return an empty proposed_diff array.
Return ONLY the JSON object, no markdown fences."""

    try:
        br_resp = bedrock.invoke_model(
            modelId=_BEDROCK_MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            }),
        )
        raw = json.loads(br_resp["body"].read())
        content_text = raw["content"][0]["text"]
        diff_result = json.loads(content_text)
    except Exception as e:
        logger.error("Bedrock diff analysis failed: %s", e)
        diff_result = {
            "analysis_summary": f"Automated analysis failed: {e}. Manual review required.",
            "proposed_diff": [],
        }

    # Write KB_REVIEW# record to DynamoDB
    now = datetime.now(timezone.utc).isoformat()
    review_id = f"{now[:19].replace(':', '-')}-{uuid.uuid4().hex[:8]}"
    pk = f"KB_REVIEW#{review_id}"

    try:
        table = ddb.Table(_METADATA_TABLE)
        table.put_item(Item={
            "PK": pk,
            "SK": "META",
            "review_id": review_id,
            "filename": file_name,
            "s3_key": key,
            "s3_bucket": bucket,
            "status": "pending",
            "analysis_summary": diff_result.get("analysis_summary", ""),
            "proposed_diff": diff_result.get("proposed_diff", []),
            "created_at": now,
            "reviewed_by": None,
            "reviewed_at": None,
        })
        logger.info("KB_REVIEW# record created: %s", review_id)
    except Exception as e:
        logger.error("DynamoDB write failed for KB review: %s", e)
        return {"document_id": key, "status": "error", "error": str(e)}

    return {"document_id": key, "status": "kb_review_pending", "review_id": review_id}
