# Plan: Microsoft Teams Notifications

## Task Description

Build a multi-channel Microsoft Teams notification system for the EAGLE platform. Teams
channels receive automated messages triggered by GitHub Actions CI/CD pipelines — specifically:
per-push commit batches, Jira commit syncs, ECS deployments (backend + frontend), and
future eval runs. Every push also auto-comments on the Greg dev weekly Jira catch-all issue.

No Teams integration exists today. This plan adds it from scratch using Incoming Webhooks
and Adaptive Cards, following the same patterns as the existing Jira scripts system.

## Objective

1. Every push to any branch → batched commit card in Teams `#commits` channel + comments
   posted to the Greg dev weekly Jira issue via existing `jira_commits_sync.py --since SHA`.
2. Nightly Jira sync summary → Teams `#jira-updates` channel (existing workflow, add notify step).
3. ECS deploy events → Teams `#deployments` channel (existing deploy.yml, add notify job).
4. Eval runs (future) → Teams `#eval-results` channel (dormant webhook wired, ready to use).

## Problem Statement

The team has no visibility into CI/CD events without visiting GitHub Actions directly.
Jira syncs, deployments, and eval runs complete silently. A Teams notification layer
provides ambient awareness without requiring anyone to poll GitHub.

## Solution Approach

1. **Core Python module** (`scripts/teams_notify.py`) — posts Adaptive Cards to Teams via
   Incoming Webhook URLs. One function per notification type, one env var per channel.
2. **Test harness** (`scripts/teams_test.py`) — mirrors `jira_test.py` pattern with dry-run
   validation of env vars and a live ping card.
3. **GitHub Actions wiring** — new `on-push-notify.yml` for per-push events; add notify
   steps to `jira-commits-sync.yml` and `deploy.yml`; standalone `teams-test.yml`.
4. **Four channels / four secrets**:
   - `TEAMS_WEBHOOK_COMMITS` → #commits (every push, batched)
   - `TEAMS_WEBHOOK_JIRA` → #jira-updates (nightly sync summary)
   - `TEAMS_WEBHOOK_DEPLOY` → #deployments (ECS deploy events)
   - `TEAMS_WEBHOOK_EVAL` → #eval-results (wired, dormant until eval workflow exists)

Adaptive Cards v1.4 format — works in all modern Teams clients. Fallback plain text
included for older clients. No SDK required — plain `requests.post()` to the webhook URL.

## Relevant Files

- `scripts/jira_connect.py` — reference pattern for module structure + dry-run
- `scripts/jira_test.py` — reference pattern for test harness
- `.github/workflows/jira-commits-sync.yml` — add Teams notify step here
- `.github/workflows/deploy.yml` — add Teams notify steps (success + failure)

### New Files
- `scripts/teams_notify.py` — core Teams notification module (4 channels, `send_push_summary` added)
- `scripts/teams_test.py` — dry-run + live ping test harness
- `.github/workflows/on-push-notify.yml` — per-push: Teams batched card + Jira sync
- `.github/workflows/teams-test.yml` — manual workflow to send a test card to any channel

## Implementation Phases

### Phase 1: Foundation
Core Python module with Adaptive Card builder and dry-run validation.
No live webhook URL needed to complete this phase.

### Phase 2: Test Harness
Standalone test script validating env vars, dry-run mode, and optional live ping.
Mirrors jira_test.py structure so the team recognizes the pattern.

### Phase 3: CI/CD Integration
Wire notification steps into existing workflows. Add GitHub secrets documentation.
Validate end-to-end with a manual `workflow_dispatch` trigger.

### Phase 4: Per-Push Commits Channel
New `on-push-notify.yml` fires on every push to any branch. Posts a batched commit
card to Teams `#commits` and runs `jira_commits_sync.py --since <before_sha>` to
post each commit to the Greg dev weekly Jira catch-all issue.

---

## Step by Step Tasks

### 1. Create Teams webhook setup guide (inline in plan)

Teams Incoming Webhooks setup — one-time per channel:

