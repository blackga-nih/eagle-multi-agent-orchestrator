"""
Feedback triage action callbacks.

Teams adaptive-card buttons (Action.OpenUrl) hit these GET endpoints.
Each endpoint verifies an HMAC signature, updates JIRA + DynamoDB,
and returns a simple HTML confirmation page.

Routes:
    GET /api/feedback/action?action=approve&feedback_id=...&ticket=...&tenant=...&sig=...
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from .. import feedback_store
from ..jira_client import add_comment, transition_issue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback/action", tags=["feedback-actions"])

_SECRET = os.getenv("FEEDBACK_ACTION_SECRET", "eagle-feedback-default-secret")

VALID_ACTIONS = {
    "approve": {
        "label": "Approved",
        "jira_status": "Done",
        "jira_comment": "Feedback approved via Teams triage card.",
        "color": "#2e7d32",
    },
    "reject": {
        "label": "Rejected",
        "jira_status": "Won't Do",
        "jira_comment": "Feedback rejected via Teams triage card.",
        "color": "#c62828",
    },
    "snooze": {
        "label": "Snoozed 24 hr",
        "jira_status": None,  # no transition, just a comment
        "jira_comment": "Feedback snoozed for 24 hours via Teams triage card.",
        "color": "#f57f17",
    },
}


def compute_sig(action: str, feedback_id: str) -> str:
    """HMAC-SHA256 signature for an action URL."""
    msg = f"{action}:{feedback_id}"
    return hmac.new(_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]


def verify_sig(action: str, feedback_id: str, sig: str) -> bool:
    return hmac.compare_digest(sig, compute_sig(action, feedback_id))


def _html_page(title: str, message: str, color: str, detail: str = "") -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: Segoe UI, sans-serif; display: flex; justify-content: center;
         align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }}
  .card {{ background: #fff; border-radius: 8px; padding: 40px 48px; box-shadow: 0 2px 8px rgba(0,0,0,.12);
           text-align: center; max-width: 440px; }}
  .icon {{ font-size: 48px; margin-bottom: 16px; }}
  h1 {{ color: {color}; margin: 0 0 8px; font-size: 22px; }}
  p {{ color: #555; font-size: 14px; margin: 4px 0; }}
  .detail {{ color: #888; font-size: 12px; margin-top: 16px; }}
</style></head><body>
<div class="card">
  <div class="icon">{"&#9989;" if "Approved" in title else "&#10060;" if "Rejected" in title else "&#9200;"}</div>
  <h1>{title}</h1>
  <p>{message}</p>
  {f'<p class="detail">{detail}</p>' if detail else ''}
</div></body></html>"""


@router.get("", response_class=HTMLResponse)
async def handle_feedback_action(
    action: str = Query(...),
    feedback_id: str = Query(...),
    ticket: str = Query(""),
    tenant: str = Query(""),
    sig: str = Query(""),
):
    """Process a feedback triage action from a Teams adaptive card button."""
    # Validate signature
    if not verify_sig(action, feedback_id, sig):
        return HTMLResponse(
            _html_page("Invalid Link", "This action link is invalid or expired.", "#c62828"),
            status_code=403,
        )

    cfg = VALID_ACTIONS.get(action)
    if not cfg:
        return HTMLResponse(
            _html_page("Unknown Action", f"Action '{action}' is not recognized.", "#c62828"),
            status_code=400,
        )

    results: list[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. Update DynamoDB feedback record
    if tenant and feedback_id:
        ok = feedback_store.update_feedback_status(
            feedback_id=feedback_id,
            tenant_id=tenant,
            status=action,
            acted_by="teams-triage",
        )
        results.append(f"Feedback record: {'updated' if ok else 'not found'}")
    else:
        results.append("Feedback record: skipped (no tenant)")

    # 2. Update JIRA ticket
    if ticket:
        # Add comment first (always works)
        add_comment(ticket, f"{cfg['jira_comment']}\n\nTriaged at {ts}")

        # Try transition if configured
        if cfg["jira_status"]:
            transitioned = transition_issue(ticket, cfg["jira_status"])
            results.append(
                f"JIRA {ticket}: {'transitioned to ' + cfg['jira_status'] if transitioned else 'comment added (transition unavailable)'}"
            )
        else:
            results.append(f"JIRA {ticket}: comment added")
    else:
        results.append("JIRA: no ticket linked")

    detail = " | ".join(results)
    logger.info("feedback_action: action=%s feedback=%s ticket=%s — %s", action, feedback_id, ticket, detail)

    return HTMLResponse(
        _html_page(
            f"Feedback {cfg['label']}",
            f"Ticket {ticket}" if ticket else f"Feedback {feedback_id[:8]}...",
            cfg["color"],
            detail=f"{ts} — {detail}",
        )
    )
