"""
eagle_state.py — EAGLE Unified Agent State Module

Single source of truth for the supervisor agent_state schema.

To add a new state field:
  1. Add it to _DEFAULTS with a safe default value
  2. Optionally handle it in apply_event() if it's mutation-driven
  3. Optionally project it in to_trace_attrs() / to_cw_payload()

That's it. normalize() guarantees the field exists everywhere automatically.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("eagle.state")

# ── Schema version ────────────────────────────────────────────────────
SCHEMA_VERSION = "1.0"

# ── Canonical defaults ────────────────────────────────────────────────
# THIS IS THE ONLY PLACE THAT DEFINES THE STATE SCHEMA.
# Add new fields here. normalize() fills them in everywhere automatically.
_DEFAULTS: dict = {
    "schema_version": SCHEMA_VERSION,
    "phase": "intake",             # intake | analysis | drafting | review | complete
    "previous_phase": None,
    "package_id": None,            # PKG-YYYY-NNNN
    "required_documents": [],      # ["sow", "igce", "market_research", ...]
    "completed_documents": [],     # subset of required that are done
    "document_versions": {},       # {doc_type: {document_id, version, s3_key}}
    "compliance_alerts": [],       # [{severity, items: [{name, note}]}]
    "validation_results": [],      # [{doc_type, action, reason, far_citation}]
    "turn_count": 0,
    "last_updated": None,          # ISO-8601
    "session_id": None,
    "specialist_summaries": {},    # {skill_name: truncated_text[:3000]} — persists across turns
}


# ── normalize ─────────────────────────────────────────────────────────

def normalize(state: dict | None) -> dict:
    """Return a state dict with all expected keys present.

    - Missing keys are filled from _DEFAULTS (forward/backward compat)
    - Unknown keys are preserved (additive schema changes are safe)
    - Never mutates the input dict
    """
    out = dict(_DEFAULTS)
    if state:
        out.update(state)
    return out


# ── apply_event ───────────────────────────────────────────────────────

def apply_event(state: dict, state_type: str, params: dict) -> dict:
    """Apply a single update_state event to state. Pure — never mutates input.

    Returns a new normalized state dict with the event applied.
    Single source of truth for how each state_type changes state.
    """
    s = normalize(dict(state))

    if state_type == "phase_change":
        s["previous_phase"] = s["phase"]
        s["phase"] = params.get("phase", s["phase"])
        s["package_id"] = params.get("package_id") or s["package_id"]

    elif state_type == "document_ready":
        doc_type = params.get("doc_type")
        if doc_type and doc_type not in s["completed_documents"]:
            s["completed_documents"] = s["completed_documents"] + [doc_type]
        if doc_type:
            s["document_versions"] = {
                **s["document_versions"],
                doc_type: {
                    "document_id": params.get("document_id"),
                    "version": params.get("version"),
                    "s3_key": params.get("s3_key"),
                },
            }
        s["package_id"] = params.get("package_id") or s["package_id"]

    elif state_type == "checklist_update":
        cl = params.get("checklist", {})
        if cl:
            s["required_documents"] = cl.get("required", s["required_documents"])
            s["completed_documents"] = cl.get("completed", s["completed_documents"])
        s["package_id"] = params.get("package_id") or s["package_id"]

    elif state_type == "compliance_alert":
        s["compliance_alerts"] = s["compliance_alerts"] + [{
            "severity": params.get("severity"),
            "items": params.get("items", []),
        }]

    elif state_type == "document_validation":
        s["validation_results"] = s.get("validation_results", []) + [{
            "doc_type": params.get("doc_type"),
            "action": params.get("action"),
            "reason": params.get("reason"),
            "far_citation": params.get("far_citation", ""),
        }]

    else:
        logger.warning("eagle_state.apply_event: unknown state_type=%r", state_type)

    return s


# ── Read projections ──────────────────────────────────────────────────

def to_trace_attrs(
    state: dict,
    *,
    tenant_id: str,
    user_id: str,
    tier: str,
    session_id: str,
) -> dict:
    """Build trace_attributes dict for Langfuse/OTEL Agent() constructor.

    Add new Langfuse span attributes here — nowhere else.
    """
    s = normalize(state)
    return {
        "eagle.tenant_id": tenant_id,
        "eagle.user_id": user_id,
        "eagle.tier": tier,
        "eagle.session_id": session_id or "",
        "eagle.phase": s["phase"],
        "eagle.package_id": s["package_id"] or "",
        "eagle.docs_required": len(s["required_documents"]),
        "eagle.docs_completed": len(s["completed_documents"]),
        "eagle.turn_count": s["turn_count"],
        # Langfuse uses session.id to group supervisor + subagent traces into one Session view
        "session.id": session_id or "",
    }


def to_cw_payload(state: dict) -> dict:
    """Build CloudWatch data payload for agent.state_flush events.

    Add new CloudWatch fields here — nowhere else.
    """
    s = normalize(state)
    return {
        "schema_version": s["schema_version"],
        "phase": s["phase"],
        "previous_phase": s["previous_phase"],
        "package_id": s["package_id"],
        "docs_required": len(s["required_documents"]),
        "docs_completed": len(s["completed_documents"]),
        "completed_documents": s["completed_documents"],
        "compliance_alert_count": len(s["compliance_alerts"]),
        "validation_count": len(s.get("validation_results", [])),
        "blocked_count": sum(
            1 for r in s.get("validation_results", []) if r.get("action") == "block"
        ),
        "turn_count": s["turn_count"],
    }


# ── Stamp ─────────────────────────────────────────────────────────────

def stamp(state: dict) -> dict:
    """Return state with last_updated set to now (UTC ISO-8601). Pure."""
    s = normalize(dict(state))
    s["last_updated"] = datetime.now(timezone.utc).isoformat()
    return s
