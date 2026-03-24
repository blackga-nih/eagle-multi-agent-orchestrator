---
description: "Full ACT-LEARN-REUSE workflow: plan Strands changes, implement them, validate, and update expertise"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [feature description or tool/agent to implement]
---

# Strands SDK Expert - Plan Build Improve Workflow

> Full ACT-LEARN-REUSE workflow for Strands SDK development.

## Purpose

Execute the complete Strands development workflow:
1. **PLAN** - Design integration using expertise
2. **VALIDATE (baseline)** - Verify SDK imports and tool registry
3. **BUILD** - Implement the tool/agent/integration
4. **VALIDATE (post)** - Verify no regressions
5. **REVIEW** - Check patterns and registrations
6. **IMPROVE** - Update expertise with learnings

## Usage

```
/experts:strands:plan_build_improve [feature description]
```

## Variables

- `TASK`: $ARGUMENTS

---

## Workflow

### Step 1: PLAN (Context Loading)

1. Read `.claude/commands/experts/strands/expertise.md` for patterns
2. Analyze the TASK — determine tool type (service / subagent / utility)
3. Search codebase for related existing tools
4. Create implementation plan

### Step 2: VALIDATE (Baseline)

```bash
# Verify Strands imports
cd server && python -c "from strands import Agent, tool; print('OK')"

# Check current tool counts
cd server && python -c "
import sys; sys.path.insert(0, '.')
from app.agentic_service import TOOL_DISPATCH
from app.strands_agentic_service import SKILL_AGENT_REGISTRY
print(f'TOOL_DISPATCH: {len(TOOL_DISPATCH)}')
print(f'SKILL_AGENT_REGISTRY: {len(SKILL_AGENT_REGISTRY)}')
"

# Lint baseline
cd server && ruff check app/ --select E,F,W
```

**STOP if baseline fails** - Fix existing issues first.

### Step 3: BUILD (Implement Changes)

Follow the tool type workflow from `expertise.md` Part 9:

**Service tool**: handler -> TOOL_DISPATCH -> _SERVICE_TOOL_DEFS
**Subagent tool**: agent.md/SKILL.md -> plugin.json
**Utility tool**: factory function -> _build_service_tools()

### Step 4: VALIDATE (Post-Implementation)

```bash
# Lint
cd server && ruff check app/ --select E,F,W

# Import check
cd server && python -c "from strands import Agent, tool; print('OK')"

# Tool count check (should be baseline + 1)
cd server && python -c "
import sys; sys.path.insert(0, '.')
from app.agentic_service import TOOL_DISPATCH
from app.strands_agentic_service import SKILL_AGENT_REGISTRY
print(f'TOOL_DISPATCH: {len(TOOL_DISPATCH)}')
print(f'SKILL_AGENT_REGISTRY: {len(SKILL_AGENT_REGISTRY)}')
"
```

### Step 5: REVIEW

Check:
- Handler follows `(params, tenant_id, session_id=None) -> dict` signature
- @tool returns `str` (not dict)
- Tool name uses underscores (not hyphens)
- Description is specific about when to use the tool
- `result_queue` SSE emission included if needed
- Multi-tenant scoping via `tenant_id` parameter

### Step 6: IMPROVE (Self-Improve)

1. Determine outcome (success / partial / failed)
2. Update `.claude/commands/experts/strands/expertise.md` Learnings section
3. Update `last_updated` timestamp

---

## Report Format

```markdown
## Strands Integration Complete: {TASK}

### Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Plan | DONE | Tool type: {type} |
| Baseline | PASS | {N} tools, imports OK |
| Build | DONE | {description} |
| Validation | PASS | Lint + imports + tool count |
| Review | PASS | Follows Strands patterns |
| Improve | DONE | Expertise updated |

### Registration Checklist
- [x] Handler / factory / plugin entry
- [x] Registration in dispatch/manifest
- [x] Validation passes
```

---

## Instructions

1. **Follow the workflow order** - Don't skip validation steps
2. **Stop on failures** - Fix before proceeding
3. **Keep atomic** - One tool/agent per workflow
4. **Always improve** - Even failed attempts have learnings
