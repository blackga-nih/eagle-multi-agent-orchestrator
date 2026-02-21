"""Document metadata model using stdlib dataclasses — no native extension dependencies."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentMetadata:
    """Metadata extracted from a government acquisition document."""

    document_id: str
    file_name: str
    file_type: str
    file_size_bytes: int
    s3_bucket: str
    s3_key: str

    # Extracted by Gemini
    title: str = ""
    summary: str = ""
    document_type: str = "unknown"
    primary_topic: str = "general"
    primary_agent: str = "supervisor"
    keywords: List[str] = field(default_factory=list)
    agencies: List[str] = field(default_factory=list)
    far_references: List[str] = field(default_factory=list)
    confidence_score: float = 0.0

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
