"""One-time JIRA -> GitHub migration for auto-created triage / feedback tickets.

Reads JIRA issues matching a JQL (default: `project = EAGLE AND labels = "auto-created"`),
downloads their attachments into `docs/development/triage-attachments/{JIRA_KEY}/`,
converts the description from JIRA wiki markup to GitHub-flavored markdown, and
creates a matching GitHub issue via the `gh` CLI.

Idempotent: every created issue embeds
    <!-- auto-triage-jira-key: EAGLE-123 -->
    <!-- auto-triage-fingerprint: abcdef012345 -->
    <!-- auto-triage-feedback-id: {uuid} -->   (when parseable)

Re-running the script skips any JIRA key that already has an issue with the
`migrated-from-jira` label.

Attachments are stored under `docs/development/triage-attachments/{JIRA_KEY}/`
and referenced via raw.githubusercontent.com URLs in the issue body — the
GitHub REST API does NOT support direct file upload, so attachments have to
be committed + pushed BEFORE the issue is created, or the image links 404.

Usage:
    python scripts/migrate_jira_to_github.py \
        --repo=CBIIT/sm_eagle \
        --jql='project = EAGLE AND labels = "auto-created"' \
        --dry-run --limit=5

    python scripts/migrate_jira_to_github.py --repo=CBIIT/sm_eagle --limit=50
    python scripts/migrate_jira_to_github.py --repo=CBIIT/sm_eagle   # live, uncapped

Env:
    JIRA_BASE_URL      — NCI self-hosted JIRA base URL
    JIRA_API_TOKEN     — bearer PAT (same token scripts/triage_notify.py uses)
    JIRA_PROJECT       — default "EAGLE"
    GH_TOKEN           — built-in GITHUB_TOKEN in CI, or `gh auth login` locally
    TABLE_NAME         — DynamoDB table (default "eagle")
    AWS_REGION         — default "us-east-1"
    AWS_PROFILE        — optional, for local runs (CI uses ambient OIDC)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

# Force stdout/stderr UTF-8 so Windows cp1252 doesn't blow up on unicode
# in print statements (JIRA data contains em-dashes, arrows, etc.).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
ATTACHMENTS_SUBDIR = Path("docs/development/triage-attachments")

# Attachment caps
MAX_ATTACHMENTS_PER_ISSUE = 10
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024        # skip anything over 2 MB
MAX_TOTAL_ATTACHMENT_BYTES = 50 * 1024 * 1024  # total per script run

# Fingerprint length (must match file_github_issues.py)
FINGERPRINT_LEN = 12

# Image extensions we inline-render in the issue body
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

# Known environment labels we copy over from JIRA labels into `env/*`
# Real EAGLE tickets use "localhost" (from config.py app.environment) — not "local".
ENV_LABEL_MAP = {
    "dev": "env/dev",
    "qa": "env/qa",
    "prod": "env/prod",
    "localhost": "env/local",
    "local": "env/local",
}

# Required GitHub labels — `gh label create --force` at script start
REQUIRED_LABELS = [
    ("auto-triage",        "FBCA04", "Created or managed by the nightly triage workflow"),
    ("migrated-from-jira", "5319E7", "Backfilled from a pre-existing JIRA ticket"),
    ("triage/error",       "B60205", "Error captured by nightly triage"),
    ("triage/feedback",    "0E8A16", "User feedback captured by nightly triage"),
    ("env/dev",            "C5DEF5", "Environment: dev"),
    ("env/qa",             "C5DEF5", "Environment: qa"),
    ("env/prod",           "C5DEF5", "Environment: prod"),
    ("env/local",          "C5DEF5", "Environment: local"),
    ("severity/actionable","D93F0B", "Actionable severity"),
    ("severity/warning",   "FBCA04", "Warning severity"),
    ("severity/noise",     "C2E0C6", "Noise severity (low priority)"),
]


# ──────────────────────────────────────────────────────────────────────
# JIRA helpers
# ──────────────────────────────────────────────────────────────────────

def _jira_headers() -> dict[str, str]:
    token = os.getenv("JIRA_API_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _jira_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0),
        limits=httpx.Limits(max_connections=5),
    )


def search_jira_issues(client: httpx.Client, jql: str, limit: Optional[int] = None) -> list[dict]:
    """Page through /rest/api/2/search until exhausted or cap hit."""
    base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("JIRA_BASE_URL not set")

    results: list[dict] = []
    start_at = 0
    page_size = 100

    while True:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": page_size,
            "fields": "summary,description,labels,created,updated,status,attachment,comment,issuetype",
        }
        resp = client.get(f"{base}/rest/api/2/search", headers=_jira_headers(), params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"JIRA search failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        issues = data.get("issues", [])
        results.extend(issues)

        total = data.get("total", 0)
        start_at += len(issues)
        if limit and len(results) >= limit:
            results = results[:limit]
            break
        if not issues or start_at >= total:
            break

    if limit:
        results = results[:limit]
    return results


def download_attachment(client: httpx.Client, url: str) -> Optional[bytes]:
    resp = client.get(url, headers={"Authorization": _jira_headers()["Authorization"]})
    if resp.status_code != 200:
        print(f"  [attachment] download failed: {resp.status_code} {url}", file=sys.stderr)
        return None
    return resp.content


# ──────────────────────────────────────────────────────────────────────
# Wiki markup conversion (JIRA → GitHub flavored markdown)
# ──────────────────────────────────────────────────────────────────────

_WIKI_CODE_BLOCK = re.compile(r"\{code(?::[^}]*)?\}(.*?)\{code\}", re.DOTALL)
_WIKI_NOFORMAT   = re.compile(r"\{noformat\}(.*?)\{noformat\}", re.DOTALL)
_WIKI_HEADING    = re.compile(r"^h([1-6])\.\s+(.*)$", re.MULTILINE)
_WIKI_BOLD       = re.compile(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])")
_WIKI_ITALIC     = re.compile(r"(?<![\w_])_([^_\n]+?)_(?![\w_])")
_WIKI_HRULE      = re.compile(r"^----+\s*$", re.MULTILINE)
_WIKI_LINK       = re.compile(r"\[([^\|\]]+)\|([^\]]+)\]")
_WIKI_LIST_STAR  = re.compile(r"^(\*+)\s+", re.MULTILINE)
_WIKI_LIST_HASH  = re.compile(r"^(#+)\s+", re.MULTILINE)


def jira_to_markdown(text: str) -> str:
    """Good-enough wiki-markup -> GitHub markdown pass.

    Optimized for the flat `_create_jira_for_feedback` output format; more
    elaborate tickets (panels, tables, color tags) will come through
    imperfectly — spot-check during dry-run.
    """
    if not text:
        return ""

    out = text

    # Code blocks first (before bold/italic can mangle their contents)
    out = _WIKI_CODE_BLOCK.sub(lambda m: f"\n```\n{m.group(1).strip()}\n```\n", out)
    out = _WIKI_NOFORMAT.sub(lambda m: f"\n```\n{m.group(1).strip()}\n```\n", out)

    # Lists BEFORE headings — otherwise `### Heading` (post-conversion) matches
    # the hash-list regex and gets turned into a numbered list.
    def _star_list(m: re.Match[str]) -> str:
        depth = len(m.group(1)) - 1
        return f"{'  ' * depth}- "
    out = _WIKI_LIST_STAR.sub(_star_list, out)

    def _hash_list(m: re.Match[str]) -> str:
        depth = len(m.group(1)) - 1
        return f"{'  ' * depth}1. "
    out = _WIKI_LIST_HASH.sub(_hash_list, out)

    # Headings: h3. X -> ### X
    out = _WIKI_HEADING.sub(lambda m: f"{'#' * int(m.group(1))} {m.group(2).strip()}", out)

    # Links: [text|url] -> [text](url)
    out = _WIKI_LINK.sub(lambda m: f"[{m.group(1).strip()}]({m.group(2).strip()})", out)

    # Horizontal rule
    out = _WIKI_HRULE.sub("---", out)

    # Bold / italic last
    out = _WIKI_BOLD.sub(lambda m: f"**{m.group(1)}**", out)
    out = _WIKI_ITALIC.sub(lambda m: f"*{m.group(1)}*", out)

    return out


# ──────────────────────────────────────────────────────────────────────
# GitHub (via gh CLI)
# ──────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], check: bool = True, input_text: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        input=input_text,
    )


def gh_ensure_labels(repo: str, dry_run: bool) -> None:
    """Create / update the fixed label set. Safe to re-run."""
    for name, color, desc in REQUIRED_LABELS:
        if dry_run:
            print(f"  [label] WOULD ensure {name}")
            continue
        cmd = [
            "gh", "label", "create", name,
            "--repo", repo,
            "--color", color,
            "--description", desc,
            "--force",
        ]
        try:
            _run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  [label] {name} create failed: {e.stderr[:200]}", file=sys.stderr)


def gh_list_migrated(repo: str) -> dict[str, int]:
    """Return {JIRA_KEY: issue_number} for already-migrated issues."""
    try:
        proc = _run(
            [
                "gh", "issue", "list",
                "--repo", repo,
                "--label", "migrated-from-jira",
                "--state", "all",
                "--limit", "2000",
                "--json", "number,body",
            ],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[gh] list failed: {e.stderr[:300]}", file=sys.stderr)
        return {}

    mapping: dict[str, int] = {}
    for issue in json.loads(proc.stdout or "[]"):
        body = issue.get("body") or ""
        m = re.search(r"<!--\s*auto-triage-jira-key:\s*([A-Z]+-\d+)\s*-->", body)
        if m:
            mapping[m.group(1)] = issue["number"]
    return mapping


def gh_create_issue(repo: str, title: str, body: str, labels: list[str]) -> Optional[int]:
    cmd = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", title[:255],
        "--body-file", "-",
    ]
    for label in labels:
        cmd += ["--label", label]
    try:
        proc = _run(cmd, check=True, input_text=body)
    except subprocess.CalledProcessError as e:
        print(f"[gh] create failed: {e.stderr[:400]}", file=sys.stderr)
        return None
    # stdout is the issue URL; parse the trailing number
    m = re.search(r"/issues/(\d+)", proc.stdout or "")
    return int(m.group(1)) if m else None


# ──────────────────────────────────────────────────────────────────────
# DynamoDB back-patch
# ──────────────────────────────────────────────────────────────────────

def _dynamodb_table():
    import boto3  # lazy import
    region = os.environ.get("AWS_REGION", "us-east-1")
    profile = os.environ.get("AWS_PROFILE")
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.resource("dynamodb", region_name=region).Table(
        os.environ.get("TABLE_NAME", "eagle")
    )


_feedback_cache: dict[str, list[dict]] = {}


def _list_feedback_for_tenant(tenant_id: str) -> list[dict]:
    """Query every FEEDBACK#{tenant_id} row. Cached per tenant_id."""
    if tenant_id in _feedback_cache:
        return _feedback_cache[tenant_id]

    try:
        from boto3.dynamodb.conditions import Key
        table = _dynamodb_table()
        items: list[dict] = []
        resp = table.query(
            KeyConditionExpression=Key("PK").eq(f"FEEDBACK#{tenant_id}") & Key("SK").begins_with("FEEDBACK#"),
            Limit=500,
        )
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.query(
                KeyConditionExpression=Key("PK").eq(f"FEEDBACK#{tenant_id}") & Key("SK").begins_with("FEEDBACK#"),
                ExclusiveStartKey=resp["LastEvaluatedKey"],
                Limit=500,
            )
            items.extend(resp.get("Items", []))
        _feedback_cache[tenant_id] = items
        return items
    except Exception as e:
        print(f"[dynamodb] query failed for {tenant_id}: {e}", file=sys.stderr)
        _feedback_cache[tenant_id] = []
        return []


