"""
Deploy Report — sends pipeline results as an Adaptive Card to Teams.

Called from GitHub Actions after all validation/deploy jobs complete.
Reads job results from environment variables, builds the card, POSTs to Teams.

Usage (from GH Actions):
    python scripts/deploy_report.py

Env vars (set by GH Actions workflow):
    TEAMS_WEBHOOK_URL     — Teams webhook endpoint
    DEPLOY_MODE           — "full" or "mini"
    COMMIT_SHA            — git commit SHA
    BRANCH                — branch name
    AUTHOR                — commit author
    RUN_URL               — GitHub Actions run URL
    PR_URL                — Pull request URL (optional)

    # Job results (from needs.<job>.result)
    RESULT_LINT           — success/failure/skipped
    RESULT_UNIT_TESTS     — success/failure/skipped
    RESULT_CDK_SYNTH      — success/failure/skipped
    RESULT_INTEGRATION    — success/failure/skipped
    RESULT_EVAL           — success/failure/skipped
    RESULT_DEPLOY_INFRA   — success/failure/skipped
    RESULT_DEPLOY_BACKEND — success/failure/skipped
    RESULT_DEPLOY_FRONTEND— success/failure/skipped

    # Job detail outputs (optional)
    DETAIL_LINT           — e.g. "ruff 0 errors, tsc 0 errors"
    DETAIL_UNIT_TESTS     — e.g. "42 passed, 0 failed"
    DETAIL_EVAL           — e.g. "30/34 passed"
    DETAIL_MVP1           — JSON array of MVP1 results
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Allow import from repo root
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from server.app.teams_cards import deploy_report_card  # noqa: E402


def _status(env_key: str) -> str:
    """Map GH Actions job result to report status."""
    val = os.getenv(env_key, "skipped").lower()
    if val == "success":
        return "PASS"
    if val == "skipped":
        return "SKIP"
    return "FAIL"


def main():
    webhook_url = os.getenv(
        "TEAMS_WEBHOOK_URL",
        os.getenv("ERROR_WEBHOOK_URL", ""),
    )
    if not webhook_url:
        print("[Deploy Report] No TEAMS_WEBHOOK_URL set, skipping notification")
        return 0

    deploy_mode = os.getenv("DEPLOY_MODE", "full")
    commit_sha = os.getenv("COMMIT_SHA", "unknown")
    branch = os.getenv("BRANCH", "main")
    author = os.getenv("AUTHOR", "unknown")
    run_url = os.getenv("RUN_URL", "")
    pr_url = os.getenv("PR_URL", "")

    # Build validation ladder results
    results = [
        {"level": "L1", "name": "Lint", "status": _status("RESULT_LINT"), "detail": os.getenv("DETAIL_LINT", "")},
        {"level": "L2", "name": "Unit Tests", "status": _status("RESULT_UNIT_TESTS"), "detail": os.getenv("DETAIL_UNIT_TESTS", "")},
        {"level": "L4", "name": "CDK Synth", "status": _status("RESULT_CDK_SYNTH"), "detail": ""},
        {"level": "L5", "name": "Integration", "status": _status("RESULT_INTEGRATION"), "detail": ""},
        {"level": "L6", "name": "Eval", "status": _status("RESULT_EVAL"), "detail": os.getenv("DETAIL_EVAL", "")},
    ]

    # MVP1 results (JSON from eval job)
    mvp1_raw = os.getenv("DETAIL_MVP1", "[]")
    try:
        mvp1_results = json.loads(mvp1_raw)
    except json.JSONDecodeError:
        mvp1_results = []

    # Deploy status
    deploy_status = {
        "infra": _status("RESULT_DEPLOY_INFRA"),
        "backend": _status("RESULT_DEPLOY_BACKEND"),
        "frontend": _status("RESULT_DEPLOY_FRONTEND"),
    }

    # Jira summary (optional, from env)
    jira_raw = os.getenv("JIRA_SUMMARY", "[]")
    try:
        jira_summary = json.loads(jira_raw)
    except json.JSONDecodeError:
        jira_summary = []

    environment = os.getenv("EAGLE_ENV", "dev")

    card = deploy_report_card(
        environment=environment,
        deploy_mode=deploy_mode,
        commit_sha=commit_sha,
        branch=branch,
        author=author,
        results=results,
        mvp1_results=mvp1_results,
        jira_summary=jira_summary,
        deploy_status=deploy_status,
        run_url=run_url,
        pr_url=pr_url,
    )

    print(f"[Deploy Report] Env={environment} Mode={deploy_mode} SHA={commit_sha[:10]} Branch={branch}")
    print(f"[Deploy Report] Sending to Teams...")
    resp = httpx.post(webhook_url, json=card, timeout=10)
    print(f"[Deploy Report] Status: {resp.status_code}")

    if resp.status_code >= 300:
        print(f"[Deploy Report] Response: {resp.text[:200]}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
