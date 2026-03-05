---
description: Sync recent commits to Jira and semantically match unkeyed commits to open issues
argument-hint: [--since <24h|SHA|"N days ago">] [--dry-run]
---

# /jira

Sync git commits to Jira. Runs in two phases:
1. **Direct key match** — commits with `EAGLE-XXX` in the message get posted to those issues
2. **Semantic match** — commits without a key are matched to open issues by meaning

## Variables
- `SINCE`: How far back to look (default: `24h`). Can be a SHA, `"7 days ago"`, etc.
- `DRY_RUN`: If `--dry-run` passed, print what would be posted without writing to Jira

## Workflow

1. **Resolve author from git config**:
   ```bash
   git config user.name
   ```

2. **Phase 1 — direct key sync**:
   ```bash
   python scripts/jira_commits_sync.py \
     --since "${SINCE:-24h}" \
     --project EAGLE \
     --author "$(git config user.name)" \
     ${DRY_RUN:+--dry-run}
   ```

3. **Phase 2 — semantic match** (read the skill, then execute it):
   - Read `.claude/skills/jira-commit-matcher/SKILL.md` for full matching rules
   - Run `python scripts/jira_scan_issues.py --project EAGLE --since "${SINCE:-24h}"`
   - Follow the skill instructions to match unkeyed commits and post comments

4. **Report summary** — print counts: commits synced, matched, unmatched
