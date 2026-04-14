"""
GitHub Morning Report — sends a commit summary Adaptive Card to Teams.

Collects commits from the last 24 hours on the current branch and sends
a formatted card to the Teams QA channel via the webhook.

Usage:
    python scripts/morning_report.py              # last 24h
    python scripts/morning_report.py --hours 48   # last 48h
    python scripts/morning_report.py --since 2026-03-18

Env vars:
    TEAMS_WEBHOOK_URL   — required (or falls back to ERROR_WEBHOOK_URL)
    GITHUB_REPOSITORY   — e.g. "CBIIT/sm_eagle" (auto-set in GitHub Actions)
"""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

# Make the langfuse-analytics skill script importable so we can reuse its
# fetch + aggregate helpers without duplicating logic.
_LF_SCRIPT_DIR = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "langfuse-analytics" / "scripts"
if _LF_SCRIPT_DIR.exists() and str(_LF_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_LF_SCRIPT_DIR))

try:
    import langfuse_report as _lf  # type: ignore
except Exception as _lf_err:  # noqa: BLE001
    _lf = None
    print(f"[Morning Report] Langfuse helper unavailable: {_lf_err}", file=sys.stderr)


def _git(args: list[str]) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def _extract_repo_from_remote(remote: str) -> str:
    """Return org/repo for canonical GitHub remotes only."""
    remote = remote.strip()
    if not remote:
        return ""

    if remote.startswith("git@github.com:"):
        path = remote.split("git@github.com:", 1)[1]
    else:
        parsed = urlparse(remote)
        if parsed.scheme not in {"http", "https"} or parsed.hostname != "github.com":
            return ""
        path = parsed.path

    return path.strip("/").removesuffix(".git")


def get_commits(since: str) -> list[dict]:
    """Get commits since a given ISO date string."""
    # Format: sha|author|date|message|files_changed
    log = _git([
        "log", f"--since={since}", "--format=%H|%an|%aI|%s",
        "--no-merges",
    ])
    if not log:
        return []

    commits = []
    for line in log.strip().split("\n"):
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        sha, author, date, message = parts

        # Count files changed per commit
        diff_stat = _git(["diff", "--shortstat", f"{sha}^..{sha}"])
        files_changed = 0
        if diff_stat:
            # e.g. "5 files changed, 120 insertions(+), 30 deletions(-)"
            try:
                files_changed = int(diff_stat.strip().split()[0])
            except (ValueError, IndexError):
                pass

        commits.append({
            "sha": sha,
            "author": author,
            "date": date,
            "message": message,
            "files_changed": files_changed,
        })

    return commits


def _summarize_langfuse(window: str = "24h", env: str = "all") -> dict | None:
    """Fetch a compact Langfuse rollup for embedding in the morning card.

    Returns None if the helper module is unavailable, credentials are missing,
    or the API call fails — morning report must never fail because of telemetry.
    """
    if _lf is None:
        return None
    try:
        agg = _lf.get_summary(window=window, env=env)
    except Exception as e:  # noqa: BLE001
        print(f"[Morning Report] Langfuse summary failed: {e}", file=sys.stderr)
        return None
    if not agg:
        return None

    def _top(counter: Counter, n: int) -> list[tuple[str, int]]:
        if not isinstance(counter, Counter):
            counter = Counter(counter or {})
        return counter.most_common(n)

    return {
        "trace_count": agg.get("trace_count", 0),
        "obs_count": agg.get("obs_count", 0),
        "session_count": agg.get("session_count", 0),
        "tool_total": sum((agg.get("tool_counts") or Counter()).values()),
        "error_total": sum((agg.get("env_error_counts") or Counter()).values()),
        "top_tools": _top(agg.get("tool_counts") or Counter(), 5),
        "doc_types": _top(agg.get("doc_types") or Counter(), 6),
        "top_research": _top(agg.get("research_keywords") or Counter(), 3),
        "envs": _top(agg.get("env_counts") or Counter(), 5),
    }


def _langfuse_block(summary: dict) -> list[dict]:
    """Convert a Langfuse summary dict into Adaptive Card body items."""
    if not summary:
        return []

    lines: list[str] = []
    lines.append(
        f"**Traces:** {summary['trace_count']} · "
        f"**Sessions:** {summary['session_count']} · "
        f"**Tool calls:** {summary['tool_total']} · "
        f"**Errors:** {summary['error_total']}"
    )
    if summary["envs"]:
        envs_str = ", ".join(f"{e}={c}" for e, c in summary["envs"])
        lines.append(f"**Envs:** {envs_str}")
    if summary["top_tools"]:
        tools_str = ", ".join(f"`{n}` ({c})" for n, c in summary["top_tools"])
        lines.append(f"**Top tools:** {tools_str}")
    if summary["doc_types"]:
        docs_str = ", ".join(f"{n} ({c})" for n, c in summary["doc_types"])
        lines.append(f"**Docs generated:** {docs_str}")
    if summary["top_research"]:
        res_str = "; ".join(f"{kw[:50]} ({c}x)" for kw, c in summary["top_research"])
        lines.append(f"**Top research topics:** {res_str}")

    return [
        {
            "type": "TextBlock",
            "text": "Langfuse Activity (24h)",
            "weight": "Bolder",
            "size": "Medium",
            "spacing": "Large",
            "separator": True,
        },
        {
            "type": "TextBlock",
            "text": "\n\n".join(lines),
            "wrap": True,
            "spacing": "Small",
        },
    ]


