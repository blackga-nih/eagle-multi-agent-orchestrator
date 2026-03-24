# Plan: Agent Skills Optimization

> **Date**: 2026-03-10
> **Branch target**: main (via PR)
> **Source report**: `docs/development/20260310-150000-report-agent-skills-self-improve-v1.md`
> **Validation**: L1 (lint) only — no code changes, all `.md` edits

---

## Problem Statement

Three issues identified from the Agent Skills spec audit:

1. **Context budget overspend** — 150+ skills in `.claude/commands/` + `.claude/skills/` compete for a ~4,000 token description budget (2% of context window). The 26 internal reference files (`_index.md` + `expertise.md` × 13 domains) we just added descriptions to are now consuming budget for files users never invoke directly. This likely causes some actionable skills to be silently excluded from context.

2. **No session-end self-improve trigger** — The `/experts:{domain}:self-improve` loop only fires when explicitly invoked. Learnings from sessions don't get written back to `expertise.md` automatically, so knowledge degrades between long gaps.

3. **`context: fork` not used** — Heavy skills (code-review, plan, build, eval runs) run inline, competing with the main conversation context. The `context: fork` + `agent` front matter keys would isolate these into subagents automatically.

---

## Phase 1 — Context Budget Fix (immediate, low risk)

**Goal**: Reclaim ~26 skill description slots for actionable skills.

### 1A. Flip internal reference files to `user-invocable: false`

`user-invocable: false` removes the file from the skills list entirely — description not loaded, not shown in `/` menu. These files are consumed by domain commands (e.g., `question.md` reads `expertise.md`), never invoked standalone.

**Files to update** — all 13 × 2 = 26 files:

```
.claude/commands/experts/{domain}/_index.md     → add user-invocable: false
.claude/commands/experts/{domain}/expertise.md  → add user-invocable: false
```

Domains: `aws`, `backend`, `claude-sdk`, `cloudwatch`, `deployment`, `eval`, `frontend`, `git`, `hooks`, `sse`, `strands`, `tac`, `test`

**Front matter change** (same for all 26):
```yaml
---
user-invocable: false        # ← add this line
type: expert-file
...
---
```

**Validation**:
```bash
# Confirm no description in skills list after restart
# Check with /context command to see budget usage
```

### 1B. Audit remaining skills for description length

Target: all descriptions ≤ 160 characters. Over-length descriptions waste budget on the least useful words.

```bash
# Find descriptions over 160 chars
grep -r "^description:" .claude/commands/ .claude/skills/ | awk 'length($0) > 175'
```

Trim any that exceed this. The "Use when... Trigger keywords:" pattern should fit in 160 chars.

---

## Phase 2 — Session-End Auto Self-Improve Hook (medium effort)

**Goal**: Automatically queue `self-improve` for expert domains touched in a session, so `expertise.md` files stay current without manual invocation.

### 2A. Create `post_session_self_improve.py` hook

New file: `.claude/hooks/post_session_self_improve.py`

**Logic**:
1. Read `git diff HEAD --name-only` to find files changed in the session
2. Map changed files to expert domains:
   - `server/app/**` → `backend`, `strands`, `sse`
   - `client/**` → `frontend`
   - `infrastructure/cdk-eagle/**` → `aws`, `deployment`
   - `.github/workflows/**` → `git`
   - `server/tests/**` → `eval`, `test`
3. Write a queue file: `.claude/context/self-improve-queue.json`
   ```json
   { "domains": ["backend", "sse"], "session_date": "2026-03-10", "triggered_by": "Stop hook" }
   ```
4. Exit 0 — non-blocking, does not stop the session

**Wire into settings.json**:
```json
{
  "hooks": {
    "Stop": [{
      "command": "python C:/Users/blackga/Desktop/eagle/sm_eagle/.claude/hooks/post_session_self_improve.py"
    }]
  }
}
```

### 2B. Update `self-improve` commands to consume the queue

Each `/experts:{domain}:self-improve` command checks for its domain in `.claude/context/self-improve-queue.json` at startup and notes the queued context. After running, it removes its domain from the queue.

### 2C. Add a queue-reader to session start (optional)

At session start, if the queue is non-empty, surface a prompt:
> "Self-improve queue has entries for: `backend`, `sse`. Run `/parallel_expert_self_improve backend sse`?"

This keeps the human in the loop while making the trigger automatic.

