"""Intake-approval tools — submit + confirm.

Two `exec_*` handlers wired into ``legacy_dispatch.get_tool_dispatch()``:

* ``exec_submit_intake_for_approval`` — supervisor calls when intake feels
  ready. Snapshots the proposed package scaffolding into
  ``intake_proposed_summary`` so the chat UI can render an
  ``intake_proposal`` card and the user can see exactly what they're
  about to approve.

* ``exec_confirm_intake_approval`` — supervisor calls after the user
  replies. Classifies the free-form reply into approve / revise /
  unclear. On approve, calls ``mark_intake_approved`` (transitions
  intake → drafting and stamps the gate). On revise, returns the
  parsed revisions so the supervisor can update the proposal and
  re-submit. On unclear, returns ``needs_clarification`` so the
  supervisor asks again.

Classifier is regex-first (deterministic, free, fast). The plan
proposed Haiku as a fallback; that can be added later behind a
``EAGLE_INTAKE_CLASSIFIER_MODEL`` env var if the regex mis-classifies
in practice. For v1, ambiguous replies route to ``needs_clarification``
and the supervisor asks the user to confirm explicitly.

PR1.2 of the jolly-snacking-narwhal plan.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..package_store import (
    get_package,
    mark_intake_approved,
    update_package,
)

logger = logging.getLogger("eagle.tools.intake_approval")


# ---------------------------------------------------------------------------
# Free-form classifier
# ---------------------------------------------------------------------------


# Affirmative tokens that are unambiguous on their own. We anchor on word
# boundaries so "approval" doesn't false-fire on the literal word "no".
_APPROVE_PATTERNS = [
    re.compile(r"\b(approve|approved|approving)\b", re.IGNORECASE),
    re.compile(r"\b(confirm|confirmed|confirming)\b", re.IGNORECASE),
    re.compile(r"\b(accept|accepted|accepting)\b", re.IGNORECASE),
    re.compile(r"\b(yes|yep|yeah|yup|sure)\b", re.IGNORECASE),
    re.compile(r"\b(go ahead|go for it|proceed|let's go|ship it)\b", re.IGNORECASE),
    re.compile(r"\b(looks good|sounds good|all good|lgtm)\b", re.IGNORECASE),
    re.compile(r"\b(ok|okay)\b", re.IGNORECASE),
]

# Decline / cancel
_DECLINE_PATTERNS = [
    re.compile(r"\b(no|nope|nah)\b", re.IGNORECASE),
    re.compile(r"\b(cancel|stop|abort|nevermind|never mind)\b", re.IGNORECASE),
    re.compile(r"\b(don'?t|do not)\s+(approve|generate|proceed|create)\b", re.IGNORECASE),
]

# Revise — the user is asking for changes, not approving
_REVISE_PATTERNS = [
    re.compile(r"\b(change|update|edit|revise|modify|fix|adjust)\b", re.IGNORECASE),
    re.compile(r"\b(actually|instead|but)\b.*\b(should|need|want)\b", re.IGNORECASE),
    re.compile(r"\b(set|make|use)\b\s+(?:the\s+)?\w+\s+(?:to|as)\b", re.IGNORECASE),
    re.compile(r"\b(should be|needs to be|has to be)\b", re.IGNORECASE),
]


def _classify_response(user_response: str) -> dict[str, Any]:
    """Return ``{decision: approve|revise|decline|unclear, reason: str}``.

    Decision precedence: revise > decline > approve. Revise wins because
    a reply like "approve, but change the value to $300K" still requires
    a re-proposal. Decline wins over approve unconditionally because the
    decline patterns include negations of approve ("don't approve") — if
    both fire, the decline is the intent.
    """
    if not user_response or not user_response.strip():
        return {"decision": "unclear", "reason": "empty_response"}

    text = user_response.strip()

    revise_hits = [p.pattern for p in _REVISE_PATTERNS if p.search(text)]
    decline_hits = [p.pattern for p in _DECLINE_PATTERNS if p.search(text)]
    approve_hits = [p.pattern for p in _APPROVE_PATTERNS if p.search(text)]

    if revise_hits:
        return {
            "decision": "revise",
            "reason": "revise_pattern_matched",
            "matched": revise_hits,
        }

    if decline_hits:
        return {
            "decision": "decline",
            "reason": "decline_pattern_matched",
            "matched": decline_hits,
        }

    if approve_hits:
        return {
            "decision": "approve",
            "reason": "approve_pattern_matched",
            "matched": approve_hits,
        }

    return {
        "decision": "unclear",
        "reason": "no_pattern_matched",
    }


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def exec_submit_intake_for_approval(
    params: dict[str, Any], tenant_id: str, session_id: str | None = None
) -> dict:
    """Snapshot the proposed package scaffolding and surface it to the user.

    Params:
        package_id: required. Must already exist (call manage_package(create) first).
        summary:    dict — proposed scaffolding fields. The supervisor decides
                    what to include; recommended keys: requirement_description,
                    requirement_type, estimated_value, contract_vehicle,
                    acquisition_method, contract_type, required_documents,
                    key_facts.

    Returns the updated package dict on success, or {"error": ...} on failure.
    The orchestration layer is responsible for emitting the SSE
    ``intake_proposal`` event so the UI can render the proposal card.
    """
    package_id = params.get("package_id")
    if not package_id:
        return {
            "error": "missing_package_id",
            "tool": "submit_intake_for_approval",
            "message": "package_id is required.",
        }

    summary = params.get("summary") or {}
    if not isinstance(summary, dict):
        return {
            "error": "invalid_summary",
            "tool": "submit_intake_for_approval",
            "message": "summary must be a JSON object.",
        }

    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        return {
            "error": "package_not_found",
            "tool": "submit_intake_for_approval",
            "package_id": package_id,
        }

    if pkg.get("intake_approved_at") and pkg.get("intake_approval_source") != "legacy_backfill":
        return {
            "status": "already_approved",
            "tool": "submit_intake_for_approval",
            "package_id": package_id,
            "intake_approved_at": pkg["intake_approved_at"],
            "message": "Package intake is already approved; you can call create_document directly.",
        }

    updated = update_package(
        tenant_id, package_id, {"intake_proposed_summary": summary}
    )
    if updated is None:
        return {
            "error": "update_failed",
            "tool": "submit_intake_for_approval",
            "package_id": package_id,
        }

    return {
        "status": "intake_proposed",
        "package_id": package_id,
        "intake_proposed_summary": summary,
        "next_step": (
            "Present the proposed scaffolding to the user in chat and ask "
            "for explicit confirmation. After they reply, call "
            "confirm_intake_approval(package_id, user_response)."
        ),
    }


def exec_confirm_intake_approval(
    params: dict[str, Any], tenant_id: str, session_id: str | None = None
) -> dict:
    """Classify the user's reply and either stamp the gate or return revisions.

    Params:
        package_id:    required.
        user_response: required. The free-form text the user just sent.
        actor_user_id: required for the audit trail.
        source:        defaults to "user_confirmation"; supervisor passes
                       "slash_bypass" for /document:* auto-approval flows.

    Returns one of:
        {"decision": "approve", "package_id": ..., "intake_approved_at": ..., ...}
        {"decision": "revise",  "package_id": ..., "proposed_summary": ..., ...}
        {"decision": "decline", "package_id": ..., "message": "..."}
        {"decision": "unclear", "package_id": ..., "message": "..."}
    """
    package_id = params.get("package_id")
    if not package_id:
        return {
            "error": "missing_package_id",
            "tool": "confirm_intake_approval",
        }

    actor_user_id = params.get("actor_user_id")
    if not actor_user_id:
        return {
            "error": "missing_actor_user_id",
            "tool": "confirm_intake_approval",
            "message": "actor_user_id is required so the approval can be audited.",
        }

    user_response = params.get("user_response", "")
    source = params.get("source") or "user_confirmation"

    pkg = get_package(tenant_id, package_id)
    if pkg is None:
        return {
            "error": "package_not_found",
            "tool": "confirm_intake_approval",
            "package_id": package_id,
        }

    classification = _classify_response(user_response)
    decision = classification["decision"]

    if decision == "approve":
        summary = pkg.get("intake_proposed_summary") or pkg.get("intake_summary") or {}
        updated = mark_intake_approved(
            tenant_id=tenant_id,
            package_id=package_id,
            user_id=actor_user_id,
            summary=summary,
            source=source,
        )
        if updated is None:
            return {
                "error": "approval_failed",
                "tool": "confirm_intake_approval",
                "package_id": package_id,
            }
        return {
            "decision": "approve",
            "package_id": package_id,
            "intake_approved_at": updated.get("intake_approved_at"),
            "status": updated.get("status"),
            "summary": summary,
            "classifier": classification,
            "next_step": (
                "Intake is now approved. Drafting phase is unlocked. "
                "When generating multiple documents, prefer the batched "
                "path (PR2 — coming soon); single-doc create_document "
                "calls now succeed."
            ),
        }

    if decision == "revise":
        return {
            "decision": "revise",
            "package_id": package_id,
            "proposed_summary": pkg.get("intake_proposed_summary") or {},
            "user_revisions_text": user_response,
            "classifier": classification,
            "next_step": (
                "Apply the user's revisions to the proposed summary, then "
                "call submit_intake_for_approval again with the updated "
                "summary so they can confirm the new version."
            ),
        }

    if decision == "decline":
        return {
            "decision": "decline",
            "package_id": package_id,
            "classifier": classification,
            "message": (
                "User declined approval. Do NOT generate any documents. "
                "Ask the user how they'd like to proceed (revise the "
                "proposal, abandon the package, or continue research)."
            ),
        }

    return {
        "decision": "unclear",
        "package_id": package_id,
        "classifier": classification,
        "message": (
            "Could not interpret the user's reply as approve / revise / "
            "decline. Ask them explicitly: 'Approve this intake summary, "
            "or do you want to change something first?'"
        ),
    }
