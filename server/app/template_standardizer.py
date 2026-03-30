"""Template Standardizer — AI-powered conversion to gold-standard markdown.

Converts raw document text (DOCX, PDF, TXT, DOC) into properly structured
markdown using Bedrock Claude. Includes quality scoring and batch job tracking.

XLSX files are excluded — IGCE/IGE spreadsheets already have a hand-crafted
igce-template.md as their gold standard.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import boto3

logger = logging.getLogger("eagle.template_standardizer")

# ── Bedrock Configuration ────────────────────────────────────────────
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv(
    "STANDARDIZER_MODEL_ID",
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
)

# ── Paths ────────────────────────────────────────────────────────────
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent / "eagle-plugin"
TEMPLATES_DIR = _PLUGIN_ROOT / "data" / "templates"
METADATA_DIR = _PLUGIN_ROOT / "data" / "template-metadata"

# XLSX MIME types — skipped by standardizer
_XLSX_MIMES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }
)

# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class StandardizationResult:
    """Result of standardizing a single template."""

    success: bool
    markdown: str
    quality_score: float = 0.0
    issues: list[str] = field(default_factory=list)
    placeholders_found: int = 0
    sections_found: int = 0
    tables_found: int = 0
    source_format: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    """Quality assessment of a markdown template."""

    score: float = 0.0
    has_title: bool = False
    has_metadata_block: bool = False
    has_numbered_sections: bool = False
    has_placeholders: bool = False
    has_tables: bool = False
    has_separators: bool = False
    has_footer: bool = False
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Reference Template Mapping ───────────────────────────────────────

_REFERENCE_MAP: Dict[str, str] = {
    "sow": "sow-template.md",
    "son_products": "sow-template.md",
    "son_services": "sow-template.md",
    "igce": "igce-template.md",
    "market_research": "market-research-template.md",
    "justification": "justification-template.md",
    "buy_american": "justification-template.md",
    "acquisition_plan": "acquisition-plan-template.md",
    "subk_plan": "acquisition-plan-template.md",
    "cor_certification": "justification-template.md",
    "conference_request": "justification-template.md",
    "conference_waiver": "justification-template.md",
    "promotional_item": "justification-template.md",
    "exemption_determination": "justification-template.md",
    "mandatory_use_waiver": "justification-template.md",
    "subk_review": "acquisition-plan-template.md",
    "gfp_form": "sow-template.md",
    "bpa_call_order": "sow-template.md",
    "technical_questionnaire": "sow-template.md",
    "quotation_abstract": "igce-template.md",
    "receiving_report": "sow-template.md",
    "srb_request": "justification-template.md",
    "reference_guide": "sow-template.md",
}

_DEFAULT_REFERENCE = "sow-template.md"

# ── Bedrock Client (lazy singleton) ──────────────────────────────────

_bedrock_client = None


def _get_bedrock():
    global _bedrock_client  # noqa: PLW0603
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _bedrock_client


# ── System Prompt ────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a federal acquisition document formatting specialist for the National Cancer Institute (NCI).

Your task: Convert raw extracted document text into a properly structured markdown template following this exact format specification.

## Required Markdown Format

1. **H1 Title** — `# DOCUMENT TYPE (ALL CAPS)` on the first line
2. **H2 Subtitle** — `## {{TITLE}}` with a placeholder token
3. **H3 Organization** — `### National Cancer Institute (NCI)`
4. **Metadata Block** — Bold key-value pairs:
   ```
   **Document Status:** DRAFT — Generated {{DATE}}
   **Prepared By:** {{PREPARER}}
   ```
5. **Horizontal Rule** — `---` between each major section
6. **Numbered Sections** — `## N. SECTION TITLE` at H2 level (ALL CAPS for section titles)
7. **Subsections** — `### N.N Subsection Title` at H3 level
8. **Placeholder Tokens** — `{{UPPER_SNAKE_CASE}}` for every fillable field. Convert any "[insert here]", "[fill in]", "________", or similar fill-in patterns to named placeholder tokens.
9. **Tables** — Markdown pipe format with header row and separator:
   ```
   | Column | Column |
   |--------|--------|
   | {{DATA}} | {{DATA}} |
   ```
10. **Checkboxes** — Use `☐` for checkbox items
11. **Footer** — End with:
    ```
    ---

    *This document was generated by EAGLE — NCI Acquisition Assistant*
    *Version: DRAFT - Subject to revision before official use*
    ```

## Rules
- Preserve ALL original content — do not remove any sections, requirements, or instructions
- Insert `{{PLACEHOLDER}}` tokens for every field that needs to be filled in by the user
- Use UPPER_SNAKE_CASE for placeholder names (e.g., `{{CONTRACT_NUMBER}}`, `{{PERIOD_OF_PERFORMANCE}}`)
- Keep section numbering consistent and sequential
- Ensure tables have proper markdown pipe formatting with header separator rows
- Bold (`**`) for field labels in key-value pairs
- Do NOT add content that wasn't in the original — only restructure and add placeholders
- Do NOT wrap the output in markdown code fences — return raw markdown directly"""


