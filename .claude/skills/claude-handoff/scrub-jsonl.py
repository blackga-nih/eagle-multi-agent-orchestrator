"""Scrub credentials and personal identifiers out of Claude Code session JSONLs.

Designed to be safe to run multiple times — idempotent on already-scrubbed files.

Usage:
    python scrub-jsonl.py --src <source-dir> --dst <dest-dir> [--username NAME] [--email EMAIL]

What it redacts (per line, regex over raw JSONL text — no JSON parsing needed):

| Pattern                                          | Replacement                       |
|--------------------------------------------------|-----------------------------------|
| AWS access key id (`ASIA…` or `AKIA…` + 16 chars)| `<REDACTED_AWS_ACCESS_KEY>`       |
| `aws_secret_access_key = <value>`                | `aws_secret_access_key=<REDACTED>`|
| `aws_session_token = <value>` (any length blob)  | `aws_session_token=<REDACTED>`    |
| Anthropic key prefix `sk-ant-…` (real, len>=50)  | `<REDACTED_ANTHROPIC_KEY>`        |
| GitHub PAT prefix `ghp_…`, `gho_…`, `ghu_…`      | `<REDACTED_GITHUB_TOKEN>`         |
| `Bearer <jwt-shaped>` headers (eyJ… header form) | `Bearer <REDACTED_BEARER>`        |
| `--username` value as bare word                  | `<originator>`                    |
| `--email` value                                  | `<originator-email>`              |

Does NOT redact:
- AWS account numbers (12-digit IDs are not secret; they appear in every ARN)
- `sk-ant-...` literal placeholder strings (those are docs)
- Project paths the originator worked on (those are inherent to the session)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Order matters — most specific first.
SCRUB_RULES: list[tuple[re.Pattern, str]] = [
    # AWS access key IDs — STS (ASIA) or long-lived (AKIA)
    # No word boundaries — keys can be preceded by JSON-escaped control chars (, \x01, etc.)
    (re.compile(r"(?:ASIA|AKIA)[A-Z0-9]{16}"), "<REDACTED_AWS_ACCESS_KEY>"),
    # AWS secret access key — explicit assignment form
    # Optional `` escape sequence (literal 6-char form as it appears in JSONL) before the value
    (
        re.compile(r"aws_secret_access_key\s*=[\s\\u0\d]{0,16}[A-Za-z0-9+/=]{16,}"),
        "aws_secret_access_key=<REDACTED>",
    ),
    # AWS session token — explicit assignment form (long base64-ish blob)
    (
        re.compile(r"aws_session_token\s*=[\s\\u0\d]{0,16}[A-Za-z0-9+/=]{40,}"),
        "aws_session_token=<REDACTED>",
    ),
    # Anthropic key — real one is 95+ chars after the prefix; placeholders are `sk-ant-...`
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{50,}"), "<REDACTED_ANTHROPIC_KEY>"),
    # GitHub PATs
    (re.compile(r"\bgh[poursu]_[A-Za-z0-9]{36,}\b"), "<REDACTED_GITHUB_TOKEN>"),
    # Bearer tokens with JWT-shaped header (eyJ...)
    (re.compile(r"Bearer\s+eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"), "Bearer <REDACTED_BEARER>"),
    # Slack tokens
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "<REDACTED_SLACK_TOKEN>"),
    # Generic high-entropy assignment form: api_key/secret/token = "<value>"
    (
        re.compile(r'((?:api[_-]?key|secret|token|password)\s*[:=]\s*["\']?)[A-Za-z0-9+/=_-]{32,}["\']?', re.IGNORECASE),
        r"\1<REDACTED>",
    ),
]


def scrub_text(
    text: str,
    username_re: re.Pattern | None,
    email_re: re.Pattern | None,
    literal_res: list[re.Pattern] | None = None,
) -> tuple[str, dict[str, int]]:
    """Return (scrubbed_text, counts_by_rule)."""
    counts: dict[str, int] = {}
    for pattern, replacement in SCRUB_RULES:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[replacement] = counts.get(replacement, 0) + n
    if username_re is not None:
        text, n = username_re.subn("<originator>", text)
        if n:
            counts["<originator>"] = counts.get("<originator>", 0) + n
    if email_re is not None:
        text, n = email_re.subn("<originator-email>", text)
        if n:
            counts["<originator-email>"] = counts.get("<originator-email>", 0) + n
    for lit_re in literal_res or []:
        text, n = lit_re.subn("<REDACTED_LITERAL>", text)
        if n:
            counts["<REDACTED_LITERAL>"] = counts.get("<REDACTED_LITERAL>", 0) + n
    return text, counts


def scrub_file(
    src: Path,
    dst: Path,
    username_re: re.Pattern | None,
    email_re: re.Pattern | None,
    literal_res: list[re.Pattern] | None = None,
) -> dict[str, int]:
    text = src.read_text(encoding="utf-8", errors="replace")
    scrubbed, counts = scrub_text(text, username_re, email_re, literal_res)
    dst.write_text(scrubbed, encoding="utf-8")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True, help="Source directory with *.jsonl files")
    ap.add_argument("--dst", required=True, help="Destination directory (created if missing)")
    ap.add_argument("--username", help="GitHub/local username to redact (bare-word match, case-insensitive)")
    ap.add_argument("--email", help="Email address to redact (literal match)")
    ap.add_argument(
        "--scrub-literal",
        action="append",
        default=[],
        help="Literal substring to redact (repeatable). Use for known-leaked partial secrets the pattern rules missed.",
    )
    ap.add_argument("--verify", action="store_true", help="After scrubbing, re-scan output and exit non-zero if any sensitive pattern remains")
    args = ap.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)

    # No word boundaries — username can be adjacent to JSON-escaped control chars (\t, \n, etc.)
    # in raw JSONL form. The username is distinctive enough that false positives are negligible.
    username_re = (
        re.compile(re.escape(args.username), re.IGNORECASE) if args.username else None
    )
    email_re = re.compile(re.escape(args.email)) if args.email else None
    literal_res = [re.compile(re.escape(s)) for s in args.scrub_literal]

    total_counts: dict[str, int] = {}
    file_count = 0
    for src_file in sorted(src.glob("*.jsonl")):
        dst_file = dst / src_file.name
        counts = scrub_file(src_file, dst_file, username_re, email_re, literal_res)
        for k, v in counts.items():
            total_counts[k] = total_counts.get(k, 0) + v
        file_count += 1

    print(f"Scrubbed {file_count} files")
    if total_counts:
        print("Redactions by rule:")
        for k, v in sorted(total_counts.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
    else:
        print("No redactions needed (already clean)")

    if args.verify:
        leaks = []
        verify_patterns = [
            (r"(?:ASIA|AKIA)[A-Z0-9]{16}", "AWS access key"),
            # Must catch both `key=<value>` and `key = <value>` forms.
            # Use negative lookahead so we don't re-flag our own `<REDACTED>` placeholder.
            (r"aws_secret_access_key\s*=\s*(?!<REDACTED>)(?:\\u0001)?[A-Za-z0-9+/=]{16,}", "AWS secret"),
            (r"aws_session_token\s*=\s*(?!<REDACTED>)(?:\\u0001)?[A-Za-z0-9+/=]{40,}", "AWS session token"),
            (r"\bsk-ant-[A-Za-z0-9_-]{50,}", "Anthropic key"),
            (r"\bgh[poursu]_[A-Za-z0-9]{36,}\b", "GitHub PAT"),
        ]
        if args.username:
            verify_patterns.append((re.escape(args.username), "originator username"))
        for dst_file in dst.glob("*.jsonl"):
            text = dst_file.read_text(encoding="utf-8", errors="replace")
            for pat, label in verify_patterns:
                if re.search(pat, text):
                    leaks.append((dst_file.name, label))
        if leaks:
            print("\nVERIFY FAILED — sensitive patterns remain in scrubbed output:")
            for name, label in leaks:
                print(f"  {name}: {label}")
            return 1
        print("\nVerify passed — no sensitive patterns detected in scrubbed output")

    return 0


if __name__ == "__main__":
    sys.exit(main())
