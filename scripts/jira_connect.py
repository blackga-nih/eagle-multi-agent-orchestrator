"""
Jira connection utility for NCI tracker (self-hosted Jira with PAT auth).

Auth: Bearer token (Personal Access Token) — no email/password needed.
Env vars: JIRA_BASE_URL, JIRA_API_TOKEN (loaded from .env or environment).
"""

import argparse
import os
import sys
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

JIRA_BASE_URL = os.getenv("JIRA_BASE_URL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")


def get_headers():
    return {
        "Authorization": f"Bearer {JIRA_API_TOKEN}",
        "Content-Type": "application/json",
    }


def test_connection():
    """Test the Jira connection by fetching current user info."""
    url = f"{JIRA_BASE_URL}/rest/api/2/myself"
    resp = requests.get(url, headers=get_headers())

    if resp.status_code == 200:
        user = resp.json()
        print(f"Connected to Jira as: {user.get('displayName')} ({user.get('emailAddress')})")
        return user
    else:
        print(f"Connection failed: {resp.status_code} - {resp.text}")
        return None


def get_projects():
    """List all accessible Jira projects."""
    url = f"{JIRA_BASE_URL}/rest/api/2/project"
    resp = requests.get(url, headers=get_headers())

    if resp.status_code == 200:
        projects = resp.json()
        print(f"\nAccessible projects ({len(projects)}):")
        for p in projects:
            print(f"  [{p['key']}] {p['name']}")
        return projects
    else:
        print(f"Failed to fetch projects: {resp.status_code} - {resp.text}")
        return None


def search_issues(jql, max_results=10):
    """Search issues using JQL."""
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    params = {"jql": jql, "maxResults": max_results}
    resp = requests.get(url, headers=get_headers(), params=params)

    if resp.status_code == 200:
        data = resp.json()
        print(f"\nFound {data['total']} issues (showing {len(data['issues'])}):")
        for issue in data["issues"]:
            print(f"  [{issue['key']}] {issue['fields']['summary']} - {issue['fields']['status']['name']}")
        return data
    else:
        print(f"Search failed: {resp.status_code} - {resp.text}")
        return None


def add_comment(issue_key: str, body: str) -> bool:
    """Add a comment to a Jira issue. Returns True on success."""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/comment"
    payload = {"body": body}
    resp = requests.post(url, headers=get_headers(), json=payload)
    if resp.status_code in (200, 201):
        return True
    print(f"Failed to comment on {issue_key}: {resp.status_code} - {resp.text}")
    return False


def find_issue_by_summary(project_key: str, summary: str, quiet: bool = True) -> str | None:
    """Find an issue in the project with matching summary. Returns issue key or None.

    Uses JQL 'summary ~ "text"' (contains) then verifies exact match client-side,
    because some Jira instances don't support 'summary = "text"' (exact operator).
    """
    escaped = summary.replace("\\", "\\\\").replace('"', '\\"')
    jql = f'project = "{project_key}" AND summary ~ "{escaped}"'
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    params = {"jql": jql, "maxResults": 10, "fields": "summary"}
    resp = requests.get(url, headers=get_headers(), params=params)
    if resp.status_code != 200:
        if not quiet:
            print(f"Search failed: {resp.status_code} - {resp.text}")
        return None
    data = resp.json()
    # Client-side exact match since ~ is a contains operator
    for issue in data.get("issues", []):
        if issue["fields"]["summary"].strip() == summary.strip():
            return issue["key"]
    return None


def create_issue(
    project_key: str,
    summary: str,
    issue_type: str = "Task",
    description: str | None = None,
) -> str | None:
    """Create an issue. Returns issue key or None."""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue"
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
    }
    if description is not None:
        payload["fields"]["description"] = description
    resp = requests.post(url, headers=get_headers(), json=payload)
    if resp.status_code in (200, 201):
        data = resp.json()
        return data.get("key")
    print(f"Failed to create issue: {resp.status_code} - {resp.text}")
    return None


def fetch_board_issues(board_id: int, max_results: int = 50) -> list[dict]:
    """Fetch all open (non-Done) issues from an Agile board by board ID.

    Uses the Agile REST API — returns issues regardless of assignee.
    Returns list of dicts: {key, summary, labels, description, assignee, status}
    """
    url = f"{JIRA_BASE_URL}/rest/agile/1.0/board/{board_id}/issue"
    params = {
        "maxResults": max_results,
        "fields": "summary,labels,description,assignee,status",
    }
    resp = requests.get(url, headers=get_headers(), params=params)
    if resp.status_code != 200:
        print(f"Failed to fetch board {board_id} issues: {resp.status_code} - {resp.text}")
        return []
    data = resp.json()
    results = []
    for issue in data.get("issues", []):
        fields = issue["fields"]
        status_cat = (fields.get("status", {}).get("statusCategory", {}) or {}).get("key", "")
        if status_cat == "done":
            continue  # skip completed items client-side
        assignee_obj = fields.get("assignee") or {}
        results.append({
            "key": issue["key"],
            "summary": fields.get("summary", ""),
            "labels": fields.get("labels", []),
            "description": (fields.get("description") or "")[:500],
            "assignee": assignee_obj.get("displayName", "unassigned"),
            "status": fields.get("status", {}).get("name", ""),
        })
    return results