# ── Core Functions ───────────────────────────────────────────────────


def standardize_template(
    body: bytes,
    filename: str,
    content_type: str,
    doc_type: str,
) -> StandardizationResult:
    """Standardize a document to gold-standard markdown using Bedrock AI.

    Args:
        body: Raw file bytes
        filename: Original filename
        content_type: MIME type
        doc_type: Classified document type (e.g., "sow", "justification")

    Returns:
        StandardizationResult with the standardized markdown and quality metrics.
    """
    source_format = _detect_format(filename, content_type)

    # Skip XLSX — these use hand-crafted templates
    if content_type in _XLSX_MIMES or source_format == "xlsx":
        return StandardizationResult(
            success=False,
            markdown="",
            issues=["XLSX files are excluded from markdown standardization"],
            source_format="xlsx",
        )

    # Step 1: Extract raw text using existing converter
    raw_markdown = _extract_raw_text(body, content_type, filename)
    if not raw_markdown or not raw_markdown.strip():
        return StandardizationResult(
            success=False,
            markdown="",
            issues=["Failed to extract text from document"],
            source_format=source_format,
        )

    # Step 2: Load reference template and metadata hints
    reference_template = _get_reference_template(doc_type)
    metadata_hints = _get_metadata_hints(filename)

    # Step 3: AI standardization via Bedrock
    try:
        standardized = _ai_standardize(
            raw_markdown,
            doc_type,
            reference_template,
            metadata_hints,
        )
    except Exception as e:
        logger.error("AI standardization failed for %s: %s", filename, e)
        return StandardizationResult(
            success=False,
            markdown=raw_markdown,
            issues=[f"AI standardization failed: {e}"],
            source_format=source_format,
        )

    if not standardized or not standardized.strip():
        return StandardizationResult(
            success=False,
            markdown=raw_markdown,
            issues=["AI returned empty result"],
            source_format=source_format,
        )

    # Step 4: Assess quality of the output
    quality = assess_quality(standardized, doc_type)

    # Count structural elements
    placeholders = len(set(re.findall(r"\{\{(\w+)\}\}", standardized)))
    sections = len(re.findall(r"^## ", standardized, re.MULTILINE))
    tables = len(re.findall(r"^\|.+\|.+\|", standardized, re.MULTILINE))

    return StandardizationResult(
        success=True,
        markdown=standardized,
        quality_score=quality.score,
        issues=quality.issues,
        placeholders_found=placeholders,
        sections_found=sections,
        tables_found=tables,
        source_format=source_format,
    )