**New files**:
```
.claude/hooks/post_session_self_improve.py
.claude/context/self-improve-queue.json        (gitignored, runtime state)
```

---

## Phase 3 — Cross-Domain Learning Log (low effort)

**Goal**: When one domain's `self-improve` discovers something cross-cutting, it propagates to other domains.

### 3A. Create `.claude/context/cross-domain-learnings.md`

Structure:
```markdown
# Cross-Domain Learnings

## 2026-03-10 — Strands SDK 0.x breaking change
- **Discovered by**: `sse` expert during session abc123
- **Affects**: `strands`, `backend`, `eval`
- **Learning**: `stream_async()` signature changed — `timeout` param removed in 0.2.x
- **Action**: Updated `sse/expertise.md`. Domains `strands`, `backend` need review.
```

### 3B. Update `self-improve.md` in each domain to append here

Add a step to each domain's `self-improve` command:
> "If any learning applies to multiple domains, append it to `.claude/context/cross-domain-learnings.md` with affected domains noted."

### 3C. Update `parallel_expert_self_improve.md` to read it first

The parallel self-improve skill reads this file before launching domain agents, so each agent gets cross-domain context.

**New file**:
```
.claude/context/cross-domain-learnings.md
```

---

## Phase 4 — `context: fork` for Heavy Skills (medium effort)

**Goal**: Run heavy skills as isolated subagents so they don't pollute the main conversation context.

### Skills to migrate

| Skill | Reason |
|-------|--------|
| `code-review` | Reads full codebase, large output |
| `plan` / `quick-plan` | Reads multiple files, medium output |
| `build` | Executes multi-step implementation |
| `fix` | Multi-file edits |
| `scribe` | Document generation, large output |
| `review` | Full git diff analysis |
| `parallel_subagents` | Already parallel — should be forked |

**Front matter change**:
```yaml
---
description: "..."
context: fork
agent: general-purpose     # or a more specific subagent type
---
```

**Validation**: Test each migrated skill to confirm output is returned correctly to the main session.

---

## Phase 5 — Pattern-to-Skill Promotion (future, post-P1–P4)

**Goal**: When a fix/pattern appears 3+ times in session history, `self-improve` proposes a new skill file.

This is what Anthropic described as future work. Build it once P1–P3 are stable.

**Trigger**: `self-improve` scans `.claude/context/cross-domain-learnings.md` for entries that have appeared ≥ 3 times. Proposes a new SKILL.md file for human approval.

---

## Execution Order

| Phase | Effort | Risk | Value | Do first? |
|-------|--------|------|-------|-----------|
| 1A — `user-invocable: false` on 26 files | S | Low | High (immediate budget relief) | ✅ Yes |
| 1B — description length audit | S | Low | Medium | ✅ Yes |
| 2A-C — Stop hook + queue | M | Low | High | After 1A |
| 3A-C — Cross-domain log | S | Low | Medium | After 2A |
| 4 — `context: fork` | M | Medium (test each) | Medium | After 3 |
| 5 — Pattern promotion | L | Low | High (future) | Last |

---

## Validation Commands

```bash
# After Phase 1
# Restart Claude Code, then:
/context                    # Check skill budget — should show ~26 fewer entries

# After Phase 2
# End a session, check queue file was written:
cat .claude/context/self-improve-queue.json

# After Phase 4
# Test a forked skill returns output:
/code-review               # Should spawn subagent, return report to main session
```

---

## Files Changed Summary

```
Modified (Phase 1A):
  .claude/commands/experts/*/  _index.md      ×13  → add user-invocable: false
  .claude/commands/experts/*/  expertise.md   ×13  → add user-invocable: false

New (Phase 2):
  .claude/hooks/post_session_self_improve.py
  .claude/context/self-improve-queue.json

New (Phase 3):
  .claude/context/cross-domain-learnings.md

Modified (Phase 3B-C):
  .claude/commands/experts/*/self-improve.md  ×13  → append cross-domain step
  .claude/commands/parallel_expert_self_improve.md  → read cross-domain log

Modified (Phase 4):
  .claude/commands/code-review.md     → add context: fork
  .claude/commands/plan.md            → add context: fork
  .claude/commands/quick-plan.md      → add context: fork
  .claude/commands/build.md           → add context: fork
  .claude/commands/fix.md             → add context: fork
  .claude/commands/scribe.md          → add context: fork
  .claude/commands/review.md          → add context: fork
  .claude/commands/parallel_subagents.md → add context: fork
```
