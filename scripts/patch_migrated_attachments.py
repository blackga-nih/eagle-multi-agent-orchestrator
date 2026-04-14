"""Second pass for migrate_jira_to_github.py: download JIRA attachments and
edit the already-migrated GitHub issues to add a permanent attachments
section.

The initial migration skipped attachments because raw.githubusercontent.com
URLs bake in a branch name, and /main/ wouldn't resolve until this feature
branch lands. This script uses SHA-pinned raw URLs instead — those are
permanent even if the branch is later deleted or rewritten.

Flow:
  1. List every `migrated-from-jira` GitHub issue, extract the JIRA key from
     its HTML-comment fingerprint.
  2. For each JIRA key, fetch attachments via the REST v2 API, skip anything
     already on disk, skip >2MB files, save under
     docs/development/triage-attachments/{KEY}/.
  3. `git add` + `git commit` the new files.
  4. `git push` (required — raw URLs 404 until origin has the commit).
  5. Read the new HEAD SHA.
  6. For each issue with new attachments, fetch its body, inject an
     "### Attachments" section with SHA-pinned raw URLs above the
     `_Migrated from JIRA by ..._` footer, edit via `gh issue edit`.

Usage:
    python scripts/patch_migrated_attachments.py --repo=CBIIT/sm_eagle --dry-run
    python scripts/patch_migrated_attachments.py --repo=CBIIT/sm_eagle --push
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO_ROOT = Path(__file__).resolve().parent.parent
ATTACHMENTS_SUBDIR = Path("docs/development/triage-attachments")

MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 80 * 1024 * 1024
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

JIRA_KEY_COMMENT = re.compile(r"<!--\s*auto-triage-jira-key:\s*([A-Z]+-\d+)\s*-->")
FOOTER_PATTERN = re.compile(
    r"(\n---\n_Migrated from JIRA by `scripts/migrate_jira_to_github\.py`_\n?)",
    re.DOTALL,
)
EXISTING_ATTACHMENTS_BLOCK = re.compile(
    r"\n### Attachments\n.*?(?=\n---\n_Migrated from JIRA)",
    re.DOTALL,
)


# ── JIRA helpers ────────────────────────────────────────────────────

def _jira_auth_header() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.getenv('JIRA_API_TOKEN', '')}"}


def _jira_headers() -> dict[str, str]:
    return {**_jira_auth_header(), "Accept": "application/json"}


def fetch_jira_attachments(client: httpx.Client, jira_key: str) -> list[dict]:
    base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    r = client.get(
        f"{base}/rest/api/2/issue/{jira_key}?fields=attachment",
        headers=_jira_headers(),
        timeout=30,
    )
    if r.status_code != 200:
        print(f"  [jira] {jira_key}: fetch failed {r.status_code}", file=sys.stderr)
        return []
    return (r.json().get("fields") or {}).get("attachment") or []


def download_attachment(client: httpx.Client, url: str) -> Optional[bytes]:
    r = client.get(url, headers=_jira_auth_header(), timeout=60)
    if r.status_code != 200:
        print(f"  [attachment] {r.status_code} {url[:80]}", file=sys.stderr)
        return None
    return r.content


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:120]


# ── gh CLI helpers ──────────────────────────────────────────────────

def _run(cmd: list[str], input_text: Optional[str] = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, input=input_text)


def _git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return _run(["git", "-C", str(REPO_ROOT)] + args, check=check)


def list_migrated_issues(repo: str) -> list[dict]:
    proc = _run(
        [
            "gh", "issue", "list",
            "--repo", repo,
            "--label", "migrated-from-jira",
            "--state", "all",
            "--limit", "2000",
            "--json", "number,body,title",
        ],
        check=True,
    )
    return json.loads(proc.stdout or "[]")


def gh_edit_body(repo: str, number: int, body: str) -> bool:
    try:
        _run(
            ["gh", "issue", "edit", str(number), "--repo", repo, "--body-file", "-"],
            input_text=body,
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [gh] edit #{number} failed: {e.stderr[:200]}", file=sys.stderr)
        return False


# ── attachments section builder ─────────────────────────────────────

def build_attachments_section(atts: list[dict], repo: str, sha: str) -> str:
    lines = ["", "### Attachments", ""]
    for a in atts:
        rel_path = f"{ATTACHMENTS_SUBDIR.as_posix()}/{a['jira_key']}/{a['filename']}"
        quoted = "/".join(quote(p) for p in rel_path.split("/"))
        raw_url = f"https://raw.githubusercontent.com/{repo}/{sha}/{quoted}"
        ext = Path(a["filename"]).suffix.lower()
        if ext in IMAGE_EXTS:
            lines.append(f"![{a['filename']}]({raw_url})")
        else:
            lines.append(f"- [{a['filename']}]({raw_url}) ({a['size']:,} bytes)")
    return "\n".join(lines) + "\n"


def inject_attachments_into_body(body: str, attachments_md: str) -> str:
    """Remove any prior attachments block, then insert above the footer."""
    stripped = EXISTING_ATTACHMENTS_BLOCK.sub("", body)
    if not FOOTER_PATTERN.search(stripped):
        # No migration footer found — append at the end
        return stripped.rstrip() + "\n\n" + attachments_md
    return FOOTER_PATTERN.sub(lambda m: "\n" + attachments_md + m.group(1), stripped, count=1)


# ── main flow ───────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--push", action="store_true", help="git push after committing attachments")
    ap.add_argument("--limit", type=int, default=0, help="Cap tickets processed (0 = no cap)")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        env_file = REPO_ROOT / "server" / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass

    if not (os.getenv("JIRA_BASE_URL") and os.getenv("JIRA_API_TOKEN")):
        print("ERROR: JIRA_BASE_URL / JIRA_API_TOKEN missing", file=sys.stderr)
        return 2

    print(f"[1/5] listing migrated GitHub issues in {args.repo}")
    issues = list_migrated_issues(args.repo)
    jira_map: dict[str, dict] = {}
    for issue in issues:
        m = JIRA_KEY_COMMENT.search(issue.get("body") or "")
        if m:
            jira_map[m.group(1)] = issue
    print(f"      found {len(jira_map)} issues with JIRA key comment")

    if args.limit:
        keys = list(jira_map.keys())[: args.limit]
        jira_map = {k: jira_map[k] for k in keys}

    print(f"[2/5] fetching attachments for {len(jira_map)} JIRA tickets")
    client = httpx.Client(timeout=60.0)
    all_new_attachments: dict[str, list[dict]] = {}  # jira_key -> [{filename,size,is_image}]
    total_bytes = 0

    for idx, (jira_key, issue) in enumerate(sorted(jira_map.items()), start=1):
        atts = fetch_jira_attachments(client, jira_key)
        if not atts:
            continue

        out_dir = REPO_ROOT / ATTACHMENTS_SUBDIR / jira_key
        kept: list[dict] = []

        for att in atts:
            size = int(att.get("size", 0))
            raw_name = _safe_filename(att.get("filename", "attachment"))
            if size > MAX_ATTACHMENT_BYTES:
                print(f"  [{idx}/{len(jira_map)}] {jira_key}/{raw_name}: {size:,}B >2MB, skip")
                continue
            if total_bytes + size > MAX_TOTAL_BYTES:
                print(f"  [{idx}/{len(jira_map)}] {jira_key}/{raw_name}: run byte budget exhausted")
                break

            dest = out_dir / raw_name
            if dest.exists() and dest.stat().st_size == size:
                kept.append({"jira_key": jira_key, "filename": raw_name, "size": size})
                continue

            if args.dry_run:
                print(f"  [{idx}/{len(jira_map)}] {jira_key}/{raw_name}: WOULD download ({size:,}B)")
                kept.append({"jira_key": jira_key, "filename": raw_name, "size": size})
                continue

            data = download_attachment(client, att.get("content", ""))
            if data is None:
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            total_bytes += len(data)
            print(f"  [{idx}/{len(jira_map)}] {jira_key}/{raw_name} ({size:,}B)")
            kept.append({"jira_key": jira_key, "filename": raw_name, "size": size})

        if kept:
            all_new_attachments[jira_key] = kept

    client.close()

    print(f"[3/5] downloaded {sum(len(v) for v in all_new_attachments.values())} attachments "
          f"across {len(all_new_attachments)} tickets ({total_bytes:,} bytes)")

    if not all_new_attachments:
        print("Nothing to commit — exiting clean.")
        return 0

    # Stage + commit
    if args.dry_run:
        print("[4/5] DRY RUN — skipping commit/push/edit")
        return 0

    _git(["add", f"{ATTACHMENTS_SUBDIR.as_posix()}/"], check=False)
    diff = _git(["diff", "--cached", "--quiet"], check=False)
    if diff.returncode != 0:
        msg = (
            "chore: backfill migrated JIRA attachments\n\n"
            f"Downloads {sum(len(v) for v in all_new_attachments.values())} files across "
            f"{len(all_new_attachments)} tickets into docs/development/triage-attachments/.\n"
            "SHA-pinned raw URLs in the migrated GitHub issue bodies reference this commit.\n\n"
            "Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>\n"
        )
        _git(["commit", "-m", msg], check=True)
        print("[4/5] committed attachment batch")
    else:
        print("[4/5] nothing staged (already committed)")

    if args.push:
        print("[4/5] pushing branch to origin…")
        _git(["push"], check=True)

    sha = _git(["rev-parse", "HEAD"], check=True).stdout.strip()
    print(f"[4/5] HEAD sha: {sha}")

    # Edit issue bodies
    print(f"[5/5] editing {len(all_new_attachments)} GitHub issues")
    edited = 0
    for jira_key, atts in sorted(all_new_attachments.items()):
        issue = jira_map[jira_key]
        current_body = issue.get("body") or ""
        section = build_attachments_section(atts, args.repo, sha)
        new_body = inject_attachments_into_body(current_body, section)
        if new_body == current_body:
            continue
        if gh_edit_body(args.repo, issue["number"], new_body):
            edited += 1
            print(f"  {jira_key} -> #{issue['number']}  ({len(atts)} atts)")

    print(f"[done] edited {edited} issues")

    # Summary report
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = REPO_ROOT / "docs" / "development" / f"{ts}-report-attachments-backfill-v1.md"
    lines = [
        "# JIRA Attachments Backfill Report",
        "",
        f"- **Run:** {datetime.now(timezone.utc).isoformat()}",
        f"- **Repo:** {args.repo}",
        f"- **SHA:** `{sha}`",
        f"- **Tickets w/ attachments:** {len(all_new_attachments)}",
        f"- **Files committed:** {sum(len(v) for v in all_new_attachments.values())}",
        f"- **Bytes committed:** {total_bytes:,}",
        f"- **Issues edited:** {edited}",
        "",
        "## Per-ticket",
        "",
    ]
    for jira_key, atts in sorted(all_new_attachments.items()):
        num = jira_map[jira_key]["number"]
        for a in atts:
            lines.append(f"- {jira_key} → #{num} — `{a['filename']}` ({a['size']:,} bytes)")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[summary] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
