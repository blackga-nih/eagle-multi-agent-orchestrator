"""
Triage Notification Script — creates JIRA issue, attaches plan, posts Teams card.

Called from the nightly-triage GitHub Actions workflow after the triage plan
is generated and committed. Posts a collapsible adaptive card with
Approve / Deny / Delay 24hr buttons to the triage Teams channel.

Usage:
    python scripts/triage_notify.py \
      --plan-file .claude/specs/20260401-...-plan-triage-fixes-dev-v1.md \
      --env dev

    python scripts/triage_notify.py --plan-file plan.md --env dev --dry-run

Env vars:
    JIRA_BASE_URL          — JIRA server URL
    JIRA_API_TOKEN         — JIRA Personal Access Token
    JIRA_PROJECT           — project key (default: EAGLE)
    TEAMS_TRIAGE_WEBHOOK_URL — Teams webhook for the triage channel
    EAGLE_BACKEND_URL      — backend URL for action callback links
    FEEDBACK_ACTION_SECRET — shared HMAC secret (must match backend)
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from server.app.teams_cards import triage_plan_card  # noqa: E402

# ── JIRA helpers (standalone — no server dependency) ────────────────────

_JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
_JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
_JIRA_PROJECT = os.getenv("JIRA_PROJECT", "EAGLE")
_JIRA_TIMEOUT = 10.0


def _jira_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_JIRA_API_TOKEN}",
        "Content-Type": "application/json",
    }


def create_triage_issue(env: str, date: str, plan_summary: str) -> str | None:
    """Create a JIRA issue for a triage run. Returns issue key or None."""
    if not _JIRA_BASE_URL or not _JIRA_API_TOKEN:
        print("[Triage] JIRA not configured, skipping issue creation")
        return None

    summary = f"[Triage] Nightly Fix Plan \u2014 {env} \u2014 {date}"
    description = (
        f"Auto-generated nightly triage fix plan for *{env}* environment.\n\n"
        f"Date: {date}\n\n"
        f"{{noformat}}\n{plan_summary[:2000]}\n{{noformat}}"
    )

    payload = {
        "fields": {
            "project": {"key": _JIRA_PROJECT},
            "summary": summary[:255],
            "issuetype": {"name": "Task"},
            "description": description,
            "labels": ["triage", "auto-created", env],
        }
    }

    try:
        resp = httpx.post(
            f"{_JIRA_BASE_URL}/rest/api/2/issue",
            headers=_jira_headers(),
            json=payload,
            timeout=_JIRA_TIMEOUT,
        )
        if resp.status_code in (200, 201):
            key = resp.json().get("key")
            print(f"[Triage] Created JIRA issue: {key}")
            return key
        print(f"[Triage] JIRA create failed: {resp.status_code} {resp.text[:200]}")
        return None
    except Exception as e:
        print(f"[Triage] JIRA create error: {e}")
        return None


def attach_file_to_issue(issue_key: str, filename: str, content: bytes) -> bool:
    """Attach a file to a JIRA issue."""
    if not _JIRA_BASE_URL or not _JIRA_API_TOKEN:
        return False

    headers = {
        "Authorization": f"Bearer {_JIRA_API_TOKEN}",
        "X-Atlassian-Token": "no-check",
    }

    try:
        resp = httpx.post(
            f"{_JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/attachments",
            headers=headers,
            files={"file": (filename, content, "application/octet-stream")},
            timeout=_JIRA_TIMEOUT,
        )
        ok = resp.status_code in (200, 201)
        if ok:
            print(f"[Triage] Attached {filename} to {issue_key}")
        else:
            print(f"[Triage] Attachment failed: {resp.status_code} {resp.text[:200]}")
        return ok
    except Exception as e:
        print(f"[Triage] Attachment error: {e}")
        return False


# ── Plan parsing helpers ────────────────────────────────────────────────


def _count_priorities(plan_text: str) -> tuple[int, int, int]:
    """Extract P1/P2/P3 counts from the plan text."""
    p1 = len(re.findall(r"\bP1\b", plan_text, re.IGNORECASE))
    p2 = len(re.findall(r"\bP2\b", plan_text, re.IGNORECASE))
    p3 = len(re.findall(r"\bP3\b", plan_text, re.IGNORECASE))
    return p1, p2, p3


# ── Main ────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Post triage plan to JIRA + Teams")
    parser.add_argument("--plan-file", required=True, help="Path to triage plan MD")
    parser.add_argument("--report-file", default="", help="Path to triage report MD")
    parser.add_argument("--env", required=True, help="Environment (dev or qa)")
    parser.add_argument("--dry-run", action="store_true", help="Print card JSON without posting")
    args = parser.parse_args()

    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        print(f"[Triage] Plan file not found: {plan_path}")
        return 1

    plan_text = plan_path.read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    triage_id = str(uuid.uuid4())[:8]
    p1, p2, p3 = _count_priorities(plan_text)

    # 1. Create JIRA issue
    jira_key = create_triage_issue(args.env, today, plan_text)

    # 2. Attach plan MD to JIRA issue
    if jira_key:
        attach_file_to_issue(jira_key, plan_path.name, plan_text.encode("utf-8"))

        # Also attach report if provided
        if args.report_file:
            report_path = Path(args.report_file)
            if report_path.exists():
                report_content = report_path.read_text(encoding="utf-8")
                attach_file_to_issue(jira_key, report_path.name, report_content.encode("utf-8"))

    # 3. Build adaptive card
    card = triage_plan_card(
        environment=args.env,
        date=today,
        plan_text=plan_text,
        p1_count=p1,
        p2_count=p2,
        p3_count=p3,
        jira_key=jira_key,
        triage_id=triage_id,
        plan_file=str(plan_path),
    )

    if args.dry_run:
        print(json.dumps(card, indent=2))
        return 0

    # 4. Post to Teams triage webhook
    webhook_url = os.getenv("TEAMS_TRIAGE_WEBHOOK_URL", "")
    if not webhook_url:
        print("[Triage] TEAMS_TRIAGE_WEBHOOK_URL not set — printing card JSON instead")
        print(json.dumps(card, indent=2))
        return 0

    print("[Triage] Sending card to Teams triage channel...")
    try:
        resp = httpx.post(webhook_url, json=card, timeout=10)
        print(f"[Triage] Teams response: {resp.status_code}")
        if resp.status_code >= 300:
            print(f"[Triage] Response body: {resp.text[:200]}")
            return 1
    except Exception as e:
        print(f"[Triage] Teams POST failed: {e}")
        return 1

    print(f"[Triage] Done. JIRA={jira_key or 'N/A'} triage_id={triage_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
