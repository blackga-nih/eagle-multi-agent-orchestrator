"""
Server-side JIRA client for NCI self-hosted Jira (REST API v2, PAT auth).

Uses httpx (sync) for issue creation — the caller needs the ticket key
before building the Teams card. Graceful degradation: never raises,
returns None on any failure.

Config via server/app/config.py JiraConfig dataclass.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("eagle.jira_client")

_sync_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    """Lazy-init a sync httpx.Client with JIRA timeout."""
    global _sync_client
    if _sync_client is None:
        from .config import jira as jira_config

        _sync_client = httpx.Client(
            timeout=httpx.Timeout(jira_config.timeout),
            limits=httpx.Limits(max_connections=5),
        )
    return _sync_client


def close_jira_client() -> None:
    """Close the sync client. Call from app shutdown."""
    global _sync_client
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None


def _headers() -> dict[str, str]:
    from .config import jira as jira_config

    return {
        "Authorization": f"Bearer {jira_config.api_token}",
        "Content-Type": "application/json",
    }


def create_feedback_issue(
    summary: str,
    description: str,
    issue_type: str = "Task",
    labels: list[str] | None = None,
) -> Optional[str]:
    """Create a JIRA issue for user feedback.

    Returns issue key (e.g. "EAGLE-456") or None on failure.
    Never raises — logs and returns None on any error.
    """
    from .config import jira as jira_config

    if not jira_config.base_url or not jira_config.api_token:
        logger.warning("jira_client: base_url or api_token not configured, skipping")
        return None

    url = f"{jira_config.base_url}/rest/api/2/issue"
    payload: dict = {
        "fields": {
            "project": {"key": jira_config.project_key},
            "summary": summary[:255],
            "issuetype": {"name": issue_type},
        }
    }
    if description:
        payload["fields"]["description"] = description
    if labels:
        payload["fields"]["labels"] = labels

    try:
        client = _get_client()
        resp = client.post(url, headers=_headers(), json=payload)
        if resp.status_code in (200, 201):
            key = resp.json().get("key")
            logger.info("jira_client: created issue %s", key)
            return key
        logger.warning(
            "jira_client: create failed status=%d body=%s",
            resp.status_code,
            resp.text[:300],
        )
        return None
    except httpx.TimeoutException:
        logger.warning("jira_client: create timed out after %ss", jira_config.timeout)
        return None
    except Exception:
        logger.warning("jira_client: create failed", exc_info=True)
        return None


def get_issue_url(issue_key: str) -> str:
    """Return the browse URL for an issue."""
    from .config import jira as jira_config

    return f"{jira_config.base_url}/browse/{issue_key}"
