"""
Fetch open Jira issues and recent unmatched commits, output structured JSON for Claude.

This script is the data-collection half of the agentic Jira commit-to-issue matching
workflow. It fetches open issues (filtered to specific assignees) and recent commits
that don't already reference a Jira issue key, then outputs a JSON payload that the
jira-commit-matcher skill consumes for semantic matching.

Usage:
  # Standard (outputs JSON to stdout)
  python scripts/jira_scan_issues.py --project EAGLE --assignees "blackga,Greg Black" --since "7 days ago"

  # Dry-run (validates connectivity, prints summary instead of JSON)
  python scripts/jira_scan_issues.py --dry-run --project EAGLE --assignees "blackga,Greg Black"

Requires: JIRA_BASE_URL, JIRA_API_TOKEN in env (or .env).
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
    from scripts.jira_connect import fetch_open_issues, fetch_board_issues
except ImportError:
    from jira_connect import fetch_open_issues, fetch_board_issues


def issue_keys_in_message(project_key: str, message: str) -> list[str]:
    """Extract Jira issue keys (e.g. EAGLE-42) from a commit message."""
    pattern = re.compile(rf"\b{re.escape(project_key)}-\d+\b", re.IGNORECASE)
    return list(dict.fromkeys(pattern.findall(message)))


def get_recent_commits(since: str, branch: str = "HEAD", author: str | None = None) -> list[dict]:
    """Fetch recent commits via git log. Returns list of {sha, subject, body, author}."""
    fmt = ["-z", "--format=%H%n%s%n%b%n---AUTHOR---%n%an"]

    # Build author args (support comma-separated)
    author_patterns = []
    if author:
        author_patterns = [p.strip() for p in author.split(",") if p.strip()]

    def _run_log(author_pat: str | None) -> list[dict]:
        author_arg = [f"--author={author_pat}"] if author_pat else []
        if since == "24h" or since == "24 hours":
            cmd = ["git", "log"] + fmt + author_arg + ["--since=24 hours ago", branch]
        elif any(x in since.lower() for x in ("hour", "day", "week", "month", "year", "ago")):
            cmd = ["git", "log"] + fmt + author_arg + [f"--since={since}", branch]
        else:
            cmd = ["git", "log"] + fmt + author_arg + [f"{since}..{branch}"]
        result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, shell=False)
        if result.returncode != 0:
            return []
        out = (result.stdout or "").strip()
        if not out:
            return []
        commits = []
        for block in out.split("\0"):
            if not block.strip():
                continue
            parts = block.split("\n---AUTHOR---\n", 1)
            lines = parts[0].strip().split("\n", 2)
            author_name = parts[1].strip() if len(parts) > 1 else ""
            sha = lines[0] if lines else ""
            subject = lines[1] if len(lines) > 1 else ""
            body = lines[2] if len(lines) > 2 else ""
            if sha:
                commits.append({"sha": sha, "subject": subject, "body": body.strip(), "author": author_name})
        return commits

    if not author_patterns:
        return _run_log(None)

    seen = set()
    merged = []
    for pat in author_patterns:
        for c in _run_log(pat):
            if c["sha"] not in seen:
                seen.add(c["sha"])
                merged.append(c)
    return merged


def build_scan_payload(
    project_key: str,
    assignees: list[str],
    since: str,
    branch: str = "HEAD",
    commit_author: str | None = None,
    repo_url: str | None = None,
    board_id: int | None = None,
) -> dict:
    """Build the JSON payload: open issues + unmatched commits."""
    # Fetch open issues — board API if board_id given, else assignee JQL
    if board_id:
        issues = fetch_board_issues(board_id)
    else:
        issues = fetch_open_issues(project_key, assignees=assignees)

    # Fetch recent commits
    all_commits = get_recent_commits(since, branch=branch, author=commit_author)

    # Filter out commits that already reference an issue key
    unmatched = []
    for c in all_commits:
        full_msg = f"{c['subject']}\n{c['body']}"
        keys = issue_keys_in_message(project_key, full_msg)
        if not keys:
            unmatched.append({
                "sha": c["sha"][:12],
                "subject": c["subject"],
                "body": c["body"][:300] if c["body"] else "",
                "author": c["author"],
            })

    # Build repo URL for commit links
    if not repo_url:
        server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
        repository = os.getenv("GITHUB_REPOSITORY", "")
        if repository:
            repo_url = f"{server}/{repository}"

    return {
        "project": project_key,
        "assignees": assignees,
        "repo_url": repo_url or "",
        "issues": issues,
        "unmatched_commits": unmatched,
        "matched_commit_count": len(all_commits) - len(unmatched),
        "total_commit_count": len(all_commits),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fetch open Jira issues + recent unmatched commits as JSON for Claude."
    )
    parser.add_argument("--project", default=os.getenv("JIRA_PROJECT", "EAGLE"), help="Jira project key")
    parser.add_argument("--board-id", type=int, default=os.getenv("JIRA_BOARD_ID") and int(os.getenv("JIRA_BOARD_ID")), help="Jira Agile board ID — fetches all open board issues (overrides --assignees)")
    parser.add_argument("--assignees", default="blackga,Greg Black", help="Comma-separated Jira assignee names")
    parser.add_argument("--since", default="7 days ago", help="Git log --since value (e.g. '7 days ago', '24h', SHA)")
    parser.add_argument("--branch", default="HEAD", help="Git branch to read commits from")
    parser.add_argument("--commit-author", default=os.getenv("JIRA_COMMIT_AUTHOR"), help="Only include commits by these git authors (comma-separated)")
    parser.add_argument("--repo-url", default=os.getenv("GITHUB_REPOSITORY"), help="Repo URL for commit links")
    parser.add_argument("--dry-run", action="store_true", help="Print summary instead of JSON (validates connectivity)")
    args = parser.parse_args()

    if not os.getenv("JIRA_BASE_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("Set JIRA_BASE_URL and JIRA_API_TOKEN in env or .env", file=sys.stderr)
        sys.exit(1)

    assignees = [a.strip() for a in args.assignees.split(",") if a.strip()]

    if args.dry_run:
        print("=== jira_scan_issues.py — Dry Run ===\n")
        print(f"  Project     : {args.project}")
        print(f"  Board ID    : {args.board_id or '(none — using assignee filter)'}")
        print(f"  Assignees   : {assignees}")
        print(f"  Since       : {args.since}")
        print(f"  Branch      : {args.branch}")
        print(f"  Commit auth : {args.commit_author or '(all)'}")

        # --- Open Issues (candidates for matching) ---
        if args.board_id:
            issues = fetch_board_issues(args.board_id)
        else:
            issues = fetch_open_issues(args.project, assignees=assignees)
        print(f"\n{'=' * 70}")
        print(f"  OPEN ISSUES — candidates for commit matching ({len(issues)})")
        print(f"{'=' * 70}")
        if issues:
            for iss in issues:
                labels = ", ".join(iss["labels"]) if iss["labels"] else "none"
                print(f"  [{iss['key']}] {iss['summary']}")
                print(f"     Status: {iss['status']}  |  Assignee: {iss['assignee']}  |  Labels: {labels}")
                if iss.get("description"):
                    desc_preview = iss["description"][:120].replace("\n", " ")
                    print(f"     Desc: {desc_preview}...")
                print()
        else:
            print("  (none found — check assignee names match Jira display names)\n")

        # --- Commits ---
        all_commits = get_recent_commits(args.since, branch=args.branch, author=args.commit_author)
        matched_commits = []
        unmatched_commits = []
        for c in all_commits:
            full_msg = f"{c['subject']}\n{c['body']}"
            keys = issue_keys_in_message(args.project, full_msg)
            if keys:
                matched_commits.append((c, keys))
            else:
                unmatched_commits.append(c)

        print(f"{'=' * 70}")
        print(f"  ALREADY MATCHED — commits with explicit {args.project}-XXX keys ({len(matched_commits)})")
        print(f"{'=' * 70}")
        if matched_commits:
            for c, keys in matched_commits:
                print(f"  {c['sha'][:10]} {c['subject'][:60]}")
                print(f"     -> {', '.join(keys)} (already linked, no action needed)")
                print()
        else:
            print("  (none)\n")

        print(f"{'=' * 70}")
        print(f"  UNMATCHED — commits Claude would semantically match ({len(unmatched_commits)})")
        print(f"{'=' * 70}")
        if unmatched_commits:
            for c in unmatched_commits:
                print(f"  {c['sha'][:10]} {c['subject']}")
                print(f"     Author: {c['author']}")
                if c["body"]:
                    body_preview = c["body"][:120].replace("\n", " ")
                    print(f"     Body: {body_preview}")
                if issues:
                    print(f"     [dry-run] Would be evaluated against {len(issues)} open issues")
                else:
                    print(f"     [dry-run] No open issues to match against — would go to weekly catch-all")
                print()
        else:
            print("  (none — all commits already have issue keys)\n")

        # --- Summary: what Jira modifications would happen ---
        print(f"{'=' * 70}")
        print(f"  JIRA MODIFICATIONS PREVIEW")
        print(f"{'=' * 70}")
        if issues and unmatched_commits:
            print(f"  Claude would analyze {len(unmatched_commits)} commit(s) against {len(issues)} issue(s).")
            print(f"  For each high-confidence match, a comment would be posted to the issue:")
            print()
            print(f"    Issue         | Action")
            print(f"    ------------- | ------")
            for iss in issues:
                print(f"    {iss['key']:13} | May receive commit comment(s) — \"{iss['summary'][:40]}\"")
            print()
            print(f"  Low-confidence commits go to the weekly catch-all issue (no semantic match).")
            print(f"  No issues will be created, modified, or reassigned — comments only.")
        elif not issues:
            print(f"  No open issues found for assignees {assignees}.")
            print(f"  All {len(unmatched_commits)} unmatched commit(s) would go to weekly catch-all issue.")
            print(f"  Tip: verify assignee names match Jira display names exactly.")
        else:
            print(f"  All commits already reference {args.project}-XXX keys.")
            print(f"  No semantic matching needed.")
        print()
        print(f"  Result: DRY RUN OK")
        return

    payload = build_scan_payload(
        project_key=args.project,
        assignees=assignees,
        since=args.since,
        branch=args.branch,
        commit_author=args.commit_author,
        repo_url=args.repo_url,
        board_id=args.board_id,
    )
    json.dump(payload, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
