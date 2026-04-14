"""Build a Langfuse activity Adaptive Card and POST it to Teams.

Reuses `_summarize_langfuse` and `_langfuse_block` from scripts/morning_report.py
so the Teams formatting stays consistent with the daily morning report.

Usage:
    python scripts/langfuse_post_teams.py                       # 24h, all envs
    python scripts/langfuse_post_teams.py --window=4h --env=qa
    python scripts/langfuse_post_teams.py --dry-run             # print JSON, do not POST

Env:
    TEAMS_WEBHOOK_URL   — required (falls back to ERROR_WEBHOOK_URL)
    LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_PROJECT_ID — required
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Reuse helpers from morning_report.py
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from morning_report import _langfuse_block, _summarize_langfuse  # type: ignore  # noqa: E402


def build_card(summary: dict, window: str, env: str) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    body: list = [
        {
            "type": "Container",
            "style": "accent",
            "bleed": True,
            "items": [{
                "type": "TextBlock",
                "text": f"EAGLE | Langfuse Activity — {now}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            }],
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "Window", "value": window},
                {"title": "Env filter", "value": env},
                {"title": "Traces", "value": str(summary.get("trace_count", 0))},
                {"title": "Sessions", "value": str(summary.get("session_count", 0))},
                {"title": "Tool calls", "value": str(summary.get("tool_total", 0))},
                {"title": "Errors", "value": str(summary.get("error_total", 0))},
            ],
        },
    ]
    body.extend(_langfuse_block(summary))

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": body,
    }

    project_id = os.getenv("LANGFUSE_PROJECT_ID", "")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com").rstrip("/")
    if project_id:
        card["actions"] = [{
            "type": "Action.OpenUrl",
            "title": "Open in Langfuse",
            "url": f"{host}/project/{project_id}/traces",
        }]

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": card,
        }],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", default="24h", help="today, 1h, 4h, 24h, 7d")
    ap.add_argument("--env", default="all", help="all, local, dev, qa, prod")
    ap.add_argument("--dry-run", action="store_true", help="Print card JSON instead of posting")
    args = ap.parse_args()

    # Autoload server/.env so local `just` invocations pick up credentials.
    try:
        from dotenv import load_dotenv
        env_file = Path(__file__).resolve().parent.parent / "server" / ".env"
        if env_file.exists():
            load_dotenv(env_file)
    except ImportError:
        pass

    summary = _summarize_langfuse(window=args.window, env=args.env)
    if not summary:
        print(
            "[langfuse-post-teams] No Langfuse summary available — "
            "check LANGFUSE_PUBLIC_KEY/SECRET_KEY and API connectivity.",
            file=sys.stderr,
        )
        return 1

    card = build_card(summary, args.window, args.env)

    if args.dry_run:
        print(json.dumps(card, indent=2))
        return 0

    webhook = os.getenv("TEAMS_WEBHOOK_URL") or os.getenv("ERROR_WEBHOOK_URL")
    if not webhook:
        print(
            "[langfuse-post-teams] TEAMS_WEBHOOK_URL (or ERROR_WEBHOOK_URL) not set — "
            "cannot POST. Use --dry-run to preview.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[langfuse-post-teams] POSTing card: "
        f"{summary['trace_count']} traces, {summary['tool_total']} tool calls, "
        f"{summary['error_total']} errors"
    )
    resp = httpx.post(webhook, json=card, timeout=15)
    print(f"[langfuse-post-teams] status={resp.status_code}")
    if resp.status_code >= 300:
        print(f"[langfuse-post-teams] response: {resp.text[:300]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
