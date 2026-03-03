---
description: "Update Strands SDK expertise with learnings from usage sessions, migration work, or integration tests"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# Strands SDK Expert - Self-Improve Mode

> Update expertise.md with learnings from Strands development and debugging.

## Purpose

After implementing Strands integrations, migrating from Claude SDK, or debugging Strands issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future Strands development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:strands:self-improve agent-construction success
/experts:strands:self-improve multi-agent failed
/experts:strands:self-improve migration partial
```

## Variables

- `COMPONENT`: $1 (component or area changed)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/strands/expertise.md`
2. Read recent changes:
   - Search for Strands-related files:
     ```bash
     grep -r "from strands" server/ --include="*.py"
     grep -r "BedrockModel\|Agent(" server/ --include="*.py"
     ```
   - Git log for recent commits:
     ```bash
     git log --oneline -10
     git diff HEAD~3 --stat
     ```
3. Check for any test results or migration logs

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- What Strands pattern made the implementation successful?
- Any new API behaviors discovered?
- Were there latency/cost improvements vs Claude SDK?
- Did multi-agent patterns work as expected?

**failed**:
- What caused the failure?
- SDK version issue? Bedrock-specific behavior? Concurrency problem?
- What should be avoided next time?
- What needs to happen before retry?

**partial**:
- What worked vs. what didn't?
- What remains to be done?
- What Strands limitations were encountered?
- Are there upstream issues to track?

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

- **Part 2** (Agent API): If new construction patterns were discovered
- **Part 3** (BedrockModel): If model provider behaviors were clarified
- **Part 4** (Tools): If tool patterns were learned
- **Part 5** (Multi-Agent): If swarm/graph behaviors were discovered
- **Part 6** (Sessions): If session management patterns were learned
- **Part 11** (Migration): If migration mapping was refined

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

- expertise.md → Learnings section
- expertise.md → last_updated timestamp
- expertise.md → {other sections if changed}
```

---

## Instructions

1. **Run after every significant Strands usage** — Even failed attempts have learnings
2. **Be specific** — Record concrete SDK behaviors, not vague observations
3. **Include context** — Date, component, SDK version, and circumstances
4. **Keep it actionable** — Learnings should help future Strands development
5. **Don't overwrite** — Append to existing learnings, don't replace
6. **Compare to Claude SDK** — Note behavioral differences when relevant
7. **Track upstream issues** — Link to GitHub issues for Strands SDK bugs

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| Expertise | `.claude/commands/experts/strands/expertise.md` | Current mental model |
| Comparison report | `docs/development/20260302-*-report-*.md` | Architecture comparison |
| Claude SDK expertise | `.claude/commands/experts/claude-sdk/expertise.md` | Migration reference |
| Cheat sheet | `.claude/commands/experts/strands/cheat-sheet.md` | Quick reference |
| Git history | `git log` | Recent changes and context |