```
1. Open Teams → navigate to the target channel
2. Click the ··· (ellipsis) on the channel → "Connectors" (or "Workflows" in new Teams)
3. Search for "Incoming Webhook" → click "Configure" or "Add"
4. Give it a name: "EAGLE CI/CD" → optionally upload the EAGLE logo
5. Click "Create" → copy the webhook URL (starts with https://outlook.office.com/...)
6. Repeat for each channel: #jira-updates, #deployments, #eval-results
7. Store each URL as a GitHub Actions secret (repo → Settings → Secrets → Actions):
   - TEAMS_WEBHOOK_JIRA
   - TEAMS_WEBHOOK_DEPLOY
   - TEAMS_WEBHOOK_EVAL
8. Optionally store in local .env for script testing:
   TEAMS_WEBHOOK_JIRA=https://outlook.office.com/...
```

> Note for new Teams UI: "Workflows" → "Post to a channel when a webhook request is
> received" is the equivalent path if "Connectors" is not visible.

---

### 2. Create `scripts/teams_notify.py`

Core module. No external SDK — only `requests` (already in `requirements.txt`).

```python
"""
Microsoft Teams notification utility for EAGLE CI/CD events.

Sends Adaptive Cards to Teams channels via Incoming Webhooks.
Env vars: TEAMS_WEBHOOK_JIRA, TEAMS_WEBHOOK_DEPLOY, TEAMS_WEBHOOK_EVAL

Auth: None required — webhook URL IS the credential. Keep it secret.
"""

import os, sys, json
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

CHANNELS = {
    "commits": os.getenv("TEAMS_WEBHOOK_COMMITS"),
    "jira":    os.getenv("TEAMS_WEBHOOK_JIRA"),
    "deploy":  os.getenv("TEAMS_WEBHOOK_DEPLOY"),
    "eval":    os.getenv("TEAMS_WEBHOOK_EVAL"),
}


def _adaptive_card(title: str, color: str, facts: list[dict], text: str = "", actions: list[dict] | None = None) -> dict:
    """Build a minimal Adaptive Card v1.4 payload for Teams."""
    body = [
        {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": title, "wrap": True},
    ]
    if text:
        body.append({"type": "TextBlock", "text": text, "wrap": True, "isSubtle": True})
    if facts:
        body.append({
            "type": "FactSet",
            "facts": facts,
        })

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "msBrainProperties": {"color": color},
                "body": body,
            }
        }]
    }

    if actions:
        card["attachments"][0]["content"]["actions"] = actions

    return card


def send_card(channel: str, title: str, color: str, facts: list[dict],
              text: str = "", run_url: str = "", dry_run: bool = False) -> bool:
    """Send an Adaptive Card to a Teams channel. Returns True on success.

    color: "good" (green), "warning" (yellow), "attention" (red), "accent" (blue)
    """
    webhook_url = CHANNELS.get(channel)
    if not webhook_url:
        print(f"[teams] TEAMS_WEBHOOK_{channel.upper()} not set — skipping")
        return False

    actions = []
    if run_url:
        actions = [{"type": "Action.OpenUrl", "title": "View Run", "url": run_url}]

    payload = _adaptive_card(title, color, facts, text, actions)

    if dry_run:
        print(f"[teams][dry-run] Would POST to {channel} channel:")
        print(f"  title : {title}")
        print(f"  color : {color}")
        print(f"  facts : {facts}")
        return True

    resp = requests.post(webhook_url, json=payload, timeout=10)
    if resp.status_code in (200, 202):
        print(f"[teams] Posted to {channel}: {title}")
        return True
    print(f"[teams] Failed to post to {channel}: {resp.status_code} — {resp.text[:200]}")
    return False


def send_jira_summary(commits_synced: int, issues_updated: int, run_url: str = "",
                      dry_run: bool = False) -> bool:
    """Post Jira sync summary to #jira-updates channel."""
    color = "good" if commits_synced > 0 else "accent"
    return send_card(
        channel="jira",
        title=f"Jira Sync — {commits_synced} commit(s) synced",
        color=color,
        facts=[
            {"title": "Commits synced", "value": str(commits_synced)},
            {"title": "Issues updated", "value": str(issues_updated)},
            {"title": "Triggered", "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
        ],
        run_url=run_url,
        dry_run=dry_run,
    )


def send_deploy_event(service: str, status: str, sha: str = "", run_url: str = "",
                      dry_run: bool = False) -> bool:
    """Post deploy event to #deployments channel.
    status: 'success' | 'failure' | 'started'
    """
    color_map = {"success": "good", "failure": "attention", "started": "accent"}
    icon_map  = {"success": "✅", "failure": "❌", "started": "🚀"}
    color = color_map.get(status, "accent")
    icon  = icon_map.get(status, "")
    short_sha = sha[:7] if sha else "unknown"

    return send_card(
        channel="deploy",
        title=f"{icon} Deploy {status.upper()} — {service}",
        color=color,
        facts=[
            {"title": "Service", "value": service},
            {"title": "Status",  "value": status},
            {"title": "SHA",     "value": short_sha},
            {"title": "Time",    "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
        ],
        run_url=run_url,
        dry_run=dry_run,
    )


def send_push_summary(commits: list[dict], branch: str, run_url: str = "",
                      dry_run: bool = False) -> bool:
    """Post a batched push card to #commits channel.

    commits: list of {sha, subject, author} — newest first.
    """
    if not commits:
        return False
    author = commits[0].get("author", "unknown")
    lines = "\n".join(
        f"• {c['sha'][:7]}  {c['subject'][:72]}" for c in commits
    )
    return send_card(
        channel="commits",
        title=f"Push to {branch} — {len(commits)} commit(s)",
        color="accent",
        facts=[
            {"title": "Author",  "value": author},
            {"title": "Branch",  "value": branch},
            {"title": "Commits", "value": str(len(commits))},
            {"title": "Time",    "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
        ],
        text=lines,
        run_url=run_url,
        dry_run=dry_run,
    )


def send_eval_result(passed: int, failed: int, total: int, run_url: str = "",
                     dry_run: bool = False) -> bool:
    """Post eval run result to #eval-results channel."""
    color = "good" if failed == 0 else "attention"
    return send_card(
        channel="eval",
        title=f"Eval Run — {passed}/{total} passed",
        color=color,
        facts=[
            {"title": "Passed",  "value": str(passed)},
            {"title": "Failed",  "value": str(failed)},
            {"title": "Total",   "value": str(total)},
            {"title": "Time",    "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
        ],
        run_url=run_url,
        dry_run=dry_run,
    )


def dry_run_check() -> bool:
    """Validate env vars and print channel status (no HTTP calls)."""
    errors = []
    print("=== Teams Notify Dry Run ===\n")
    for name, url in CHANNELS.items():
        var = f"TEAMS_WEBHOOK_{name.upper()}"
        if not url:
            print(f"  {var} : NOT SET")
            errors.append(f"{var} is not set")
        else:
            masked = url[:40] + "..."
            print(f"  {var} : {masked}")
    print(f"\n  Channels configured : {sum(1 for v in CHANNELS.values() if v)} / {len(CHANNELS)}")
    if errors:
        print(f"\n  WARNINGS (non-fatal — channels without webhook will be skipped):")
        for e in errors:
            print(f"    - {e}")
    print(f"\n  Result: DRY RUN OK")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Teams notification utility")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--channel", choices=["jira", "deploy", "eval"], default="deploy")
    parser.add_argument("--title", default="Test notification from EAGLE")
    args = parser.parse_args()

    if args.dry_run:
        dry_run_check()
        sys.exit(0)

    ok = send_card(args.channel, args.title, "accent", [
        {"title": "Source", "value": "teams_notify.py CLI"},
        {"title": "Time",   "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")},
    ])
    sys.exit(0 if ok else 1)
```

