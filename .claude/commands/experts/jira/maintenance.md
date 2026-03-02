---
allowed-tools: Bash, Read, Grep, Glob
description: "Check Jira connectivity, validate PAT, list open issues, and report board health"
argument-hint: [--connect | --issues | --board | --full]
---

# Jira Expert - Maintenance Command

Execute Jira health checks and report status.

## Purpose

Validate the NCI Jira connection, PAT token, issue state, and board health. Run after PAT renewal, before sync runs, or to diagnose connectivity issues.

## Usage

```
/experts:jira:maintenance --connect
/experts:jira:maintenance --issues
/experts:jira:maintenance --board
/experts:jira:maintenance --full
```

## Presets

| Flag | Checks | Description | API Calls |
|------|--------|-------------|-----------|
| `--connect` | Dry-run only | Validate env vars, no HTTP | None |
| `--issues` | Connection + open issues | List open EAGLE issues | 2 |
| `--board` | Connection + board issues | List board 1767 issues | 2 |
| `--full` | Everything | Connection, issues, board, scripts | 3+ |

## Workflow

### Phase 1: Environment Check

Always run first, regardless of preset:

```bash
# Validate env vars without making API calls
python scripts/jira_connect.py --dry-run
```

If this fails (missing JIRA_BASE_URL or JIRA_API_TOKEN), report the error and stop.

### Phase 2: Connection Test (--issues, --board, --full)

```bash
# Test actual Jira connectivity
python -c "
from scripts.jira_connect import test_connection
user = test_connection()
if user:
    print(f'Connection: PASS')
    print(f'User: {user.get(\"displayName\")} ({user.get(\"emailAddress\")})')
else:
    print('Connection: FAIL')
"
```

### Phase 3: Open Issues (--issues, --full)

```bash
# List open EAGLE issues
python -c "
from scripts.jira_connect import fetch_open_issues
issues = fetch_open_issues('EAGLE')
print(f'Open issues: {len(issues)}')
for i in issues:
    labels = ', '.join(i.get('labels', [])) or 'none'
    print(f'  [{i[\"key\"]}] {i[\"summary\"]} ({i[\"status\"]}) — labels: {labels}')
"
```

### Phase 4: Board Issues (--board, --full)

```bash
# List board 1767 issues
python -c "
from scripts.jira_connect import fetch_board_issues
issues = fetch_board_issues(1767)
print(f'Board 1767 issues: {len(issues)}')
for i in issues:
    print(f'  [{i[\"key\"]}] {i[\"summary\"]} ({i[\"status\"]}) — {i[\"assignee\"]}')
"
```

### Phase 5: Scripts Check (--full only)

```bash
# Verify all Jira scripts exist and are importable
python -c "
import importlib.util
scripts = [
    'scripts/jira_connect.py',
    'scripts/jira_commits_sync.py',
    'scripts/jira_scan_issues.py',
    'scripts/create_git_stories.py',
]
for s in scripts:
    spec = importlib.util.spec_from_file_location('mod', s)
    status = 'OK' if spec else 'MISSING'
    print(f'  {s}: {status}')
"

# Check for story docs
ls -la docs/jira-new-items-*.md 2>/dev/null || echo "No story docs found"

# Check skills
ls -la .claude/skills/jira-commit-matcher/SKILL.md 2>/dev/null || echo "jira-commit-matcher skill MISSING"
ls -la .claude/skills/jira-story-writer/SKILL.md 2>/dev/null || echo "jira-story-writer skill MISSING"
```

### Phase 6: Analyze and Report

Compile all check results and report.

## Report Format

```markdown
## Jira Maintenance Report

**Date**: {timestamp}
**Preset**: {--connect | --issues | --board | --full}
**Status**: HEALTHY | DEGRADED | FAILED

### Environment Check

- JIRA_BASE_URL: SET | MISSING
- JIRA_API_TOKEN: SET | MISSING ({N} chars)
- Auth method: Bearer PAT
- API version: REST v2

### Connection Test (if checked)

| Check | Status |
|-------|--------|
| PAT auth | PASS | FAIL |
| User | {displayName} |

### Open Issues (if checked)

| Key | Summary | Status | Labels |
|-----|---------|--------|--------|
| EAGLE-{N} | {summary} | {status} | {labels} |

Total: {N} open issues

### Board 1767 (if checked)

| Key | Summary | Status | Assignee |
|-----|---------|--------|----------|
| EAGLE-{N} | {summary} | {status} | {assignee} |

Total: {N} board issues

### Scripts (if checked)

| Script | Status |
|--------|--------|
| jira_connect.py | OK | MISSING |
| jira_commits_sync.py | OK | MISSING |
| jira_scan_issues.py | OK | MISSING |
| create_git_stories.py | OK | MISSING |

### Issues Found

- {issue description and recommended fix}

### Next Steps

- {recommended actions}
```

## Troubleshooting

### PAT Expired
1. Generate new PAT at tracker.nci.nih.gov → Profile → Personal Access Tokens
2. Update `JIRA_API_TOKEN` in `.env`
3. Re-run `/experts:jira:maintenance --connect`

### Connection Timeout
- Check VPN connection (NCI tracker requires NCI network)
- Verify `JIRA_BASE_URL` is correct (no trailing slash)

### No Issues Found
- Verify project key is `EAGLE`
- Check board ID is `1767`
- Try fetching without assignee filter
