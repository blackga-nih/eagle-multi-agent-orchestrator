---
description: "Plan Strands integrations — new Agent setups, multi-agent patterns, tool creation, migration steps — using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature description or Strands integration to plan]
---

# Strands SDK Expert - Plan Mode

> Create detailed plans for Strands integrations informed by expertise.

## Purpose

Generate a plan for adding new Strands `Agent()` integrations, multi-agent orchestrations, custom `@tool` functions, streaming handlers, session persistence, or Claude SDK migration steps, using:
- Expertise from `.claude/commands/experts/strands/expertise.md`
- Current SDK usage patterns in the codebase
- Migration mapping from the Claude SDK comparison report
- Validation-first methodology

## Usage

```
/experts:strands:plan [feature description or Strands integration]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/strands/expertise.md` for:
   - `Agent()` constructor patterns
   - `BedrockModel` shared model pattern
   - Multi-agent patterns (agents-as-tools, swarm, graph)
   - `@tool` decorator and ToolContext
   - Session management options
   - Streaming and callback handlers
   - EAGLE migration mapping
   - Known issues and gotchas

2. Search current codebase for migration context:
   ```
   grep "from strands" server/ -r
   grep "BedrockModel" server/ -r
   grep "from claude_agent_sdk" server/ -r
   grep "AgentDefinition" server/ -r
   ```

3. Understand the TASK:
   - Is this a new Strands Agent integration?
   - Is it a migration from Claude Agent SDK?
   - Does it need multi-agent patterns (swarm, graph)?
   - Does it need custom @tool functions?
   - Does it need session persistence?
   - Does it need SSE streaming?

### Phase 2: Analyze Current State

1. Search for related code:
   ```
   grep "pattern" server/app/ -r
   grep "pattern" server/tests/ -r
   ```

2. Check existing patterns:
   - How does `sdk_agentic_service.py` currently work?
   - What does `build_skill_agents()` return?
   - What DynamoDB infrastructure exists (`plugin_store.py`, `wspc_store.py`)?

3. Identify:
   - Files that need to change
   - New files to create
   - Dependencies and prerequisites
   - Impact on existing functionality

### Phase 3: Generate Plan

Create a plan document:

```markdown
# Strands Integration Plan: {TASK}

## Overview
- Integration Type: Agent | Multi-Agent | Tool | Migration | Session | Streaming
- Files Modified: {list}
- New Files: {list}
- Strands Features Used: {list}
- Migration Impact: {description}

## Design

### Agent Configuration

| Component | Value | Reason |
|-----------|-------|--------|
| BedrockModel | shared module-level | Avoid per-request boto3 overhead |
| system_prompt | from DynamoDB | Hot-reloadable per-request |
| tools | [...] | Tier-gated tool list |
| callback_handler | None / Custom | Server-side: None |
| session_manager | DynamoDB custom | Multi-tenant persistence |

### Multi-Agent Pattern (if applicable)

| Pattern | When to Use |
|---------|-------------|
| Agents-as-Tools | Supervisor → specialist (current EAGLE pattern) |
| Swarm | Autonomous multi-step handoff |
| Graph | Deterministic pipeline |

### Implementation Steps

1. {step 1 with code reference}
2. {step 2 with code reference}
3. {step 3 with code reference}

### Streaming Setup

- How to handle `stream_async()` for SSE
- Callback handler for real-time events
- Error propagation through stream

## Migration Checklist (if applicable)

- [ ] Shared BedrockModel at module level
- [ ] Per-request Agent construction with DynamoDB prompts
- [ ] Subagent @tool wrappers (replacing AgentDefinition)
- [ ] Streaming adapter (callback handler → SSE)
- [ ] Session manager (replacing resume: session_id)
- [ ] Tier-gated tool lists mapped
- [ ] Multi-tenant system_prompt injection
- [ ] Cost tracking integrated

## Validation

1. Run `pip install strands-agents` and verify import
2. Verify BedrockModel connects to Bedrock
3. Test basic Agent invocation
4. Test multi-agent routing (if applicable)
5. Verify streaming works end-to-end
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/strands-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** — Contains all Strands patterns and conventions
2. **Reference migration mapping** — expertise.md Part 11 has the Claude→Strands mapping
3. **Include shared model pattern** — Always recommend shared `BedrockModel` at module level
4. **Consider hot-reload** — DynamoDB prompt infrastructure must be preserved
5. **Consider multi-tenant** — system_prompt is the tenant context injection point
6. **Include streaming setup** — Most integrations need SSE streaming

---

## Output Location

Plans are saved to: `.claude/specs/strands-{feature}.md`
