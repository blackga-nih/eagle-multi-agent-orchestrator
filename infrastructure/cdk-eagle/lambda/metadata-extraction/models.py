"""Document metadata model using stdlib dataclasses — no native extension dependencies."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentMetadata:
    """Metadata extracted from a government acquisition document."""

    # Core identifiers
    document_id: str
    file_name: str
    file_type: str
    file_size_bytes: int
    s3_bucket: str
    s3_key: str

    # Extracted by LLM (Claude via Bedrock)
    title: str = ""
    summary: str = ""
    document_type: str = "unknown"  # regulation|guidance|policy|template|memo|checklist|reference
    primary_topic: str = "general"  # funding|compliance|market_research|contract_types|etc.
    primary_agent: str = "supervisor"  # supervisor-core|financial-advisor|legal-counselor|etc.
    keywords: List[str] = field(default_factory=list)
    agencies: List[str] = field(default_factory=list)
    far_references: List[str] = field(default_factory=list)
    confidence_score: float = 0.0

    # New: Routing & discovery fields
    related_topics: List[str] = field(default_factory=list)
    relevant_agents: List[str] = field(default_factory=list)
    key_requirements: List[str] = field(default_factory=list)  # 3-5 main requirements
    section_summaries: Dict[str, str] = field(default_factory=dict)  # section_name -> summary

    # New: Regulatory references
    statute_references: List[str] = field(default_factory=list)  # USC citations
    agency_references: List[str] = field(default_factory=list)  # DFARS, HHSAR, etc.
    authority_level: str = "guidance"  # statute|regulation|policy|guidance|internal
    source_agency: str = ""  # FAR|GSA|OMB|DOD|GAO|HHS|NIH|Agency-specific

    # New: Discovery & audience
    complexity_level: str = "intermediate"  # basic|intermediate|advanced
    audience: List[str] = field(default_factory=list)  # contracting_officer|legal_counsel|etc.

    # New: Temporal fields
    effective_date: str = ""  # ISO 8601
    expiration_date: str = ""  # ISO 8601 or empty
    fiscal_year: int = 0  # YYYY

    # New: File metrics (computed, not extracted)
    word_count: int = 0
    page_count: int = 0
    file_size_kb: int = 0

    # New: Catalog tracking
    catalog_version: str = "1.0"
    added_to_catalog: str = field(default_factory=_now_iso)
    last_validated: str = field(default_factory=_now_iso)

    # Timestamps
    upload_date: str = field(default_factory=_now_iso)
    last_updated: str = field(default_factory=_now_iso)
    extraction_model: str = ""

    def model_dump(self) -> dict:
        """Return dict representation (pydantic-compatible API)."""
        return asdict(self)

    def to_dynamo_item(self) -> dict:
        """Convert to DynamoDB-compatible dict with string-typed confidence_score."""
        data = self.model_dump()
        data["confidence_score"] = str(data["confidence_score"])
        return data
