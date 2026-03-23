---
description: "Update Strands expertise with learnings from tool implementations, debugging, or agent changes"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---

# Strands SDK Expert - Self-Improve Mode

> Update expertise.md with learnings from Strands development and debugging.

## Purpose

After implementing tools, adding subagents, or debugging Strands issues, run self-improve to:
- Record what worked (patterns_that_work)
- Record what to avoid (patterns_to_avoid)
- Document issues encountered (common_issues)
- Add tips for future Strands development

This is the **LEARN** step in ACT-LEARN-REUSE.

## Usage

```
/experts:strands:self-improve tools success
/experts:strands:self-improve subagents failed
/experts:strands:self-improve streaming partial
```

## Variables

- `COMPONENT`: $1 (component or area changed)
- `OUTCOME`: $2 (success | failed | partial)

---

## Workflow

### Phase 1: Gather Information

1. Read current `.claude/commands/experts/strands/expertise.md`
2. Read recent changes:
   - `server/app/strands_agentic_service.py` — tool factories, Agent usage
   - `server/app/agentic_service.py` — TOOL_DISPATCH, handler implementations
   - `eagle-plugin/plugin.json` — agent/skill registry
   - Git log for recent commits:
     ```bash
     git log --oneline -10
     git diff HEAD~3 --stat
     ```

### Phase 2: Analyze Outcome

Based on OUTCOME:

**success**: What pattern made the implementation successful? New behaviors discovered?
**failed**: What caused the failure? What should be avoided?
**partial**: What worked vs. what didn't? What remains?

### Phase 3: Update expertise.md

Add entries to the appropriate Learnings subsection:

```markdown
### patterns_that_work
- {what worked} (discovered: {date})

### patterns_to_avoid
- {what to avoid} (reason: {why})

### common_issues
- {issue}: {solution} (component: {COMPONENT})

### tips
- {useful tip learned}
```

### Phase 4: Update timestamp

Update the `last_updated` field in the frontmatter.

---

## Instructions

1. **Run after every significant Strands change** - Even failed attempts have learnings
2. **Be specific** - Record concrete behaviors, not vague observations
3. **Include context** - Date, component, and circumstances
4. **Don't overwrite** - Append to existing learnings, don't replace
5. **Update cheat-sheet.md** - If a new important pattern was discovered

---

## Queue & Cross-Domain (Auto-Added by Skills Optimization)

### Pre-flight: Check self-improve queue

Before analyzing, check if this domain was queued by the session-end hook:

```bash
cat .claude/context/self-improve-queue.json 2>/dev/null | python3 -c "
import sys, json
q = json.load(sys.stdin)
domains = q.get('domains', [])
print('Queued domains:', ', '.join(domains) if domains else 'none')
"
```

If this domain appears in the queue, pay extra attention to the recently changed files listed in the queue history.

### Post-update: Cross-domain propagation

After updating expertise.md, check if any learnings affect other domains:

- If a learning applies to 2+ domains → append it to `.claude/context/cross-domain-learnings.md`
- Format: `## YYYY-MM-DD — [short title]` with `Discovered by`, `Affects`, `Learning`, `Action taken` fields
- Then remove this domain from the queue:

```bash
python3 -c "
import json, sys
path = '.claude/context/self-improve-queue.json'
try:
    with open(path) as f: q = json.load(f)
    q['domains'] = [d for d in q.get('domains',[]) if d != 'strands']
    with open(path,'w') as f: json.dump(q, f, indent=2)
    print('Removed strands from queue')
except FileNotFoundError:
    pass
"
```