def patch_feedback_with_issue(feedback_id: str, tenant_id: str, issue_number: int, jira_key: str, dry_run: bool) -> bool:
    """Set github_issue_number on the matching feedback row (idempotent)."""
    items = _list_feedback_for_tenant(tenant_id)
    match = next((i for i in items if i.get("feedback_id") == feedback_id), None)
    if not match:
        return False
    if dry_run:
        print(f"  [dynamodb] WOULD patch feedback {feedback_id} -> issue #{issue_number}")
        return True
    try:
        table = _dynamodb_table()
        table.update_item(
            Key={"PK": match["PK"], "SK": match["SK"]},
            UpdateExpression="SET github_issue_number = :n, github_filed_at = :t, migrated_from_jira = :j",
            ConditionExpression="attribute_not_exists(github_issue_number)",
            ExpressionAttributeValues={
                ":n": issue_number,
                ":t": datetime.now(timezone.utc).isoformat(),
                ":j": jira_key,
            },
        )
        return True
    except Exception as e:
        # ConditionalCheckFailed means already patched — treat as success
        if "ConditionalCheckFailed" in str(e):
            return True
        print(f"  [dynamodb] patch failed for {feedback_id}: {e}", file=sys.stderr)
        return False


# ──────────────────────────────────────────────────────────────────────
# Per-issue migration
# ──────────────────────────────────────────────────────────────────────

