"""
Triage plan action callbacks.

Teams adaptive-card buttons (Action.OpenUrl) hit these GET endpoints.
Each endpoint verifies an HMAC signature, updates JIRA labels,
optionally fires a GitHub repository_dispatch, and returns an HTML page.

Routes:
    GET /api/triage/action?action=approve&triage_id=...&ticket=...&sig=...
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from ..jira_client import add_comment, update_labels

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triage/action", tags=["triage-actions"])

_SECRET = os.getenv("FEEDBACK_ACTION_SECRET", "eagle-feedback-default-secret")
_GH_TOKEN = os.getenv("GH_DISPATCH_TOKEN", "")
_GH_REPO = os.getenv("GITHUB_REPO", "CBIIT/sm_eagle")

VALID_ACTIONS = {
    "approve": {
        "label": "Approved",
        "jira_label": "triage-approved",
        "jira_comment": "Triage plan approved via Teams. Triggering implementation workflow.",
        "github_dispatch": True,
        "color": "#2e7d32",
    },
    "deny": {
        "label": "Denied",
        "jira_label": "triage-denied",
        "jira_comment": "Triage plan denied via Teams.",
        "github_dispatch": False,
        "color": "#c62828",
    },
    "delay": {
        "label": "Delayed 24hr",
        "jira_label": "triage-delayed",
        "jira_comment": "Triage plan delayed 24 hours via Teams.",
        "github_dispatch": False,
        "color": "#f57f17",
    },
}


def compute_sig(action: str, triage_id: str) -> str:
    """HMAC-SHA256 signature for a triage action URL."""
    msg = f"triage:{action}:{triage_id}"
    return hmac.new(_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:16]


def verify_sig(action: str, triage_id: str, sig: str) -> bool:
    return hmac.compare_digest(sig, compute_sig(action, triage_id))


def _dispatch_github(event_type: str, jira_key: str, triage_id: str) -> bool:
    """Fire a repository_dispatch event to GitHub. Returns True on success."""
    if not _GH_TOKEN:
        logger.warning("triage_actions: GH_DISPATCH_TOKEN not set, skipping dispatch")
        return False

    try:
        resp = httpx.post(
            f"https://api.github.com/repos/{_GH_REPO}/dispatches",
            headers={
                "Authorization": f"token {_GH_TOKEN}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "event_type": event_type,
                "client_payload": {
                    "jira_key": jira_key,
                    "triage_id": triage_id,
                },
            },
            timeout=10,
        )
        ok = resp.status_code in (200, 204)
        if ok:
            logger.info("triage_actions: dispatched %s to %s", event_type, _GH_REPO)
        else:
            logger.warning(
                "triage_actions: dispatch failed status=%d body=%s",
                resp.status_code,
                resp.text[:200],
            )
        return ok
    except Exception:
        logger.warning("triage_actions: dispatch failed", exc_info=True)
        return False


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
  <div class="icon">{"&#9989;" if "Approved" in title else "&#10060;" if "Denied" in title else "&#9200;"}</div>
  <h1>{title}</h1>
  <p>{message}</p>
  {f'<p class="detail">{detail}</p>' if detail else ''}
</div></body></html>"""


@router.get("", response_class=HTMLResponse)
async def handle_triage_action(
    action: str = Query(...),
    triage_id: str = Query(...),
    ticket: str = Query(""),
    sig: str = Query(""),
):
    """Process a triage plan action from a Teams adaptive card button."""
    if not verify_sig(action, triage_id, sig):
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

    # 1. Update JIRA labels + comment
    if ticket:
        update_labels(ticket, add=[cfg["jira_label"]])
        add_comment(ticket, f"{cfg['jira_comment']}\n\nTriaged at {ts}")
        results.append(f"JIRA {ticket}: label '{cfg['jira_label']}' added")
    else:
        results.append("JIRA: no ticket linked")

    # 2. Fire GitHub dispatch if configured
    if cfg["github_dispatch"]:
        dispatched = _dispatch_github("triage-approved", ticket, triage_id)
        results.append(f"GitHub dispatch: {'sent' if dispatched else 'failed or not configured'}")

    detail = " | ".join(results)
    logger.info(
        "triage_action: action=%s triage_id=%s ticket=%s — %s",
        action, triage_id, ticket, detail,
    )

    return HTMLResponse(
        _html_page(
            f"Triage Plan {cfg['label']}",
            f"Ticket {ticket}" if ticket else f"Triage {triage_id[:8]}...",
            cfg["color"],
            detail=f"{ts} — {detail}",
        )
    )
