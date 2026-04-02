"""
Sync recent git commits to Jira by adding comments to issues mentioned in commit messages.

Usage:
  # Commits in last 24 hours (default)
  python scripts/jira_commits_sync.py

  # Commits since a specific SHA (e.g. last nightly run)
  python scripts/jira_commits_sync.py --since abc123

  # Custom project key and repo URL
  python scripts/jira_commits_sync.py --project EAGLE --repo-url https://github.com/org/repo

Requires: JIRA_BASE_URL, JIRA_API_TOKEN in env (or .env).
In GitHub Actions, set JIRA_BASE_URL and JIRA_API_TOKEN as repo secrets.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Allow running from repo root or from scripts/
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv
load_dotenv(repo_root / ".env")

# Import from sibling module (works from repo root or scripts/)
try:
    from scripts.jira_connect import add_comment, create_issue, find_issue_by_summary
except ImportError:
    from jira_connect import add_comment, create_issue, find_issue_by_summary  # noqa: E402

# Jira issue key pattern: PROJECT-123
def issue_keys_in_message(project_key: str, message: str) -> list[str]:
    pattern = re.compile(rf"\b{re.escape(project_key)}-\d+\b", re.IGNORECASE)
    return list(dict.fromkeys(pattern.findall(message)))  # unique, preserve order


def _author_list(author: str | None) -> list[str]:
    """Return list of author patterns (comma-separated input); each is passed to git --author (name/email substring)."""
    if not author or not author.strip():
        return []
    return [p.strip() for p in author.split(",") if p.strip()]


def _get_commit_log_one(since: str, branch: str, author_pat: str | None) -> list[dict]:
    """One git log run with optional single author pattern."""
    fmt = ["-z", "--format=%H%n%s%n%b%n---AUTHOR---%n%an"]
    author_arg = [f"--author={author_pat}"] if author_pat else []
    if since == "24h" or since == "24 hours":
        cmd = ["git", "log"] + fmt + author_arg + ["--since=24 hours ago", branch]
    elif any(x in since.lower() for x in ("hour", "day", "week", "month", "year", "ago")):
        cmd = ["git", "log"] + fmt + author_arg + [f"--since={since}", branch]
    else:
        cmd = ["git", "log"] + fmt + author_arg + [f"{since}..{branch}"]
    result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, shell=False)
    if result.returncode != 0 and "unknown revision" not in (result.stderr or "").lower():
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


def get_commit_log(since: str, branch: str = "HEAD", author: str | None = None) -> list[dict]:
    """Return list of {sha, subject, body, author} for commits since `since`. Author can be comma-separated (any match)."""
    authors = _author_list(author)
    if not authors:
        return _get_commit_log_one(since, branch, None)
    seen = set()
    merged = []
    for apat in authors:
        for c in _get_commit_log_one(since, branch, apat):
            if c["sha"] not in seen:
                seen.add(c["sha"])
                merged.append(c)
    # Keep order: first author's commits (newest first), then others not yet seen
    return merged


def weekly_issue_summary(prefix: str) -> str:
    """Current ISO year+week with prefix, e.g. 'Greg Dev Weekly Summary — 2026-W14'."""
    year, week, _ = datetime.now().isocalendar()
    return f"{prefix.strip()} {year}-W{week:02d}"


def get_or_create_weekly_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    dry_run: bool = False,
) -> str | None:
    """Find an issue with that summary, or create it. Returns issue key or None. In dry_run, skips Jira API (no lookup/create)."""
    if dry_run:
        return None
    key = find_issue_by_summary(project_key, summary, quiet=True)
    if key:
        return key
    key = create_issue(project_key, summary, issue_type=issue_type, labels=["catch-all-dev"])
    return key


def clean_commit_body(body: str) -> str:
    """Strip Co-Authored-By lines and trailing whitespace from commit body."""
    lines = body.splitlines()
    cleaned = [l for l in lines if not l.strip().lower().startswith("co-authored-by:")]
    return "\n".join(cleaned).strip()


def main():
    parser = argparse.ArgumentParser(description="Sync git commits to Jira issue comments.")
    parser.add_argument("--since", default="24h", help="SHA to sync after, or '24h' for last 24 hours")
    parser.add_argument("--branch", default="HEAD", help="Branch to read commits from")
    parser.add_argument("--project", default=os.getenv("JIRA_PROJECT", "EAGLE"), help="Jira project key (e.g. EAGLE)")
    parser.add_argument("--repo-url", default=os.getenv("GITHUB_REPOSITORY") or os.getenv("REPO_URL"), help="Repo URL (unused in comments, kept for backwards compat)")
    parser.add_argument("--author", default=os.getenv("JIRA_COMMIT_AUTHOR"), help="Only sync commits by these author(s): comma-separated (e.g. gblack686-revstar,gblack686,blackga-nih) or single pattern")
    parser.add_argument("--weekly-summary", default=os.getenv("JIRA_WEEKLY_SUMMARY"), help="Suffix for weekly catch-all issue (e.g. 'greg dev') -> 'yyyyww greg dev'; commits without an issue key are posted here")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be commented, do not call Jira")
    args = parser.parse_args()

    if not os.getenv("JIRA_BASE_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("Set JIRA_BASE_URL and JIRA_API_TOKEN in env or .env", file=sys.stderr)
        sys.exit(1)

    # Build repo URL for links (GitHub Actions sets GITHUB_SERVER_URL + GITHUB_REPOSITORY)
    repo_url = args.repo_url
    if not repo_url and os.getenv("GITHUB_SERVER_URL") and os.getenv("GITHUB_REPOSITORY"):
        repo_url = f"{os.getenv('GITHUB_SERVER_URL')}/{os.getenv('GITHUB_REPOSITORY')}"

    commits = get_commit_log(args.since, args.branch, author=args.author or None)
    if not commits:
        print("No commits to sync." + (" (author filter may exclude all)" if args.author else ""))
        return

    author_desc = f" by author(s) '{args.author}'" if args.author else ""
    print(f"Found {len(commits)} commit(s) since {args.since}{author_desc}. Project: {args.project}")

    weekly_key: str | None = None
    weekly_summary_str: str | None = None
    if args.weekly_summary and args.weekly_summary.strip():
        weekly_summary_str = weekly_issue_summary(args.weekly_summary)
        weekly_key = get_or_create_weekly_issue(
            args.project, weekly_summary_str, dry_run=args.dry_run
        )
        if weekly_key:
            print(f"Weekly issue: [{weekly_key}] {weekly_summary_str}")
        elif args.dry_run:
            print(f"Weekly issue (dry-run): [would create or find] {weekly_summary_str}")

    commented = 0
    for c in commits:
        clean_body = clean_commit_body(c["body"])
        full_message = f"{c['subject']}\n\n{clean_body}".strip() if clean_body else c["subject"]
        keys = issue_keys_in_message(args.project, f"{c['subject']}\n\n{c['body']}")
        short_sha = c["sha"][:10]
        body_plain = f"Commit: {short_sha}\n\n{full_message}"

        if keys:
            for key in keys:
                if args.dry_run:
                    print(f"  [dry-run] Would comment on {key}: {c['subject'][:50]}...")
                else:
                    if add_comment(key, body_plain):
                        commented += 1
                        print(f"  Commented on {key}: {c['subject'][:50]}...")
        else:
            # No issue key in message -> post to weekly catch-all if configured
            if weekly_key:
                if args.dry_run:
                    print(f"  [dry-run] Would comment on weekly [{weekly_key}]: {c['subject'][:50]}...")
                else:
                    if add_comment(weekly_key, body_plain):
                        commented += 1
                        print(f"  Commented on weekly [{weekly_key}]: {c['subject'][:50]}...")
            elif weekly_summary_str and args.dry_run:
                print(f"  [dry-run] Would comment on weekly [{weekly_summary_str}]: {c['subject'][:50]}...")
            else:
                if args.dry_run:
                    print(f"  [skip] No {args.project}-XXX in message: {c['subject'][:60]}...")

    print(f"Done. Comments added: {commented}.")


if __name__ == "__main__":
    main()
