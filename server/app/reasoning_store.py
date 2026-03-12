"""Session-scoped reasoning log accumulator with DynamoDB persistence.

Supports three levels of reasoning entries:
- **Tool-level** (ReasoningEntry): captures tool call decisions
- **Section-level** (SectionEntry): tracks document section omissions/gaps
- **Justification-level** (JustificationEntry): records key acquisition decisions
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

import boto3

logger = logging.getLogger("eagle.reasoning")

_TABLE_NAME: str | None = None
_table = None


def _get_table():
    global _table, _TABLE_NAME
    if _table is None:
        _TABLE_NAME = os.getenv("DYNAMODB_TABLE", "eagle")
        _table = boto3.resource("dynamodb").Table(_TABLE_NAME)
    return _table


@dataclass
class ReasoningEntry:
    timestamp: str
    event_type: str       # "tool_call", "compliance_check", "recommendation"
    tool_name: str
    reasoning: str        # Why this action was taken
    determination: str    # What was decided
    data: dict
    confidence: str       # "high", "medium", "low"


@dataclass
class SectionEntry:
    """Section-level reasoning for document Appendix A (Omissions & Gaps)."""
    section_name: str
    status: str           # "complete", "partial", "omitted", "default"
    reason: str           # Why this status
    info_needed: str      # What would complete this section


@dataclass
class JustificationEntry:
    """Key acquisition decision for document Appendix B (AI Rationale)."""
    decision: str         # e.g., "Contract Type -> FFP"
    reasoning: str        # 2-3 sentence explanation
    far_basis: str        # FAR/HHSAR citation
    confidence: str       # "high", "medium", "low"


class ReasoningLog:
    """Accumulates reasoning entries for a session and persists to DynamoDB."""

    def __init__(self, session_id: str, tenant_id: str, user_id: str):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.entries: list[ReasoningEntry] = []
        self.section_entries: list[SectionEntry] = []
        self.justification_entries: list[JustificationEntry] = []

    def add(
        self,
        event_type: str,
        tool_name: str,
        reasoning: str,
        determination: str,
        data: Optional[dict] = None,
        confidence: str = "high",
    ):
        self.entries.append(ReasoningEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            tool_name=tool_name,
            reasoning=reasoning,
            determination=determination,
            data=data or {},
            confidence=confidence,
        ))

    def add_section(
        self,
        section_name: str,
        status: str,
        reason: str,
        info_needed: str = "",
    ):
        """Add a section-level omission/gap entry for Appendix A."""
        self.section_entries.append(SectionEntry(
            section_name=section_name,
            status=status,
            reason=reason,
            info_needed=info_needed,
        ))

    def add_justification(
        self,
        decision: str,
        reasoning: str,
        far_basis: str = "",
        confidence: str = "high",
    ):
        """Add a key acquisition decision entry for Appendix B."""
        self.justification_entries.append(JustificationEntry(
            decision=decision,
            reasoning=reasoning,
            far_basis=far_basis,
            confidence=confidence,
        ))

    def to_json(self) -> list[dict]:
        return [asdict(e) for e in self.entries]

    def to_full_json(self) -> dict:
        """Serialize all entry types for DynamoDB persistence."""
        return {
            "entries": [asdict(e) for e in self.entries],
            "sections": [asdict(e) for e in self.section_entries],
            "justifications": [asdict(e) for e in self.justification_entries],
        }

    def to_appendix_markdown(self) -> str:
        """Generate the legacy tool-level appendix (backward compat)."""
        if not self.entries:
            return ""
        lines = [
            "\n\n---\n",
            "## Appendix: AI Decision Rationale\n",
            "*This appendix documents the AI-assisted analysis and reasoning "
            "that informed this document. All determinations were made based on "
            "applicable FAR/HHSAR regulations and NCI acquisition policies.*\n",
        ]
        for i, e in enumerate(self.entries, 1):
            ts = e.timestamp[11:19] if len(e.timestamp) > 19 else e.timestamp
            lines.append(f"### {i}. {e.event_type} — {e.tool_name}")
            lines.append(f"**Time:** {ts}  ")
            lines.append(f"**Action:** {e.reasoning}  ")
            lines.append(f"**Determination:** {e.determination}  ")
            if e.confidence:
                lines.append(f"**Confidence:** {e.confidence}  ")
            lines.append("")
        return "\n".join(lines)

    def to_omissions_appendix(self) -> str:
        """Generate Appendix A: Omissions & Information Gaps."""
        if not self.section_entries:
            return ""
        lines = [
            "\n\n---\n",
            "## Appendix A: Omissions & Information Gaps\n",
            "*Sections where specific information was unavailable or inferred.*\n",
            "| Section | Status | Reason | Information Needed |",
            "|---------|--------|--------|-------------------|",
        ]
        for e in self.section_entries:
            lines.append(
                f"| {e.section_name} | {e.status.title()} | {e.reason} | {e.info_needed} |"
            )
        lines.append("")
        return "\n".join(lines)

    def to_justification_appendix(self) -> str:
        """Generate Appendix B: AI Decision Rationale."""
        if not self.justification_entries:
            return ""
        lines = [
            "\n\n---\n",
            "## Appendix B: AI Decision Rationale\n",
            "*Key acquisition decisions and their regulatory basis.*\n",
        ]
        for e in self.justification_entries:
            lines.append(f"**{e.decision}**")
            lines.append(f"{e.reasoning}")
            if e.far_basis:
                lines.append(f"*Basis: {e.far_basis}*")
            if e.confidence:
                lines.append(f"*Confidence: {e.confidence}*")
            lines.append("")
        return "\n".join(lines)

    def save(self):
        """Persist to DynamoDB as REASONING#{session_id}."""
        if not self.entries and not self.section_entries and not self.justification_entries:
            return
        table = _get_table()
        table.put_item(Item={
            "PK": f"SESSION#{self.session_id}",
            "SK": f"REASONING#{self.session_id}",
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "reasoning_entries": json.dumps(self.to_json(), default=str),
            "section_entries": json.dumps(
                [asdict(e) for e in self.section_entries], default=str
            ),
            "justification_entries": json.dumps(
                [asdict(e) for e in self.justification_entries], default=str
            ),
            "entry_count": len(self.entries),
            "section_count": len(self.section_entries),
            "justification_count": len(self.justification_entries),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    @classmethod
    def load(cls, session_id: str, tenant_id: str, user_id: str) -> ReasoningLog:
        """Load from DynamoDB. Returns empty log if not found."""
        log = cls(session_id, tenant_id, user_id)
        try:
            table = _get_table()
            resp = table.get_item(Key={
                "PK": f"SESSION#{session_id}",
                "SK": f"REASONING#{session_id}",
            })
            item = resp.get("Item")
            if not item:
                return log

            # Load tool-level entries
            if item.get("reasoning_entries"):
                entries = json.loads(item["reasoning_entries"])
                for e in entries:
                    log.entries.append(ReasoningEntry(**e))

            # Load section-level entries
            if item.get("section_entries"):
                sections = json.loads(item["section_entries"])
                for s in sections:
                    log.section_entries.append(SectionEntry(**s))

            # Load justification entries
            if item.get("justification_entries"):
                justifications = json.loads(item["justification_entries"])
                for j in justifications:
                    log.justification_entries.append(JustificationEntry(**j))

        except Exception:
            logger.debug("Failed to load reasoning log for session=%s", session_id)
        return log