def get_transitions(issue_key: str) -> list[dict]:
    """Return available transitions for an issue as [{id, name}, ...]."""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/transitions"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200:
        print(f"Failed to get transitions for {issue_key}: {resp.status_code} - {resp.text}")
        return []
    return [{"id": t["id"], "name": t["to"]["name"]} for t in resp.json().get("transitions", [])]


def transition_issue(issue_key: str, target_status: str) -> bool:
    """Transition an issue to the named status. Returns True on success.

    Fetches available transitions and picks the first one whose target status
    name matches (case-insensitive). Prints available options if no match found.
    """
    transitions = get_transitions(issue_key)
    match = next((t for t in transitions if t["name"].lower() == target_status.lower()), None)
    if not match:
        available = ", ".join(t["name"] for t in transitions)
        print(f"No transition to '{target_status}' for {issue_key}. Available: {available}")
        return False
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/transitions"
    resp = requests.post(url, headers=get_headers(), json={"transition": {"id": match["id"]}})
    if resp.status_code == 204:
        return True
    print(f"Transition failed for {issue_key}: {resp.status_code} - {resp.text}")
    return False


def fetch_open_issues(project_key, assignees=None, max_results=50):
    """Fetch open issues (not Done), optionally filtered to specific assignees only.

    Returns list of dicts: {key, summary, labels, description, assignee}
    """
    assignee_clause = ""
    if assignees:
        quoted = ", ".join(f'"{a}"' for a in assignees)
        assignee_clause = f" AND assignee in ({quoted})"
    jql = (
        f'project = "{project_key}" AND status != "Done"'
        f"{assignee_clause} ORDER BY updated DESC"
    )
    url = f"{JIRA_BASE_URL}/rest/api/2/search"
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,labels,description,assignee,status",
    }
    resp = requests.get(url, headers=get_headers(), params=params)
    if resp.status_code != 200:
        print(f"Failed to fetch issues: {resp.status_code} - {resp.text}")
        return []
    data = resp.json()
    results = []
    for issue in data.get("issues", []):
        fields = issue["fields"]
        assignee_obj = fields.get("assignee") or {}
        results.append({
            "key": issue["key"],
            "summary": fields.get("summary", ""),
            "labels": fields.get("labels", []),
            "description": (fields.get("description") or "")[:500],
            "assignee": assignee_obj.get("displayName", ""),
            "status": fields.get("status", {}).get("name", ""),
        })
    return results


def dry_run():
    """Validate env vars and print what API calls would be made (no HTTP requests)."""
    errors = []
    print("=== Jira Connect Dry Run ===\n")

    # Check env vars
    if not JIRA_BASE_URL:
        errors.append("JIRA_BASE_URL is not set")
    else:
        parsed = urlparse(JIRA_BASE_URL)
        if not parsed.scheme or not parsed.netloc:
            errors.append(f"JIRA_BASE_URL is not a valid URL: {JIRA_BASE_URL}")
        else:
            print(f"  JIRA_BASE_URL : {JIRA_BASE_URL}")
            print(f"    scheme      : {parsed.scheme}")
            print(f"    host        : {parsed.netloc}")

    if not JIRA_API_TOKEN:
        errors.append("JIRA_API_TOKEN is not set")
    else:
        print(f"  JIRA_API_TOKEN: [set, {len(JIRA_API_TOKEN)} chars]")

    print(f"\n  Auth method   : Bearer PAT (self-hosted Jira)")
    print(f"  API version   : REST API v2")

    # Show what endpoints would be called
    print(f"\n--- Endpoints that would be called ---")
    base = JIRA_BASE_URL or "<MISSING>"
    print(f"  test_connection : GET  {base}/rest/api/2/myself")
    print(f"  get_projects    : GET  {base}/rest/api/2/project")
    print(f"  search_issues   : GET  {base}/rest/api/2/search?jql=...")
    print(f"  add_comment     : POST {base}/rest/api/2/issue/{{key}}/comment")
    print(f"  create_issue    : POST {base}/rest/api/2/issue")
    print(f"  find_by_summary : GET  {base}/rest/api/2/search?jql=project=...AND summary=...")
    print(f"  fetch_open_issues: GET  {base}/rest/api/2/search?jql=project=...AND status!=Done")

    if errors:
        print(f"\n  ERRORS:")
        for e in errors:
            print(f"    - {e}")
        return False

    print(f"\n  Result: ALL CHECKS PASSED")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jira connection utility (NCI self-hosted, PAT auth)")
    parser.add_argument("--dry-run", action="store_true", help="Validate config without making API calls")
    args = parser.parse_args()

    if args.dry_run:
        ok = dry_run()
        sys.exit(0 if ok else 1)

    print("Testing Jira connection...\n")
    user = test_connection()
    if user:
        get_projects()
