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


def deploy_report_card(
    environment: str,
    deploy_mode: str,
    commit_sha: str,
    branch: str,
    author: str,
    results: list[dict],
    mvp1_results: list[dict],
    jira_summary: list[dict],
    deploy_status: dict,
    run_url: str = "",
    pr_url: str = "",
) -> dict:
    """Build an Adaptive Card for deploy pipeline report.

    results: [{"level": "L1", "name": "Lint", "status": "PASS", "detail": "ruff 0 errors"}]
    mvp1_results: [{"test_id": 35, "uc": "UC-01", "name": "New Acquisition", "status": "PASS"}]
    jira_summary: [{"key": "EAGLE-42", "action": "transitioned to Done"}]
    deploy_status: {"infra": "PASS", "backend": "PASS", "frontend": "SKIP"}
    """
    non_fail = ("PASS", "SKIP", "CANCEL")
    all_pass = all(r["status"] in non_fail for r in results)
    deploy_ok = all(v in non_fail for v in deploy_status.values())
    cancelled = any(r["status"] == "CANCEL" for r in results) or any(v == "CANCEL" for v in deploy_status.values())
    style = "warning" if cancelled else ("good" if (all_pass and deploy_ok) else "attention")

    facts = [
        {"title": "Commit", "value": commit_sha[:10]},
        {"title": "Author", "value": author},
        {"title": "Branch", "value": branch},
        {"title": "Mode", "value": deploy_mode.upper()},
    ]

    # Validation ladder
    ladder_lines = []
    for r in results:
        icon = "PASS" if r["status"] == "PASS" else ("SKIP" if r["status"] == "SKIP" else "FAIL")
        detail = f" — {r['detail']}" if r.get("detail") else ""
        ladder_lines.append(f"**{r['level']}** {r['name']}: {icon}{detail}")

    # MVP1 eval section
    mvp1_lines = []
    if mvp1_results:
        mvp1_pass = sum(1 for m in mvp1_results if m["status"] == "PASS")
        mvp1_total = len(mvp1_results)
        mvp1_lines.append(f"**MVP1 Eval** ({mvp1_pass}/{mvp1_total} pass)")
        for m in mvp1_results:
            icon = "PASS" if m["status"] == "PASS" else "FAIL"
            mvp1_lines.append(f"  {m['uc']} {m['name']}: {icon}")

    # Deploy status
    deploy_lines = []
    for component, status in deploy_status.items():
        deploy_lines.append(f"**{component}**: {status}")

    # Jira
    jira_lines = []
    for j in jira_summary:
        jira_lines.append(f"[{j['key']}] {j['action']}")

    sections = []
    if ladder_lines:
        sections.append("**Validation**\n\n" + "\n\n".join(ladder_lines))
    if mvp1_lines:
        sections.append("\n\n".join(mvp1_lines))
    if deploy_lines:
        sections.append("**Deploy**\n\n" + " | ".join(deploy_lines))
    if jira_lines:
        sections.append("**Jira**\n\n" + "\n\n".join(jira_lines))

    body_text = "\n\n---\n\n".join(sections)

    actions = []
    if run_url:
        actions.append({"type": "Action.OpenUrl", "title": "View Run on GitHub", "url": run_url})
    if pr_url:
        actions.append({"type": "Action.OpenUrl", "title": "View PR", "url": pr_url})

    suffix = "Cancelled" if cancelled else deploy_mode.capitalize()
    return _card(
        title=f"EAGLE {environment.upper()} | Deploy Report — {suffix}",
        facts=facts,
        body_text=body_text,
        style=style,
        actions=actions or None,
    )


def eval_report_card(
    environment: str,
    date: str,
    tier1_pass: int,
    tier1_total: int,
    tier2_pass: int,
    tier2_total: int,
    tier3_pass: int,
    tier3_total: int,
    tier3_run: bool,
    failed_tests: list[str],
    elapsed_seconds: float,
    langfuse_url: str = "",
    cloudwatch_url: str = "",
) -> dict:
    """Build an Adaptive Card for the mvp1-eval suite results."""
    all_pass = (
        tier1_pass == tier1_total
        and tier2_pass == tier2_total
        and (not tier3_run or tier3_pass == tier3_total)
    )
    style = "good" if all_pass else "attention"

    total_pass = tier1_pass + tier2_pass + (tier3_pass if tier3_run else 0)
    total = tier1_total + tier2_total + (tier3_total if tier3_run else 0)
    tier3_value = f"{tier3_pass}/{tier3_total}" if tier3_run else "SKIPPED"

    facts = [
        {"title": "Date", "value": date},
        {"title": "Environment", "value": environment},
        {"title": "Tier 1 — Unit", "value": f"{tier1_pass}/{tier1_total}"},
        {"title": "Tier 2 — Integration", "value": f"{tier2_pass}/{tier2_total}"},
        {"title": "Tier 3 — Full Eval", "value": tier3_value},
        {"title": "Total", "value": f"{total_pass}/{total} passed"},
        {"title": "Duration", "value": f"{elapsed_seconds:.0f}s"},
    ]

    if all_pass:
        body_text = f"All {total} tests passed."
    else:
        lines = [f"**{len(failed_tests)} failing:**"]
        for t in failed_tests[:10]:
            lines.append(f"- {t}")
        if len(failed_tests) > 10:
            lines.append(f"*...and {len(failed_tests) - 10} more*")
        body_text = "\n\n".join(lines)

    actions = []
    if langfuse_url:
        actions.append({"type": "Action.OpenUrl", "title": "Langfuse Traces", "url": langfuse_url})
    if cloudwatch_url:
        actions.append({"type": "Action.OpenUrl", "title": "CloudWatch Logs", "url": cloudwatch_url})

    status_label = "All Pass" if all_pass else f"{len(failed_tests)} Failed"
    return _card(
        title=f"EAGLE {environment} | Eval Report — {status_label}",
        facts=facts,
        body_text=body_text,
        style=style,
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
    from datetime import datetime, timezone

    facts = [
        {"title": "Event", "value": event_type},
        {"title": "Detail", "value": detail or "(no path)"},
        {"title": "Time", "value": datetime.now(timezone.utc).strftime("%H:%M:%S UTC")},
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