def build_card(commits: list[dict], since: str, repo: str, branch: str, langfuse_summary: dict | None = None) -> dict:
    """Build the Adaptive Card payload."""
    authors = sorted(set(c["author"] for c in commits))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    date_range = f"{since[:10]} to {today}"

    repo_url = f"https://github.com/{repo}" if repo else ""

    # Build commit entries for the card body
    commit_lines = []
    for c in commits[:15]:
        sha = c["sha"][:7]
        author = c["author"]
        msg = c["message"][:80]
        files = c["files_changed"]
        commit_lines.append(f"**{sha}** ({author}) {msg} — {files} files")

    if len(commits) > 15:
        commit_lines.append(f"*...and {len(commits) - 15} more*")

    body_text = "\n\n".join(commit_lines) if commit_lines else "*No commits in this period.*"

    facts = [
        {"title": "Repository", "value": repo or "unknown"},
        {"title": "Branch", "value": branch},
        {"title": "Period", "value": date_range},
        {"title": "Commits", "value": str(len(commits))},
        {"title": "Authors", "value": ", ".join(authors) if authors else "none"},
    ]

    actions = []
    if repo_url:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "View on GitHub",
            "url": repo_url,
        })

    card_body = [
        {
            "type": "Container",
            "style": "accent",
            "bleed": True,
            "items": [{
                "type": "TextBlock",
                "text": f"EAGLE | Morning Report — {today}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            }],
        },
        {"type": "FactSet", "facts": facts},
    ]

    if body_text:
        card_body.append({
            "type": "TextBlock",
            "text": body_text,
            "wrap": True,
            "spacing": "Medium",
        })

    card_body.extend(_langfuse_block(langfuse_summary or {}))

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": card_body,
    }
    if actions:
        card["actions"] = actions

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": card,
        }],
    }


def main():
    # Parse args
    hours = 24
    since = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--hours" and i + 1 < len(args):
            hours = int(args[i + 1])
            i += 2
        elif args[i] == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        else:
            i += 1

    if since is None:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    # Get webhook URL
    webhook_url = os.getenv(
        "TEAMS_WEBHOOK_URL",
        os.getenv(
            "ERROR_WEBHOOK_URL",
            "https://prod-52.usgovtexas.logic.azure.us:443/workflows/8705df58d766420d8847222b1b12d7a0/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=Xo4vpYNBYWWdyreboIYnBJtGlO3cNRLSEakEcNGWBoM",
        ),
    )

    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not repo:
        # Try to get from git remote
        remote = _git(["remote", "get-url", "origin"])
        repo = _extract_repo_from_remote(remote)

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])

    print(f"[Morning Report] Repo: {repo}")
    print(f"[Morning Report] Branch: {branch}")
    print(f"[Morning Report] Since: {since}")

    # Collect commits
    commits = get_commits(since)
    print(f"[Morning Report] Commits found: {len(commits)}")

    for c in commits[:5]:
        print(f"  {c['sha'][:7]} ({c['author']}) {c['message'][:60]}")
    if len(commits) > 5:
        print(f"  ...and {len(commits) - 5} more")

    # Pull Langfuse activity rollup (24h, all envs). Non-fatal on failure.
    langfuse_summary = _summarize_langfuse(window="24h", env="all")
    if langfuse_summary:
        print(
            f"[Morning Report] Langfuse: {langfuse_summary['trace_count']} traces, "
            f"{langfuse_summary['tool_total']} tool calls, {langfuse_summary['error_total']} errors"
        )
    else:
        print("[Morning Report] Langfuse summary unavailable — skipping section")

    # Build and send card
    card = build_card(commits, since, repo, branch, langfuse_summary=langfuse_summary)

    print(f"[Morning Report] Sending to Teams...")
    resp = httpx.post(webhook_url, json=card, timeout=10)
    print(f"[Morning Report] Status: {resp.status_code}")

    if resp.status_code >= 300:
        print(f"[Morning Report] Response: {resp.text[:200]}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