def _ai_standardize(
    raw_markdown: str,
    doc_type: str,
    reference_template: str,
    metadata_hints: dict,
) -> str:
    """Call Bedrock Claude to standardize the markdown.

    Args:
        raw_markdown: Raw extracted text from the document
        doc_type: Document type classification
        reference_template: Gold-standard reference template content
        metadata_hints: Section structure hints from metadata JSON

    Returns:
        Standardized markdown string.
    """
    # Build user prompt
    section_hints = ""
    if metadata_hints:
        sections = metadata_hints.get("sections", [])
        if sections:
            hints = [
                f"- Section {s.get('number', '?')}: {s.get('title', '?')}"
                for s in sections
            ]
            section_hints = "\n## Expected Sections\n" + "\n".join(hints)

    user_prompt = f"""Convert this document to properly structured markdown.

## Document Type
{doc_type.replace("_", " ").title()}

## Raw Document Content
---
{raw_markdown[:30000]}
---

## Reference Template (follow this format exactly)
---
{reference_template[:8000]}
---
{section_hints}

Convert the raw document content above into the gold-standard markdown format shown in the reference template. Preserve all original content while restructuring it."""

    body = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 8192,
            "temperature": 0.1,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
    )

    logger.info(
        "Invoking Bedrock %s for %s standardization", BEDROCK_MODEL_ID, doc_type
    )

    bedrock = _get_bedrock()
    response = bedrock.invoke_model(modelId=BEDROCK_MODEL_ID, body=body)
    result = json.loads(response["body"].read())

    # Extract text from Claude response
    text = result["content"][0]["text"].strip()

    # Strip markdown fences if the model wrapped the output
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    if text.startswith("markdown"):
        text = text[8:]

    return text.strip()


def assess_quality(markdown: str, doc_type: str = "") -> QualityReport:
    """Assess markdown quality against the gold standard format.

    Scoring:
        - H1 title: +15
        - Metadata block: +10
        - Numbered sections (## N.): +20
        - {{PLACEHOLDER}} tokens: +20
        - Markdown tables: +10
        - --- separators: +10
        - EAGLE footer: +5
        - Section count reasonable (3+): +10

    Args:
        markdown: Markdown content to assess
        doc_type: Document type (for context-specific checks)

    Returns:
        QualityReport with score and issues.
    """
    if not markdown or not markdown.strip():
        return QualityReport(score=0.0, issues=["Empty markdown content"])

    score = 0.0
    issues: list[str] = []

    # Check H1 title
    has_title = bool(re.search(r"^# [A-Z]", markdown, re.MULTILINE))
    if has_title:
        score += 15
    else:
        issues.append("Missing H1 title (# DOCUMENT TITLE)")

    # Check metadata block (**Key:** value)
    metadata_count = len(re.findall(r"^\*\*[^*]+:\*\*", markdown, re.MULTILINE))
    has_metadata = metadata_count >= 2
    if has_metadata:
        score += 10
    else:
        issues.append("Missing metadata block (**Key:** value pairs)")

    # Check numbered sections (## N. or ## PART N)
    numbered = re.findall(r"^## (?:\d+\.|PART \d)", markdown, re.MULTILINE)
    has_numbered_sections = len(numbered) >= 2
    if has_numbered_sections:
        score += 20
    else:
        issues.append("Missing numbered sections (## N. SECTION TITLE)")

    # Check placeholder tokens
    placeholders = set(re.findall(r"\{\{(\w+)\}\}", markdown))
    has_placeholders = len(placeholders) >= 3
    if has_placeholders:
        score += 20
    else:
        issues.append(f"Few/no placeholder tokens (found {len(placeholders)})")

    # Check markdown tables
    table_rows = re.findall(r"^\|.+\|", markdown, re.MULTILINE)
    has_tables = len(table_rows) >= 2
    if has_tables:
        score += 10
    else:
        issues.append("No markdown tables found")

    # Check separators
    separators = re.findall(r"^---\s*$", markdown, re.MULTILINE)
    has_separators = len(separators) >= 2
    if has_separators:
        score += 10
    else:
        issues.append("Missing --- section separators")

    # Check EAGLE footer
    has_footer = (
        "EAGLE" in markdown[-200:] and "NCI Acquisition Assistant" in markdown[-200:]
    )
    if has_footer:
        score += 5
    else:
        issues.append("Missing EAGLE footer")

    # Check reasonable section count
    all_sections = re.findall(r"^## ", markdown, re.MULTILINE)
    if len(all_sections) >= 3:
        score += 10
    else:
        issues.append(f"Too few sections ({len(all_sections)})")

    return QualityReport(
        score=score,
        has_title=has_title,
        has_metadata_block=has_metadata,
        has_numbered_sections=has_numbered_sections,
        has_placeholders=has_placeholders,
        has_tables=has_tables,
        has_separators=has_separators,
        has_footer=has_footer,
        issues=issues,
    )