---

### 3. Create `scripts/teams_test.py`

Mirrors `jira_test.py` — sections: env vars, dry-run check, workflow YAML, optional live ping.

Structure:
- `[1/4] Environment Variables` — check each `TEAMS_WEBHOOK_*`
- `[2/4] teams_notify.py --dry-run` — subprocess call, validate exit 0 + "DRY RUN OK"
- `[3/4] Workflow YAML` — parse `teams-test.yml` as valid YAML with `on` + `jobs`
- `[4/4] Live Ping (optional)` — only runs if `--live` flag passed; sends test card

Exit 0 if all required checks pass. Webhook not-set is a WARNING, not a FAIL.

---

### 4. Add Teams notification to `jira-commits-sync.yml`

After the "Sync commits to Jira" step, add:

```yaml
      - name: Notify Teams — Jira sync result
        if: always()
        env:
          TEAMS_WEBHOOK_JIRA: ${{ secrets.TEAMS_WEBHOOK_JIRA }}
          GITHUB_SERVER_URL: ${{ github.server_url }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_RUN_ID: ${{ github.run_id }}
        run: |
          pip install requests python-dotenv --quiet
          python scripts/teams_notify.py \
            --channel jira \
            --title "Jira Sync — ${{ github.run_number }}"
```

For richer output (commit count), the sync script should write counts to
`$GITHUB_OUTPUT` and the notify step reads them:

```yaml
        run: |
          COMMITS=$(cat .jira-sync-counts/commits 2>/dev/null || echo 0)
          ISSUES=$(cat .jira-sync-counts/issues 2>/dev/null || echo 0)
          RUN_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
          python - <<'EOF'
          import os, sys
          sys.path.insert(0, "scripts")
          from teams_notify import send_jira_summary
          ok = send_jira_summary(
              commits_synced=int(os.getenv("COMMITS", 0)),
              issues_updated=int(os.getenv("ISSUES", 0)),
              run_url=os.getenv("RUN_URL", ""),
          )
          sys.exit(0 if ok else 1)
          EOF
        env:
          COMMITS: ${{ steps.sync.outputs.commits_synced || 0 }}
          ISSUES:  ${{ steps.sync.outputs.issues_updated || 0 }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          TEAMS_WEBHOOK_JIRA: ${{ secrets.TEAMS_WEBHOOK_JIRA }}
```

---

### 5. Add Teams notification to `deploy.yml`

Add a `notify` job at the end that runs `if: always()` after verify:

```yaml
  notify:
    needs: [deploy-infra, deploy-backend, deploy-frontend, verify]
    runs-on: ubuntu-latest
    if: always()

    steps:
    - name: Checkout
      uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11

    - name: Setup Python
      uses: actions/setup-python@v5
      with:
        python-version: "3.11"

    - name: Install dependencies
      run: pip install requests python-dotenv --quiet

    - name: Notify Teams
      env:
        TEAMS_WEBHOOK_DEPLOY: ${{ secrets.TEAMS_WEBHOOK_DEPLOY }}
        DEPLOY_STATUS: ${{ (needs.deploy-backend.result == 'success' && needs.deploy-frontend.result == 'success') && 'success' || 'failure' }}
        GIT_SHA: ${{ github.sha }}
        RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      run: |
        python - <<'EOF'
        import os, sys
        sys.path.insert(0, "scripts")
        from teams_notify import send_deploy_event
        status = os.environ["DEPLOY_STATUS"]
        send_deploy_event("eagle-platform", status,
                          sha=os.environ["GIT_SHA"],
                          run_url=os.environ["RUN_URL"])
        EOF
```

---

### 6. Create `.github/workflows/teams-test.yml`

Standalone manual workflow to send a test card without triggering a real deployment.

```yaml
name: Teams Notify — Test

on:
  workflow_dispatch:
    inputs:
      channel:
        description: 'Channel to test'
        required: true
        default: 'deploy'
        type: choice
        options: [jira, deploy, eval]
      dry_run:
        description: 'Dry run only (no actual POST)'
        required: false
        default: 'false'
        type: string

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install requests python-dotenv
      - name: Send test card
        env:
          TEAMS_WEBHOOK_JIRA:   ${{ secrets.TEAMS_WEBHOOK_JIRA }}
          TEAMS_WEBHOOK_DEPLOY: ${{ secrets.TEAMS_WEBHOOK_DEPLOY }}
          TEAMS_WEBHOOK_EVAL:   ${{ secrets.TEAMS_WEBHOOK_EVAL }}
          DRY_RUN: ${{ inputs.dry_run }}
        run: |
          ARGS="--channel ${{ inputs.channel }} --title 'Test card from EAGLE CI'"
          if [ "$DRY_RUN" == "true" ]; then ARGS="$ARGS --dry-run"; fi
          python scripts/teams_notify.py $ARGS
```