def _extract_feedback_id(description: str) -> Optional[str]:
    m = re.search(
        r"\*Feedback ID:\*\s*([0-9a-fA-F-]{8,})",
        description or "",
    )
    return m.group(1) if m else None


def _extract_tenant(description: str) -> Optional[str]:
    """Parse `*Tenant:* dev-tenant` out of the feedback JIRA description."""
    m = re.search(r"\*Tenant:\*\s*([\w.-]+)", description or "")
    return m.group(1) if m else None


def _extract_env_from_labels(labels: list[str]) -> str:
    for lab in labels:
        if lab in ENV_LABEL_MAP:
            return lab
    return "unknown"


def _fingerprint_feedback(feedback_id: Optional[str], jira_key: str) -> str:
    seed = feedback_id or jira_key
    return hashlib.md5(seed.encode()).hexdigest()[:FINGERPRINT_LEN]


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


def download_issue_attachments(
    client: httpx.Client,
    jira_issue: dict,
    byte_budget_remaining: int,
    repo_slug: str,
    dry_run: bool,
) -> tuple[list[dict], int]:
    """Download up to MAX_ATTACHMENTS_PER_ISSUE attachments under 2 MB.

    Returns (attachment_meta_list, total_bytes_written).
    """
    key = jira_issue["key"]
    raw_atts = (jira_issue.get("fields") or {}).get("attachment") or []
    if not raw_atts:
        return [], 0

    out_dir = REPO_ROOT / ATTACHMENTS_SUBDIR / key
    meta: list[dict] = []
    total_bytes = 0

    for att in raw_atts[:MAX_ATTACHMENTS_PER_ISSUE]:
        size = int(att.get("size", 0))
        filename = _safe_filename(att.get("filename", "attachment"))
        content_url = att.get("content", "")

        if size > MAX_ATTACHMENT_BYTES:
            print(f"  [attachment] {key}/{filename}: {size:,}B > 2MB, skipping")
            continue
        if size + total_bytes > byte_budget_remaining:
            print(f"  [attachment] {key}/{filename}: would exceed run budget, stopping")
            break

        ext = Path(filename).suffix.lower()
        rel_path = f"{ATTACHMENTS_SUBDIR.as_posix()}/{key}/{filename}"
        raw_url = (
            f"https://raw.githubusercontent.com/{repo_slug}/main/"
            + "/".join(quote(p) for p in rel_path.split("/"))
        )

        meta_entry = {
            "filename": filename,
            "rel_path": rel_path,
            "raw_url": raw_url,
            "is_image": ext in IMAGE_EXTS,
            "size": size,
        }

        if dry_run:
            print(f"  [attachment] WOULD download {key}/{filename} ({size:,}B)")
            meta.append(meta_entry)
            continue

        data = download_attachment(client, content_url)
        if data is None:
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / filename).write_bytes(data)
        total_bytes += len(data)
        meta.append(meta_entry)

    return meta, total_bytes


