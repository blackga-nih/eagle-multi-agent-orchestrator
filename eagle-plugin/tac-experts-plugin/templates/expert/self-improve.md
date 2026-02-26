---
description: "Update {{DOMAIN}} expertise with new learnings"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# {{DOMAIN_TITLE}} Expert - Self-Improve Mode

> Update expertise.md with learnings from {{DOMAIN}} development work.

## Purpose

After completing {{DOMAIN}} work, run self-improve to:
- Record patterns that work (patterns_that_work)
- Record anti-patterns discovered (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add practical tips for future work

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:{{DOMAIN}}:self-improve [component] [success|failed|partial]
```

## Variables

- `COMPONENT`: $1 (component or area of {{DOMAIN}} work)
- `OUTCOME`: $2 (success | failed | partial)

## Allowed Tools

`Read`, `Write`, `Edit`, `Grep`, `Glob`

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/{{DOMAIN}}/expertise.md`
2. Scan for recent changes:
   ```
   Glob: {{SOURCE_GLOB_PATTERN}}
   ```
3. Check the COMPONENT context

### Phase 2: Analyze Outcome

**success**: What worked? Which patterns were effective? Any new patterns worth recording?

**failed**: What went wrong? Which patterns were violated? What context was missing?

**partial**: What succeeded and what didn't? What blockers were encountered?

### Phase 3: Update expertise.md

Add entries to the Learnings section:

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

Optionally update domain-specific Parts if new architecture or patterns discovered.

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter of expertise.md.

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
```

---

## Instructions

1. **Run after every significant session** — even failed attempts have learnings
2. **Be specific** — record concrete patterns, not vague observations
3. **Include context** — date, component, and circumstances
4. **Don't overwrite** — append to existing learnings