---

### 7. Update `.env.example` (if it exists) or document new env vars

Add to `.env.example`:
```
# Microsoft Teams Incoming Webhook URLs (one per channel)
TEAMS_WEBHOOK_COMMITS=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_JIRA=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_DEPLOY=https://outlook.office.com/webhook/...
TEAMS_WEBHOOK_EVAL=https://outlook.office.com/webhook/...
```

---

### 8. Create `.github/workflows/on-push-notify.yml`

Fires on every push to any branch. Two jobs run in parallel:
- `teams-notify` — posts batched commit card to `#commits`
- `jira-sync` — runs `jira_commits_sync.py --since <before_sha>` → posts to Greg dev weekly issue

```yaml
name: On Push — Teams + Jira

on:
  push:
    branches: ['**']

permissions:
  contents: read

jobs:
  # ── Post batched commit card to Teams #commits ───────────────
  teams-notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install requests python-dotenv --quiet

      - name: Post commit card to Teams
        env:
          TEAMS_WEBHOOK_COMMITS: ${{ secrets.TEAMS_WEBHOOK_COMMITS }}
          BEFORE_SHA: ${{ github.event.before }}
          AFTER_SHA:  ${{ github.sha }}
          BRANCH:     ${{ github.ref_name }}
          RUN_URL:    ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          python - <<'EOF'
          import os, subprocess, sys
          sys.path.insert(0, "scripts")
          from teams_notify import send_push_summary

          before = os.environ["BEFORE_SHA"]
          after  = os.environ["AFTER_SHA"]
          branch = os.environ["BRANCH"]
          run_url = os.environ["RUN_URL"]

          # Handle first push to a branch (before = 0000...0000)
          if before.strip("0") == "":
              before = f"{after}~10"   # fall back to last 10 commits

          result = subprocess.run(
              ["git", "log", "--format=%H%n%s%n%an", f"{before}..{after}"],
              capture_output=True, text=True
          )
          commits = []
          for block in result.stdout.strip().split("\n\n"):
              lines = block.strip().splitlines()
              if len(lines) >= 2:
                  commits.append({
                      "sha": lines[0], "subject": lines[1],
                      "author": lines[2] if len(lines) > 2 else ""
                  })

          if commits:
              send_push_summary(commits, branch, run_url=run_url)
          else:
              print("No commits to notify about")
          EOF

  # ── Post commits to Greg dev weekly Jira issue ───────────────
  jira-sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install requests python-dotenv --quiet

      - name: Sync push commits to Jira weekly issue
        env:
          JIRA_BASE_URL:    ${{ secrets.JIRA_BASE_URL }}
          JIRA_API_TOKEN:   ${{ secrets.JIRA_API_TOKEN }}
          JIRA_PROJECT:     EAGLE
          JIRA_WEEKLY_SUMMARY: ${{ secrets.JIRA_WEEKLY_SUMMARY }}
          JIRA_COMMIT_AUTHOR:  ${{ secrets.JIRA_COMMIT_AUTHOR }}
          GITHUB_SERVER_URL:   ${{ github.server_url }}
          GITHUB_REPOSITORY:   ${{ github.repository }}
        run: |
          BEFORE="${{ github.event.before }}"
          # Skip if before is all zeros (first push to branch)
          if [ "$(echo $BEFORE | tr -d '0')" = "" ]; then
            echo "First push to branch — skipping Jira sync"
            exit 0
          fi
          AUTH_ARGS=""
          if [ -n "$JIRA_COMMIT_AUTHOR" ]; then AUTH_ARGS="--author $JIRA_COMMIT_AUTHOR"; fi
          python scripts/jira_commits_sync.py \
            --since "$BEFORE" \
            --project "$JIRA_PROJECT" \
            --weekly-summary "$JIRA_WEEKLY_SUMMARY" \
            $AUTH_ARGS
```

