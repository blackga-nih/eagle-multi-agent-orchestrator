---
description: "Update SDK expertise with learnings from SDK usage sessions, test runs, or integration work"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# Claude SDK Expert - Self-Improve Mode

> Update expertise.md with learnings from SDK development and debugging.

## Purpose

After implementing SDK integrations or debugging SDK issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future SDK development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:claude-sdk:self-improve sessions success
/experts:claude-sdk:self-improve subagents failed
/experts:claude-sdk:self-improve hooks partial
```

## Variables

- `COMPONENT`: $1 (component or area changed)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/claude-sdk/expertise.md`
2. Read recent changes:
   - `server/tests/test_eagle_sdk_eval.py` — check SDK test patterns
   - `server/tests/test_agent_sdk.py` — check advanced SDK features
   - Git log for recent commits:
     ```bash
     git log --oneline -10
     git diff HEAD~3 --stat
     ```
3. Check for any test results or trace logs

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What SDK pattern made the implementation successful?
- Any new API behaviors discovered?
- Were there session/cost surprises?
- Did message types behave as expected?

**failed**:
- What caused the failure?
- SDK version issue? API change? Bedrock-specific behavior?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- What worked vs. what didn't?
- What remains to be done?
- What SDK limitations were encountered?

### Phase 3: Update expertise.md

#### Update `Learnings` section:

Add entries to the appropriate subsection:

```markdown
### patterns_that_work
- {what worked} (discovered: {date}, component: {COMPONENT})

### patterns_to_avoid
- {what to avoid} (reason: {why})

### common_issues
- {issue}: {solution} (component: {COMPONENT})

### tips
- {useful tip learned}
```

#### Update other sections if needed:

- **Part 2** (query() API): If new API patterns were discovered
- **Part 4** (Sessions): If session behavior was clarified
- **Part 5** (Subagents): If subagent patterns were learned
- **Part 7** (Hooks): If hook behaviors were discovered
- **Part 9** (Cost): If cost patterns changed

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter.

---

## Report Format

```markdown
## Self-Improve Report: {COMPONENT}

### Outcome: {OUTCOME}

### Learnings Recorded

**Patterns that work:**
- {pattern 1}

**Patterns to avoid:**
- {pattern 1}

**Issues documented:**
- {issue 1}

**Tips added:**
- {tip 1}

### Expertise Updated

- expertise.md -> Learnings section
- expertise.md -> last_updated timestamp
- expertise.md -> {other sections if changed}
```

---

## Instructions

1. **Run after every significant SDK usage** - Even failed attempts have learnings
2. **Be specific** - Record concrete SDK behaviors, not vague observations
3. **Include context** - Date, component, SDK version, and circumstances
4. **Keep it actionable** - Learnings should help future SDK development
5. **Don't overwrite** - Append to existing learnings, don't replace
6. **Update cheat-sheet.md** - If a new important pattern was discovered

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| SDK test suite | `server/tests/test_eagle_sdk_eval.py` | query() patterns, sessions, cost |
| SDK advanced tests | `server/tests/test_agent_sdk.py` | Tools, hooks, client, subagents |
| Expertise | `.claude/commands/experts/claude-sdk/expertise.md` | Current mental model |
| Cheat sheet | `.claude/commands/experts/claude-sdk/cheat-sheet.md` | Quick reference |
| Git history | `git log` | Recent changes and context |
