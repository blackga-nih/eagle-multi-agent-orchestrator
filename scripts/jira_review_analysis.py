"""
Jira Review Analysis — match recent commits to open Jira issues and suggest transitions.

Fetches open EAGLE issues, gets recent git commits, matches via EAGLE-\\d+ regex,
and suggests status transitions (e.g., move to Done if commits indicate completion).

Usage:
    python scripts/jira_review_analysis.py                          # last 7 days
    python scripts/jira_review_analysis.py --since "3 days ago"
    python scripts/jira_review_analysis.py --dry-run                # no API calls
    python scripts/jira_review_analysis.py --json                   # output as JSON

Env vars:
    JIRA_BASE_URL   — Jira server URL
    JIRA_API_TOKEN  — Personal Access Token
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

try:
    from scripts.jira_connect import fetch_open_issues, get_transitions
except ImportError:
    from jira_connect import fetch_open_issues, get_transitions  # noqa: E402


ISSUE_PATTERN = re.compile(r"\bEAGLE-\d+\b", re.IGNORECASE)

# Keywords in commit messages that suggest completion
COMPLETION_KEYWORDS = [
    "fix", "implement", "add", "complete", "resolve", "close", "finish",
    "wire", "integrate", "deploy", "ship",
]


def _git(args: list[str]) -> str:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, timeout=30, cwd=repo_root,
    )
    return result.stdout.strip()


def get_recent_commits(since: str) -> list[dict]:
    """Get commits since a given time period."""
    log = _git([
        "log", f"--since={since}", "--format=%H|%an|%s",
        "--no-merges",
    ])
    if not log:
        return []

    commits = []
    for line in log.strip().split("\n"):
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        sha, author, message = parts
        commits.append({"sha": sha, "author": author, "message": message})
    return commits


def match_commits_to_issues(commits: list[dict], issues: list[dict]) -> dict:
    """Match commits mentioning EAGLE-XXX to open issues.

    Returns dict keyed by issue key with list of matching commits and suggested action.
    """
    issue_map = {i["key"]: i for i in issues}
    matches = {}

    for commit in commits:
        keys = ISSUE_PATTERN.findall(commit["message"])
        for key in keys:
            key_upper = key.upper()
            if key_upper not in matches:
                matches[key_upper] = {
                    "issue": issue_map.get(key_upper),
                    "commits": [],
                    "suggestion": None,
                }
            matches[key_upper]["commits"].append(commit)

    # Determine suggestions
    for key, data in matches.items():
        commit_msgs = " ".join(c["message"].lower() for c in data["commits"])
        has_completion = any(kw in commit_msgs for kw in COMPLETION_KEYWORDS)

        if data["issue"]:
            status = data["issue"].get("status", "").lower()
            if has_completion and status not in ("done", "closed"):
                data["suggestion"] = "transition_done"
            else:
                data["suggestion"] = "add_comment"
        else:
            # Issue key in commit but not in open issues (may already be done)
            data["suggestion"] = "already_closed_or_missing"

    return matches


def analyze(since: str, project_key: str, dry_run: bool = False) -> list[dict]:
    """Run the full analysis and return suggestions."""
    print(f"[Jira Analysis] Fetching open issues for {project_key}...")
    if dry_run:
        issues = []
        print(f"[Jira Analysis] Dry run — skipping Jira API calls")
    else:
        issues = fetch_open_issues(project_key)
    print(f"[Jira Analysis] Found {len(issues)} open issues")

    print(f"[Jira Analysis] Fetching commits since '{since}'...")
    commits = get_recent_commits(since)
    print(f"[Jira Analysis] Found {len(commits)} commits")

    matches = match_commits_to_issues(commits, issues)

    suggestions = []
    for key, data in sorted(matches.items()):
        commit_shas = [c["sha"][:7] for c in data["commits"]]
        commit_msgs = [c["message"][:80] for c in data["commits"]]
        issue_summary = data["issue"]["summary"] if data["issue"] else "(not found in open issues)"
        issue_status = data["issue"]["status"] if data["issue"] else "unknown"

        suggestion = {
            "key": key,
            "summary": issue_summary,
            "current_status": issue_status,
            "commits": commit_shas,
            "commit_messages": commit_msgs,
            "action": data["suggestion"],
        }

        # Get available transitions if not dry run
        if not dry_run and data["issue"] and data["suggestion"] == "transition_done":
            transitions = get_transitions(key)
            suggestion["available_transitions"] = [t["name"] for t in transitions]

        suggestions.append(suggestion)

    return suggestions


def main():
    parser = argparse.ArgumentParser(description="Analyze Jira issues vs recent commits")
    parser.add_argument("--since", default="7 days ago", help="Git log --since value")
    parser.add_argument("--project", default=os.getenv("JIRA_PROJECT", "EAGLE"), help="Jira project key")
    parser.add_argument("--dry-run", action="store_true", help="Skip Jira API calls")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.dry_run and (not os.getenv("JIRA_BASE_URL") or not os.getenv("JIRA_API_TOKEN")):
        print("Set JIRA_BASE_URL and JIRA_API_TOKEN in env or .env", file=sys.stderr)
        sys.exit(1)

    suggestions = analyze(args.since, args.project, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(suggestions, indent=2))
        return

    if not suggestions:
        print("\n[Jira Analysis] No commit-to-issue matches found.")
        return

    print(f"\n{'='*60}")
    print(f"  Jira Review Analysis — {len(suggestions)} issue(s) matched")
    print(f"{'='*60}\n")

    for s in suggestions:
        action_label = {
            "transition_done": "SUGGEST: Transition to Done",
            "add_comment": "SUGGEST: Add commit summary comment",
            "already_closed_or_missing": "INFO: Issue already closed or not found",
        }.get(s["action"], s["action"])

        print(f"  [{s['key']}] {s['summary']}")
        print(f"    Status: {s['current_status']}")
        print(f"    Commits: {', '.join(s['commits'])}")
        print(f"    Action: {action_label}")
        if s.get("available_transitions"):
            print(f"    Transitions: {', '.join(s['available_transitions'])}")
        print()


if __name__ == "__main__":
    main()