---

### 9. Validate

Run locally (dry-run — no live webhook needed):
```bash
python scripts/teams_notify.py --dry-run
python scripts/teams_test.py
```

With a real webhook URL set in `.env`:
```bash
python scripts/teams_notify.py --channel commits --title "Manual test"
python scripts/teams_notify.py --channel deploy --title "Manual test"
```

Trigger the GitHub Actions test workflow:
```
GitHub → Actions → "Teams Notify — Test" → Run workflow → channel: commits → dry_run: false
```

---

## Testing Strategy

- **Dry-run first**: All code paths exercisable without a real webhook URL
- **Live ping**: `scripts/teams_test.py --live` sends a real card when ready
- **CI self-test**: `teams-test.yml` workflow validates end-to-end in GitHub Actions
- **Failure isolation**: Missing webhook URL is a soft warning (logged, not a CI failure)
  so the pipeline never breaks because a Teams channel isn't configured yet

---

## Acceptance Criteria

- [ ] `scripts/teams_notify.py --dry-run` exits 0 and prints all 4 channel statuses
- [ ] `scripts/teams_test.py` exits 0 (all checks pass)
- [ ] With `TEAMS_WEBHOOK_COMMITS` set, a push to any branch posts a batched card to Teams
- [ ] With `JIRA_WEEKLY_SUMMARY` set, a push posts commits to the Greg dev weekly Jira issue
- [ ] `deploy.yml` has a `notify` job that runs `if: always()`
- [ ] `jira-commits-sync.yml` has a notify step after the sync step
- [ ] `.github/workflows/on-push-notify.yml` exists with `teams-notify` and `jira-sync` jobs
- [ ] `.github/workflows/teams-test.yml` exists and parses as valid YAML
- [ ] Missing webhook URL logs a warning and returns `False` (does not raise an exception)
- [ ] First push to a new branch (before SHA = 0000...) is handled gracefully (no crash)

## Validation Commands

```bash
# Syntax check the new scripts
python -c "import py_compile; py_compile.compile('scripts/teams_notify.py', doraise=True)"
python -c "import py_compile; py_compile.compile('scripts/teams_test.py', doraise=True)"

# Dry-run validation (no webhook URL needed)
python scripts/teams_notify.py --dry-run

# Full test harness (no webhook URL needed for required checks)
python scripts/teams_test.py

# Live test (requires TEAMS_WEBHOOK_DEPLOY in .env)
python scripts/teams_notify.py --channel deploy --title "EAGLE Teams integration test"

# Validate workflow YAML syntax
python -c "import yaml; yaml.safe_load(open('.github/workflows/teams-test.yml'))"
python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"
python -c "import yaml; yaml.safe_load(open('.github/workflows/jira-commits-sync.yml'))"
```

## Notes

- **No SDK needed**: Teams Incoming Webhooks accept plain `requests.post()` with JSON.
  `pymsteams` (third-party) is optional — not used here to keep the dep footprint small.
- **Adaptive Cards vs MessageCard**: Adaptive Cards are the current standard. Legacy
  `@type: MessageCard` still works but is deprecated by Microsoft.
- **Webhook URL = secret**: The URL itself is the auth credential — store only in GitHub
  Secrets and `.env` (gitignored). Never commit it.
- **New Teams ("Teams 2.0")**: In the new Teams client, "Connectors" was replaced by
  "Workflows" (Power Automate). The Incoming Webhook connector still works in the classic
  Teams flow; the equivalent in new Teams is the "Post to a channel when a webhook request
  is received" workflow template. Both produce identical webhook URLs and behavior.
- **Rate limits**: Teams webhooks are rate-limited to ~4 req/sec per webhook. CI/CD
  notifications are well within limits.
- **`if: always()`**: Use on the notify job so deploy failures still trigger a Teams
  notification — the most important case.
