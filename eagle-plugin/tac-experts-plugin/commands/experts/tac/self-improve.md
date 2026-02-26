---
description: "Update TAC expertise with new learnings, patterns discovered, or methodology refinements"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# TAC Expert - Self-Improve Mode

> Update expertise.md with learnings from TAC-guided development work.

## Purpose

After applying TAC principles to build features, create experts, or design hooks, run self-improve to:
- Record patterns that work (patterns_that_work)
- Record anti-patterns discovered (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add practical tips for future TAC application

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:tac:self-improve expert-bootstrap success
/experts:tac:self-improve hook-architecture failed
/experts:tac:self-improve context-engineering partial
```

## Variables

- `COMPONENT`: $1 (component or area of TAC methodology applied)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/tac/expertise.md` (practical patterns file)
   - Note: `tac-learning-expertise.md` (theory) is a stable reference and is NOT updated by self-improve. Only `expertise.md` accumulates learnings.
2. Scan for recent changes:
   ```
   Glob: .claude/commands/experts/**/*.md
   Glob: .claude/hooks/*
   Glob: .claude/commands/*.md
   ```
3. Read git log for recent changes (if available via Bash):
   - What was built?
   - Which TAC tactics were applied?
   - What worked and what didn't?
4. Check the COMPONENT context

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**:
- Which TAC tactics were most effective?
- Which framework guided the work? (PITER, R&D, ACT-LEARN-REUSE)
- Any new patterns worth recording?
- Did the agentic layer classification help?

**failed**:
- Which TAC principles were violated?
- What anti-patterns were encountered?
- Was the wrong framework chosen?
- What context was missing?

**partial**:
- What succeeded and what didn't?
- Which tactics helped and which didn't apply?
- What blockers were encountered?
- What remains to be done?

### Phase 3: Update expertise.md

#### Update `Learnings` section:

Add entries to the appropriate subsection:

```markdown
### patterns_that_work
- {what worked} (discovered: {date}, component: {COMPONENT}, tactics: {N,N})

### patterns_to_avoid
- {what to avoid} (reason: {why}, violates tactic: {N})

### common_issues
- {issue}: {solution} (component: {COMPONENT})

### tips
- {useful tip learned from applying TAC}
```

#### Optionally update other sections:

- **Part 1 (Hook Architecture)**: Document new hook patterns or filtering strategies
- **Part 2 (SSVA)**: Add new self-validation or block/retry patterns
- **Part 4 (Ecosystem Graph)**: Update pattern index with new patterns
- **Part 5 (Agent Team Patterns)**: Add new workflow patterns, agent types, or catalogs

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter of expertise.md.

---

## Report Format

```markdown
## Self-Improve Report: {COMPONENT}

### Outcome: {OUTCOME}

### TAC Tactics Applied
- Tactic {N}: {name} — {how it was applied}

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
- {other sections updated, if any}
```

---

## Instructions

1. **Run after every significant TAC-guided session** - Even failed attempts have learnings
2. **Be specific** - Record concrete patterns with tactic numbers, not vague observations
3. **Include context** - Date, component, applicable tactics, and circumstances
4. **Keep it actionable** - Learnings should help future TAC application
5. **Don't overwrite** - Append to existing learnings, don't replace them
6. **Cross-reference tactics** - Always note which tactic number relates to the learning

---

## Data Sources

| Source | Location | Content |
|--------|----------|---------|
| TAC Theory | `.claude/commands/experts/tac/tac-learning-expertise.md` | TAC methodology reference (read-only) |
| TAC Patterns | `.claude/commands/experts/tac/expertise.md` | Practical patterns (updated by self-improve) |
| Expert Files | `.claude/commands/experts/*/` | Expert structures to analyze |
| Hook Files | `.claude/hooks/` | Hook patterns to evaluate |
| Git History | `git log` | Recent changes and context |
| Specs | `.claude/specs/` | Task-specific plans created |
