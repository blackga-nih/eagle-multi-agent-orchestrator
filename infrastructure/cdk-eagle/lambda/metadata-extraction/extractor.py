"""Bedrock invoke_model call to Claude for metadata extraction."""

from __future__ import annotations

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)

bedrock = boto3.client(
    "bedrock-runtime",
    region_name=os.environ.get("AWS_REGION_NAME", "us-east-1"),
)

EXTRACTION_PROMPT = """You are a government acquisition document analyst. Analyze the following document and extract structured metadata.

Return ONLY valid JSON with these fields:
- title: document title (string)
- summary: 2-3 sentence summary (string)
- document_type: one of [regulation, guidance, template, memo, report, policy, unknown] (string)
- primary_topic: main topic from [contracting, pricing, compliance, market_research, source_selection, contract_administration, small_business, it_acquisition, services, construction, general] (string)
- primary_agent: best EAGLE agent from [supervisor, legal-counsel, market-intelligence, tech-translator, public-interest, policy-supervisor, policy-librarian, policy-analyst] (string)
- keywords: up to 10 relevant keywords (list of strings)
- agencies: mentioned government agencies (list of strings)
- far_references: FAR/DFARS clause references like "FAR 15.3" (list of strings)
- confidence_score: your confidence in the extraction from 0.0 to 1.0 (float)

Document text:
---
{document_text}
---

Return ONLY the JSON object, no markdown fences or explanation."""


def extract_metadata(document_text: str, file_name: str) -> dict:
    """Call Claude via Bedrock to extract metadata from document text."""
    model_id = os.environ["BEDROCK_MODEL_ID"]

    prompt = EXTRACTION_PROMPT.format(document_text=document_text[:40_000])

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0.1,
            "messages": [{"role": "user", "content": prompt}],
        }
    )

    logger.info("Invoking Bedrock model %s for %s", model_id, file_name)

    response = bedrock.invoke_model(modelId=model_id, body=body)
    result = json.loads(response["body"].read())

    # Parse Claude response — extract text from content array
    try:
        text = result["content"][0]["text"].strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        metadata = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError):
        logger.exception("Failed to parse Claude response for %s", file_name)
        metadata = {
            "title": file_name,
            "summary": "",
            "document_type": "unknown",
            "primary_topic": "general",
            "primary_agent": "supervisor",
            "keywords": [],
            "agencies": [],
            "far_references": [],
            "confidence_score": 0.0,
        }

    return metadata
