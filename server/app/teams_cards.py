"""
Adaptive Card builders for Teams webhook notifications.

Builds cards following the Microsoft Adaptive Card schema v1.4.
The Azure Logic App webhook accepts the Power Automate envelope:
  { "type": "message", "attachments": [{ "contentType": "...", "content": <card> }] }

Each builder returns a dict ready to POST as JSON.

Styles reference (Container.style):
  - "default"   — no background
  - "emphasis"   — subtle gray
  - "good"       — green
  - "attention"  — red
  - "warning"    — yellow
  - "accent"     — blue
"""

from __future__ import annotations


def _wrap_card(card: dict) -> dict:
    """Wrap an Adaptive Card in the Power Automate webhook envelope."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def _card(
    title: str,
    facts: list[dict],
    body_text: str = "",
    style: str = "default",
    actions: list[dict] | None = None,
) -> dict:
    """Build a generic Adaptive Card."""
    card_body: list[dict] = [
        {
            "type": "Container",
            "style": style,
            "bleed": True,
            "items": [
                {
                    "type": "TextBlock",
                    "text": title,
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                }
            ],
        },
        {
            "type": "FactSet",
            "facts": facts,
        },
    ]
    if body_text:
        card_body.append({
            "type": "TextBlock",
            "text": body_text,
            "wrap": True,
            "spacing": "Medium",
        })

    card: dict = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "msteams": {"width": "Full"},
        "body": card_body,
    }
    if actions:
        card["actions"] = actions
    return _wrap_card(card)


# ── Public card builders ─────────────────────────────────────────────

def error_card(
    environment: str,
    status_code: int,
    method: str,
    path: str,
    error_type: str,
    error_message: str,
    tenant_id: str = "",
    user_id: str = "",
    session_id: str = "",
    request_id: str = "",
    timestamp: str = "",
) -> dict:
    """Build an Adaptive Card for a 5xx error notification."""
    facts = [
        {"title": "Status", "value": str(status_code)},
        {"title": "Endpoint", "value": f"{method} {path}"},
        {"title": "Error", "value": error_type},
    ]
    if tenant_id:
        facts.append({"title": "Tenant", "value": tenant_id})
    if user_id:
        facts.append({"title": "User", "value": user_id})
    if session_id:
        facts.append({"title": "Session", "value": session_id[:36]})
    if timestamp:
        facts.append({"title": "Time", "value": timestamp})

    # Truncate long error messages
    msg = error_message[:500] + ("..." if len(error_message) > 500 else "")

    return _card(
        title=f"EAGLE {environment} | {status_code} Error",
        facts=facts,
        body_text=msg,
        style="attention",
    )


def feedback_card(
    environment: str,
    tenant_id: str,
    user_id: str,
    tier: str,
    session_id: str,
    feedback_text: str,
    feedback_type: str = "general",
    page: str = "",
) -> dict:
    """Build an Adaptive Card for user feedback."""
    facts = [
        {"title": "Type", "value": feedback_type or "general"},
        {"title": "User", "value": f"{user_id} ({tier})"},
        {"title": "Tenant", "value": tenant_id},
    ]
    if page:
        facts.append({"title": "Page", "value": page})
    if session_id:
        facts.append({"title": "Session", "value": session_id[:36]})

    truncated = feedback_text[:500] + ("..." if len(feedback_text) > 500 else "")

    return _card(
        title=f"EAGLE {environment} | Feedback",
        facts=facts,
        body_text=truncated,
        style="accent",
    )


def daily_summary_card(
    environment: str,
    date: str,
    requests: int,
    tokens: int,
    cost: float,
    active_users: int,
    feedback_count: int,
    feedback_breakdown: str,
) -> dict:
    """Build an Adaptive Card for the daily usage summary."""
    facts = [
        {"title": "Requests", "value": f"{requests:,}"},
        {"title": "Tokens", "value": f"{tokens:,}"},
        {"title": "Cost", "value": f"${cost:.4f}"},
        {"title": "Active Users", "value": str(active_users)},
        {"title": "Feedback", "value": f"{feedback_count} new ({feedback_breakdown})"},
    ]

    return _card(
        title=f"EAGLE {environment} | Daily Summary — {date}",
        facts=facts,
        style="default",
    )


def startup_card(
    environment: str,
    hostname: str,
    timestamp: str,
) -> dict:
    """Build an Adaptive Card for service startup."""
    facts = [
        {"title": "Hostname", "value": hostname},
        {"title": "Time", "value": timestamp},
        {"title": "Webhook", "value": "enabled"},
    ]

    return _card(
        title=f"EAGLE {environment} | Service Started",
        facts=facts,
        style="good",
    )


def morning_report_card(
    repo: str,
    branch: str,
    date: str,
    commit_count: int,
    authors: list[str],
    commits: list[dict],
    repo_url: str = "",
) -> dict:
    """Build an Adaptive Card for the GitHub morning commit report.

    commits: list of {"sha": "abc1234", "author": "name", "message": "...", "files_changed": 5}
    """
    facts = [
        {"title": "Repository", "value": repo},
        {"title": "Branch", "value": branch},
        {"title": "Period", "value": date},
        {"title": "Commits", "value": str(commit_count)},
        {"title": "Authors", "value": ", ".join(authors) if authors else "none"},
    ]

    # Build commit list as markdown-ish text (Adaptive Card TextBlock)
    commit_lines = []
    for c in commits[:15]:  # Cap at 15 to avoid card size limits
        sha = c.get("sha", "")[:7]
        author = c.get("author", "unknown")
        msg = c.get("message", "").split("\n")[0][:80]
        files = c.get("files_changed", 0)
        commit_lines.append(f"**{sha}** ({author}) {msg} — {files} files")

    if commit_count > 15:
        commit_lines.append(f"*...and {commit_count - 15} more*")

    body_text = "\n\n".join(commit_lines) if commit_lines else "*No commits in this period.*"

    actions = []
    if repo_url:
        actions.append({
            "type": "Action.OpenUrl",
            "title": "View on GitHub",
            "url": repo_url,
        })

    return _card(
        title=f"EAGLE | Morning Report — {date}",
        facts=facts,
        body_text=body_text,
        style="accent",
        actions=actions or None,
    )


def suspicious_card(
    environment: str,
    event_type: str,
    detail: str,
    tenant_id: str = "",
    user_id: str = "",
) -> dict:
    """Build an Adaptive Card for suspicious activity."""
    facts = [
        {"title": "Event", "value": event_type},
        {"title": "Detail", "value": detail},
    ]
    if tenant_id:
        facts.append({"title": "Tenant", "value": tenant_id})
    if user_id:
        facts.append({"title": "User", "value": user_id})

    return _card(
        title=f"EAGLE {environment} | Suspicious Activity",
        facts=facts,
        style="warning",
    )