def _get_reference_template(doc_type: str) -> str:
    """Load the closest gold-standard reference template for a doc_type."""
    filename = _REFERENCE_MAP.get(doc_type, _DEFAULT_REFERENCE)
    path = TEMPLATES_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Reference template not found: %s", path)
        # Fallback to default
        fallback = TEMPLATES_DIR / _DEFAULT_REFERENCE
        try:
            return fallback.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""


def _get_metadata_hints(filename: str) -> dict:
    """Load metadata hints from the template-metadata JSON files."""
    if not METADATA_DIR.exists():
        return {}

    # Normalize filename to match metadata JSON naming convention
    # e.g., "HHS Streamlined Acquisition Plan Template.docx" →
    #        "HHS_Streamlined_Acquisition_Plan_Template.json"
    stem = Path(filename).stem
    json_name = re.sub(r"[^A-Za-z0-9._-]", "_", stem) + ".json"

    path = METADATA_DIR / json_name
    if not path.exists():
        # Try exact stem match
        for candidate in METADATA_DIR.glob("*.json"):
            if candidate.name.startswith("_"):
                continue
            if candidate.stem.lower().replace("_", "") == stem.lower().replace(
                " ", ""
            ).replace("-", "").replace("_", ""):
                path = candidate
                break

    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _extract_raw_text(body: bytes, content_type: str, filename: str) -> Optional[str]:
    """Extract raw text from document bytes using existing converter."""
    from .document_markdown_service import convert_to_markdown

    return convert_to_markdown(body, content_type, filename)


def _detect_format(filename: str, content_type: str) -> str:
    """Detect source file format from filename/content_type."""
    lower = filename.lower()
    if lower.endswith(".docx"):
        return "docx"
    if lower.endswith(".doc"):
        return "doc"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".xlsx") or lower.endswith(".xls"):
        return "xlsx"
    if lower.endswith(".txt"):
        return "txt"
    if lower.endswith(".md"):
        return "md"

    if "spreadsheet" in content_type or "excel" in content_type:
        return "xlsx"
    if "pdf" in content_type:
        return "pdf"
    if "word" in content_type or "msword" in content_type:
        return "docx"
    return "txt"


# ── Batch Job Tracking ───────────────────────────────────────────────

_batch_jobs: Dict[str, Dict[str, Any]] = {}


@dataclass
class BatchJobResult:
    """Result entry for a single template in a batch job."""

    filename: str
    doc_type: str
    quality_score: float
    success: bool
    issues: list[str] = field(default_factory=list)
    placeholders_found: int = 0
    sections_found: int = 0


def create_batch_job(total: int) -> str:
    """Create a new batch job and return its ID."""
    job_id = str(uuid.uuid4())[:8]
    _batch_jobs[job_id] = {
        "job_id": job_id,
        "status": "processing",
        "created_at": time.time(),
        "total": total,
        "completed": 0,
        "results": [],
        "summary": None,
    }
    return job_id


def update_batch_job(job_id: str, result: BatchJobResult) -> None:
    """Add a result to a batch job."""
    job = _batch_jobs.get(job_id)
    if not job:
        return
    job["results"].append(asdict(result))
    job["completed"] += 1

    # Check if complete
    if job["completed"] >= job["total"]:
        results = job["results"]
        successes = [r for r in results if r["success"]]
        job["status"] = "complete"
        job["summary"] = {
            "total": len(results),
            "success": len(successes),
            "failed": len(results) - len(successes),
            "avg_quality": (
                sum(r["quality_score"] for r in successes) / len(successes)
                if successes
                else 0.0
            ),
        }


def get_batch_job(job_id: str) -> Optional[dict]:
    """Get batch job status."""
    return _batch_jobs.get(job_id)


def mark_batch_error(job_id: str, error: str) -> None:
    """Mark a batch job as failed."""
    job = _batch_jobs.get(job_id)
    if job:
        job["status"] = "error"
        job["error"] = error