def build_issue_body(
    jira_issue: dict,
    attachments: list[dict],
    feedback_id: Optional[str],
    fingerprint: str,
) -> str:
    fields = jira_issue.get("fields", {}) or {}
    key = jira_issue["key"]
    status = (fields.get("status") or {}).get("name", "Unknown")
    created = fields.get("created", "")
    updated = fields.get("updated", "")
    description_raw = fields.get("description") or "(no description)"
    description_md = jira_to_markdown(description_raw)

    base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    jira_browse = f"{base_url}/browse/{key}" if base_url else key

    # Comments
    comments_blob = ""
    comments = ((fields.get("comment") or {}).get("comments")) or []
    if comments:
        lines = ["", "### JIRA Comments", ""]
        for c in comments[:20]:
            author = (c.get("author") or {}).get("displayName", "unknown")
            body = jira_to_markdown(c.get("body") or "")
            created_at = (c.get("created") or "")[:10]
            # Quote each line
            quoted = "\n".join(f"> {line}" for line in body.splitlines())
            lines.append(f"**{author}** — {created_at}")
            lines.append("")
            lines.append(quoted)
            lines.append("")
        comments_blob = "\n".join(lines)

    # Attachments block
    att_blob = ""
    if attachments:
        lines = ["", "### Attachments", ""]
        for a in attachments:
            if a["is_image"]:
                lines.append(f"![{a['filename']}]({a['raw_url']})")
            else:
                lines.append(f"- [{a['filename']}]({a['raw_url']}) ({a['size']:,} bytes)")
        att_blob = "\n".join(lines)

    feedback_comment = f"<!-- auto-triage-feedback-id: {feedback_id} -->\n" if feedback_id else ""

    return (
        f"<!-- auto-triage-jira-key: {key} -->\n"
        f"<!-- auto-triage-fingerprint: {fingerprint} -->\n"
        f"{feedback_comment}"
        f"\n"
        f"**Migrated from JIRA** [{key}]({jira_browse})\n"
        f"**Status:** {status}   **Created:** {created[:10]}   **Updated:** {updated[:10]}\n"
        f"\n---\n\n"
        f"{description_md}\n"
        f"{att_blob}\n"
        f"{comments_blob}\n"
        f"\n---\n"
        f"_Migrated from JIRA by `scripts/migrate_jira_to_github.py`_\n"
    )


