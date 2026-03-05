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

EXTRACTION_PROMPT = """You are a federal acquisition document analyst. Extract comprehensive metadata from this document.

## Document
Filename: {file_name}
Content:
---
{document_text}
---

## Required Output (JSON)
Return a JSON object with ALL of these fields:

### Core Classification
- title: Document title (string)
- summary: 2-3 sentence summary, max 500 chars (string)
- document_type: regulation|guidance|policy|template|memo|checklist|reference|unknown (string)
- source_agency: FAR|GSA|OMB|DOD|GAO|HHS|NIH|NCI|other (string)

### Topic & Routing
- primary_topic: Main topic from [funding, acquisition_packages, contract_types, compliance, legal, market_research, socioeconomic, labor, intellectual_property, termination, modifications, closeout, performance, subcontracting, general] (string)
- related_topics: Array of secondary topics from the same list (array of strings)
- primary_agent: Best EAGLE agent from [supervisor-core, financial-advisor, legal-counselor, compliance-strategist, market-intelligence, technical-translator, public-interest-guardian] (string)
- relevant_agents: Other agents that should reference this document (array of strings)

### Content Analysis
- key_requirements: 3-5 main requirements or takeaways as short bullets (array of strings)
- section_summaries: Key sections mapped to brief summaries, e.g. {{"Purpose": "...", "Requirements": "..."}} (object)
- keywords: 5-15 search terms (array of strings)

### Regulatory References
- far_references: FAR citations like "FAR 16.505", "FAR Part 6" (array of strings)
- statute_references: USC citations like "31 USC 1341", "41 USC 3901" (array of strings)
- agency_references: Agency regs like "DFARS 232.7", "HHSAR 352.270" (array of strings)
- agencies: Government agencies mentioned (array of strings)
- authority_level: statute|regulation|policy|guidance|internal (string)

### Discovery & Audience
- complexity_level: basic|intermediate|advanced (string)
- audience: Target roles from [contracting_officer, legal_counsel, program_manager, financial_advisor, technical_specialist, supervisor, all] (array of strings)

### Temporal
- effective_date: ISO date (YYYY-MM-DD) if mentioned, else empty string
- expiration_date: ISO date if mentioned, else empty string
- fiscal_year: 4-digit year if applicable, else 0 (integer)

### Confidence
- confidence_score: Your confidence in extraction accuracy, 0.0 to 1.0 (float)

Return ONLY valid JSON, no markdown fences or explanation."""


def extract_metadata(document_text: str, file_name: str) -> dict:
    """Call Claude via Bedrock to extract metadata from document text."""
    model_id = os.environ["BEDROCK_MODEL_ID"]

    prompt = EXTRACTION_PROMPT.format(
        file_name=file_name,
        document_text=document_text[:40_000],
    )

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,  # Increased for expanded schema
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
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

        metadata = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError):
        logger.exception("Failed to parse Claude response for %s", file_name)
        metadata = _default_metadata(file_name)

    return metadata


def _default_metadata(file_name: str) -> dict:
    """Return default metadata when extraction fails."""
    return {
        # Core
        "title": file_name,
        "summary": "",
        "document_type": "unknown",
        "source_agency": "",
        # Topic & Routing
        "primary_topic": "general",
        "related_topics": [],
        "primary_agent": "supervisor-core",
        "relevant_agents": [],
        # Content
        "key_requirements": [],
        "section_summaries": {},
        "keywords": [],
        # Regulatory
        "far_references": [],
        "statute_references": [],
        "agency_references": [],
        "agencies": [],
        "authority_level": "guidance",
        # Discovery
        "complexity_level": "intermediate",
        "audience": [],
        # Temporal
        "effective_date": "",
        "expiration_date": "",
        "fiscal_year": 0,
        # Confidence
        "confidence_score": 0.0,
    }
