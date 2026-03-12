---
allowed-tools: Bash, Read
description: Sync recent commits to EAGLE Jira issues using Claude semantic matching. Dry-run by default.
argument-hint: [dry-run|live|prepare-stories] [since: e.g. "24h", "7 days ago", SHA]
model: haiku
---

# Jira Sync — Agentic Commit Matcher

## Variables

MODE: $1   (dry-run | live | prepare-stories — default: dry-run)
SINCE: $2  (how far back to look — default: 24h)

## Purpose

Sync commits by the current git user to EAGLE Jira issues using two-phase matching, or prepare story entries from commits:

- **Phase 1 — Direct**: commits referencing `EAGLE-XXX` go straight to that issue
- **Phase 2 — Semantic**: remaining commits are matched to open issues by meaning (you do this)
- **Phase 3 — Catch-all**: anything still unmatched goes to `JIRA_WEEKLY_SUMMARY` if set; otherwise skipped

Only commits by the current git author email are synced. Resolve it once at the start and reuse throughout.

When MODE is `prepare-stories`, skip Phases 1-3 and instead generate formatted story entries from commits.

## Instructions

- If MODE is empty or "dry-run", run in dry-run mode — print the match plan, post nothing.
- If MODE is "live", execute for real and post comments to Jira.
- If MODE is "prepare-stories", skip sync phases and generate story markdown instead (see Step 8).
- If SINCE is empty, default to "24h".
- Read `.env` for `JIRA_BASE_URL`, `JIRA_API_TOKEN`, `JIRA_WEEKLY_SUMMARY` if needed.
- Never create Jira issues — only comment on existing ones.
- Never touch issues not assigned to the target user.
- Strip `Co-Authored-By:` lines from all commit bodies before posting.
- Use short SHA (first 10 chars) only — no full commit URLs.

## Workflow

### Step 1 — Resolve author

```bash
GIT_AUTHOR=$(git config user.email)
echo "Syncing commits by: $GIT_AUTHOR"
```

### Step 2 — Phase 1: Direct key matching

Run the deterministic sync scoped to the current git user:

```bash
SINCE="${SINCE:-24h}"
DRY_FLAG=$([ "${MODE:-dry-run}" != "live" ] && echo "--dry-run" || echo "")
WEEKLY_FLAG=$([ -n "$JIRA_WEEKLY_SUMMARY" ] && echo "--weekly-summary $JIRA_WEEKLY_SUMMARY" || echo "")

python scripts/jira_commits_sync.py \
  --since "$SINCE" \
  --project EAGLE \
  --author "$GIT_AUTHOR" \
  $DRY_FLAG \
  $WEEKLY_FLAG
```

Build the command dynamically:
- Always add `--author "$GIT_AUTHOR"`
- Add `--dry-run` if MODE is anything other than "live" (default is dry-run)
- Add `--weekly-summary "$JIRA_WEEKLY_SUMMARY"` only if the env var is set

### Step 3 — Collect data for semantic matching

Run the scanner to get open issues and unmatched commits:

```bash
python scripts/jira_scan_issues.py \
  --project EAGLE \
  --board-id 1767 \
  --since "${SINCE:-24h}" \
  --author "$GIT_AUTHOR"
```

Parse the JSON output. Extract:
- `issues` — open Jira issues (candidates for matching)
- `unmatched_commits` — commits without an EAGLE-XXX key, filtered to the current git author

If `unmatched_commits` is empty, print "Nothing to semantically match — done." and stop.

### Step 4 — Semantic matching (you do this)

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

### Step 5 — Output match plan

Always print the match table regardless of MODE:

```
=== Jira Sync — {GIT_AUTHOR} | since: {SINCE} | mode: {MODE} ===

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

### Step 6 — Post comments (live mode only)

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

### Step 7 — Summary

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

---

### Step 8 — Prepare Stories (prepare-stories mode only)

If MODE is `prepare-stories`, skip Steps 2-7 entirely and run this instead:

#### 8a — Collect commits

```bash
SINCE="${SINCE:-7 days ago}"
GIT_AUTHOR=$(git config user.email)
git log --format="%H|%s|%b" --since="$SINCE" --author="$GIT_AUTHOR"
```

#### 8b — Group by feature/PR branch

Group related commits into cohesive stories:
- Commits on the same feature branch → 1 story
- Commits referencing the same `EAGLE-XXX` key → 1 story
- Related by subject prefix (e.g., all `feat(strands):` commits) → 1 story

#### 8c — Generate story entries

Read the story-writer skill for full format rules:

```bash
cat .claude/skills/jira-story-writer/SKILL.md
```

For each story group, produce a formatted story entry with:
- Type, Epic, Summary, Status, Assignee, Expert Domain
- PR links and commit SHAs
- Plan/spec paths (verify they exist)
- Description narrative
- Acceptance Criteria (checked for Done, unchecked for To Do)
- Priority (P1-P3) and Effort (S/M/L)

#### 8d — Collect open issues for context

```bash
python scripts/jira_scan_issues.py \
  --project EAGLE \
  --board-id 1767 \
  --since "${SINCE}" \
  --author "$GIT_AUTHOR"
```

Use open issues to:
- Update existing issues instead of creating duplicates
- Add "Updates to Existing Issues" section when labels or status changed
- Identify new epic needs

#### 8e — Write output

Write the full story document to:
```
docs/jira-new-items-{YYYYMMDD}.md
```

Include:
1. Header with date and summary
2. Completed Stories section (Done entries)
3. Updates to Existing Issues section (if any)
4. New Epic section (if needed)
5. New Stories section (To Do entries)
6. Summary tables (completed + open priority)

#### 8f — Report

```
=== Prepare Stories — {GIT_AUTHOR} | since: {SINCE} ===

Output: docs/jira-new-items-{YYYYMMDD}.md

Completed stories: {N}
New stories:       {N}
Commits covered:   {N}
Existing updates:  {N}
```
