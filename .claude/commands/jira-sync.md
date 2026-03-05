---
allowed-tools: Bash, Read
description: Sync recent commits by blackga-nih to EAGLE Jira issues using Claude semantic matching. Dry-run by default.
argument-hint: [dry-run|live] [since: e.g. "24h", "7 days ago", SHA]
model: haiku
---

# Jira Sync — Agentic Commit Matcher

## Variables

MODE: $1   (dry-run | live — default: dry-run)
SINCE: $2  (how far back to look — default: 24h)

## Purpose

Sync commits by `blackga-nih` to EAGLE Jira issues using two-phase matching:

- **Phase 1 — Direct**: commits referencing `EAGLE-XXX` go straight to that issue
- **Phase 2 — Semantic**: remaining commits are matched to open issues by meaning (you do this)
- **Phase 3 — Catch-all**: anything still unmatched goes to `JIRA_WEEKLY_SUMMARY` if set; otherwise skipped

Only commits by `blackga@nih.gov` (git author email) are synced. Never touch commits by other authors.

## Instructions

- If MODE is empty or "dry-run", run in dry-run mode — print the match plan, post nothing.
- If MODE is "live", execute for real and post comments to Jira.
- If SINCE is empty, default to "24h".
- Read `.env` for `JIRA_BASE_URL`, `JIRA_API_TOKEN`, `JIRA_WEEKLY_SUMMARY` if needed.
- Never create Jira issues — only comment on existing ones.
- Never touch issues not assigned to the target user.
- Strip `Co-Authored-By:` lines from all commit bodies before posting.
- Use short SHA (first 10 chars) only — no full commit URLs.

## Workflow

### Step 1 — Phase 1: Direct key matching

Run the deterministic sync for `blackga-nih` commits only:

```bash
SINCE="${SINCE:-24h}"
DRY_FLAG=$([ "${MODE:-dry-run}" != "live" ] && echo "--dry-run" || echo "")
WEEKLY_FLAG=$([ -n "$JIRA_WEEKLY_SUMMARY" ] && echo "--weekly-summary $JIRA_WEEKLY_SUMMARY" || echo "")

python scripts/jira_commits_sync.py \
  --since "$SINCE" \
  --project EAGLE \
  --author "blackga@nih.gov" \
  $DRY_FLAG \
  $WEEKLY_FLAG
```

Build the command dynamically:
- Always add `--author blackga@nih.gov`
- Add `--dry-run` if MODE is anything other than "live" (default is dry-run)
- Add `--weekly-summary "$JIRA_WEEKLY_SUMMARY"` only if the env var is set

### Step 2 — Collect data for semantic matching

Run the scanner to get open issues and unmatched commits:

```bash
python scripts/jira_scan_issues.py \
  --project EAGLE \
  --board-id 1767 \
  --since "${SINCE:-24h}" \
  --author "blackga@nih.gov"
```

Parse the JSON output. Extract:
- `issues` — open Jira issues (candidates for matching)
- `unmatched_commits` — commits without an EAGLE-XXX key, filtered to blackga-nih

If `unmatched_commits` is empty, print "Nothing to semantically match — done." and stop.

### Step 3 — Semantic matching (you do this)

Read the matching skill for full rules:

```bash
cat .claude/skills/jira-commit-matcher/SKILL.md
```

Apply the skill logic:

For each unmatched commit:
1. Score the commit scope (1-4)
2. Compare against every open issue — score each issue's complexity (1-4)
3. Match only when genuinely confident the commit contributes to that issue
4. One commit → at most one issue
5. If no confident match: leave unmatched (catch-all handles it in Phase 1, or skip)

### Step 4 — Output match plan

Always print the match table regardless of MODE:

```
=== Jira Sync — blackga-nih | since: {SINCE} | mode: {MODE} ===

Phase 1 (direct key matches): {N} commits
Phase 2 (semantic matches):
  Commit (score) | Issue          | Confidence reason
  -------------- | -------------- | -----------------
  abc1234567 feat: add X (3/4)  | EAGLE-42 Title (2/4) | Reason
  ...

Unmatched (no confident issue found):
  def4567890 chore: bump deps (1/4) — trivial, no scope match
  ...

Catch-all ({JIRA_WEEKLY_SUMMARY or "not configured"}): {N} commits
```

### Step 5 — Post comments (live mode only)

If MODE is "live":

For each semantic match, post using this exact format:

```
**Commit Linked** (Scope: {score}/4 — {level})
Commit: {short_sha}

{commit_subject}

{commit_body — stripped of Co-Authored-By lines}

*Issue Complexity: {issue_score}/4 — {level}*
*Matched by: Claude semantic analysis — {one-sentence reason}*
```

Post via:
```python
from scripts.jira_connect import add_comment
add_comment("EAGLE-XX", comment_body)
```

Print confirmation for each posted comment.

### Step 6 — Summary

Print final summary:
```
=== Done ===
Phase 1 direct matches : {N}
Phase 2 semantic matches: {N}
Unmatched (skipped)    : {N}
Catch-all posted       : {N}
Total commits processed: {N}
Mode: {dry-run / live}
```
