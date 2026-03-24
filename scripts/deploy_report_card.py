"""
Deploy Report Card CLI — sends a deploy report card to Teams from local runs.

Used by the /ship command to send notifications after local validation.

Usage:
    python scripts/deploy_report_card.py --results '{"L1": "PASS", ...}' --pr-url "https://..."
    python scripts/deploy_report_card.py --results-file results.json
    python scripts/deploy_report_card.py --dry-run --results '...'

Env vars:
    TEAMS_WEBHOOK_URL — Teams webhook endpoint (or ERROR_WEBHOOK_URL fallback)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from server.app.teams_cards import deploy_report_card  # noqa: E402


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description="Send deploy report card to Teams")
    parser.add_argument("--results", default=None, help="JSON string of validation results")
    parser.add_argument("--results-file", default=None, help="Path to JSON file with results")
    parser.add_argument("--mvp1-results", default=None, help="JSON string of MVP1 eval results")
    parser.add_argument("--jira-summary", default=None, help="JSON string of Jira actions")
    parser.add_argument("--pr-url", default="", help="PR URL")
    parser.add_argument("--deploy-mode", default="full", help="Deploy mode: full or mini")
    parser.add_argument("--dry-run", action="store_true", help="Print card JSON without sending")
    args = parser.parse_args()

    # Load results
    if args.results_file:
        with open(args.results_file) as f:
            data = json.load(f)
    elif args.results:
        data = json.loads(args.results)
    else:
        data = {}

    # Build validation results from data
    results = []
    level_map = {
        "L1": "Lint", "L2": "Unit Tests", "L4": "CDK Synth",
        "L5": "Integration", "L6": "Eval",
    }
    for level, name in level_map.items():
        val = data.get(level, data.get(level.lower(), "SKIP"))
        if isinstance(val, dict):
            results.append({"level": level, "name": name, "status": val.get("status", "SKIP"), "detail": val.get("detail", "")})
        else:
            results.append({"level": level, "name": name, "status": str(val).upper(), "detail": ""})

    # MVP1
    mvp1_results = []
    if args.mvp1_results:
        mvp1_results = json.loads(args.mvp1_results)

    # Jira
    jira_summary = []
    if args.jira_summary:
        jira_summary = json.loads(args.jira_summary)

    # Deploy status (from data or default to SKIP)
    deploy_status = data.get("deploy", {"infra": "SKIP", "backend": "SKIP", "frontend": "SKIP"})

    # Git info
    commit_sha = _git(["rev-parse", "HEAD"])
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    author = _git(["log", "-1", "--format=%an"])

    card = deploy_report_card(
        environment="dev",
        deploy_mode=args.deploy_mode,
        commit_sha=commit_sha,
        branch=branch,
        author=author,
        results=results,
        mvp1_results=mvp1_results,
        jira_summary=jira_summary,
        deploy_status=deploy_status,
        run_url="",
        pr_url=args.pr_url,
    )

    if args.dry_run:
        print(json.dumps(card, indent=2))
        return 0

    webhook_url = os.getenv(
        "TEAMS_WEBHOOK_URL",
        os.getenv("ERROR_WEBHOOK_URL", ""),
    )
    if not webhook_url:
        print("[Deploy Card] No TEAMS_WEBHOOK_URL set — printing card JSON instead")
        print(json.dumps(card, indent=2))
        return 0

    print(f"[Deploy Card] Sending report to Teams...")
    resp = httpx.post(webhook_url, json=card, timeout=10)
    print(f"[Deploy Card] Status: {resp.status_code}")
    if resp.status_code >= 300:
        print(f"[Deploy Card] Response: {resp.text[:200]}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