def build_issue_title(jira_issue: dict) -> str:
    key = jira_issue["key"]
    summary = (jira_issue.get("fields") or {}).get("summary") or "(no summary)"
    return f"[migrated] {summary} ({key})"


def build_issue_labels(jira_issue: dict) -> list[str]:
    labels = set(["auto-triage", "migrated-from-jira"])
    jira_labels = (jira_issue.get("fields") or {}).get("labels") or []
    for lab in jira_labels:
        if lab in ENV_LABEL_MAP:
            labels.add(ENV_LABEL_MAP[lab])
        elif lab == "feedback":
            labels.add("triage/feedback")
        elif lab == "triage":
            labels.add("triage/error")
    # Default to triage/feedback if none of the triage type labels matched
    if not any(l.startswith("triage/") for l in labels):
        labels.add("triage/feedback")
    return sorted(labels)


# ──────────────────────────────────────────────────────────────────────
# Git commit helpers (for attachments)
# ──────────────────────────────────────────────────────────────────────

def _git(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return _run(["git", "-C", str(REPO_ROOT)] + cmd, check=check)


def commit_attachments_batch(batch_label: str, dry_run: bool) -> bool:
    """Stage and commit any new files under triage-attachments/. Idempotent.

    Returns True if a commit was created (so caller knows to push before
    creating GitHub issues — raw URLs 404 until the push lands).
    """
    if dry_run:
        print(f"  [git] WOULD commit attachments ({batch_label})")
        return False

    _git(["add", f"{ATTACHMENTS_SUBDIR.as_posix()}/"], check=False)
    diff = _git(["diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        return False  # nothing staged

    msg = (
        f"chore: migrate JIRA attachments ({batch_label})\n\n"
        "Auto-committed by scripts/migrate_jira_to_github.py so raw image "
        "URLs in migrated issue bodies resolve.\n\n"
        "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n"
    )
    _git(["commit", "-m", msg], check=True)
    # Push is the caller's responsibility; attempt it if we're in CI
    if os.environ.get("GITHUB_ACTIONS") == "true":
        _git(["push"], check=False)
    return True


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="GitHub repo slug (e.g. CBIIT/sm_eagle)")
    ap.add_argument(
        "--jql",
        default='project = EAGLE AND labels = "auto-created"',
        help="JQL for JIRA search (default: auto-created label in EAGLE project)",
    )
    ap.add_argument("--since", help="Only migrate JIRA issues updated >= this ISO date")
    ap.add_argument("--limit", type=int, default=0, help="Cap total issues processed (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true", help="Plan only; no GH/Dynamo writes")
    ap.add_argument("--skip-attachments", action="store_true", help="Do not download attachments")
    ap.add_argument("--tenant", default="default", help="DynamoDB feedback tenant prefix")
    args = ap.parse_args()

    if args.since:
        args.jql += f' AND updated >= "{args.since}"'

    # Load server/.env so local runs pick up JIRA creds without Just file wiring
    try:
        from dotenv import load_dotenv
        env_file = REPO_ROOT / "server" / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass

    if not os.getenv("JIRA_BASE_URL") or not os.getenv("JIRA_API_TOKEN"):
        print("ERROR: JIRA_BASE_URL / JIRA_API_TOKEN not set", file=sys.stderr)
        return 2

    # Bootstrap labels once
    gh_ensure_labels(args.repo, args.dry_run)

    # Build migrated map (skip list)
    already_migrated = gh_list_migrated(args.repo)
    print(f"[gh] {len(already_migrated)} JIRA keys already migrated")

    # Search JIRA
    with _jira_client() as client:
        print(f"[jira] search: {args.jql}")
        issues = search_jira_issues(client, args.jql, limit=args.limit or None)
        print(f"[jira] {len(issues)} issues matched")

        created: list[dict] = []
        skipped: list[dict] = []
        byte_budget = MAX_TOTAL_ATTACHMENT_BYTES
        batch_since_commit = 0

        for idx, issue in enumerate(issues, start=1):
            key = issue["key"]
            fields = issue.get("fields") or {}
            description = fields.get("description") or ""
            labels = fields.get("labels") or []

            if key in already_migrated:
                skipped.append({"key": key, "reason": "already migrated", "issue_number": already_migrated[key]})
                print(f"[{idx}/{len(issues)}] {key}: skip (already migrated → #{already_migrated[key]})")
                continue

            feedback_id = _extract_feedback_id(description)
            env = _extract_env_from_labels(labels)
            tenant_id = _extract_tenant(description)
            fingerprint = _fingerprint_feedback(feedback_id, key)

            # Attachments (optionally)
            atts: list[dict] = []
            bytes_written = 0
            if not args.skip_attachments and byte_budget > 0:
                atts, bytes_written = download_issue_attachments(
                    client, issue, byte_budget, args.repo, args.dry_run
                )
                byte_budget -= bytes_written

            body = build_issue_body(issue, atts, feedback_id, fingerprint)
            title = build_issue_title(issue)
            gh_labels = build_issue_labels(issue)

            if args.dry_run:
                print(f"[{idx}/{len(issues)}] {key}: WOULD create '{title[:60]}' ({len(atts)} atts, labels={gh_labels})")
                created.append({
                    "key": key, "title": title, "labels": gh_labels,
                    "attachments": len(atts), "feedback_id": feedback_id, "issue_number": None,
                })
                continue

            # Commit the attachment batch BEFORE creating the issue so raw URLs resolve
            batch_since_commit += 1
            if atts and (batch_since_commit >= 20 or idx == len(issues)):
                commit_attachments_batch(f"batch ending at {key}", args.dry_run)
                batch_since_commit = 0

            issue_num = gh_create_issue(args.repo, title, body, gh_labels)
            if issue_num is None:
                skipped.append({"key": key, "reason": "gh create failed"})
                continue

            # Back-patch DynamoDB feedback row if we can
            if feedback_id and tenant_id:
                patch_feedback_with_issue(feedback_id, tenant_id, issue_num, key, args.dry_run)

            created.append({
                "key": key, "title": title, "labels": gh_labels,
                "attachments": len(atts), "feedback_id": feedback_id, "issue_number": issue_num,
            })
            print(f"[{idx}/{len(issues)}] {key} -> #{issue_num} ({len(atts)} atts)")

            # Polite pacing to avoid JIRA + GitHub rate limits
            time.sleep(0.2)

        # Final commit for any straggler attachments
        if not args.dry_run and batch_since_commit > 0:
            commit_attachments_batch("final batch", args.dry_run)

    # Summary report
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    summary_path = REPO_ROOT / "docs" / "development" / f"{ts}-report-jira-migration-v1.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# JIRA → GitHub Migration Report",
        f"",
        f"- **Run:** {datetime.now(timezone.utc).isoformat()}",
        f"- **Repo:** {args.repo}",
        f"- **JQL:** `{args.jql}`",
        f"- **Mode:** {'dry-run' if args.dry_run else 'live'}",
        f"- **Matched:** {len(issues)}   **Created:** {len(created)}   **Skipped:** {len(skipped)}",
        f"",
        f"## Created",
        f"",
    ]
    for c in created:
        num_str = f"#{c['issue_number']}" if c['issue_number'] else "(dry-run)"
        lines.append(f"- {c['key']} → {num_str} — {c['title'][:80]} — {c['attachments']} atts")
    lines += ["", "## Skipped", ""]
    for s in skipped:
        lines.append(f"- {s['key']}: {s['reason']}")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[summary] {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
