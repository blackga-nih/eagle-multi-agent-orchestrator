---
description: "Plan SDK integrations — new query patterns, subagent setups, custom tools, hooks — using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature description or SDK integration to plan]
---

# Claude SDK Expert - Plan Mode

> Create detailed plans for SDK integrations informed by expertise.

## Purpose

Generate a plan for adding new `query()` integrations, subagent orchestrations, custom tools, hook interceptors, or session patterns, using:
- Expertise from `.claude/commands/experts/claude-sdk/expertise.md`
- Current SDK usage patterns in the codebase
- Proven patterns from test_eagle_sdk_eval.py and test_agent_sdk.py
- Validation-first methodology

## Usage

```
/experts:claude-sdk:plan [feature description or SDK integration]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/claude-sdk/expertise.md` for:
   - `query()` API patterns
   - Session management lifecycle
   - Subagent orchestration patterns
   - Custom tool and MCP server setup
   - Hook system capabilities
   - Known issues and gotchas

2. Search current SDK usage:
   ```
   grep "from claude_agent_sdk" server/ -r
   grep "query(" server/ -r
   grep "ClaudeAgentOptions" server/ -r
   ```

3. Understand the TASK:
   - Is this a new query() integration?
   - Does it need subagents?
   - Does it need custom tools (MCP)?
   - Does it need hook interceptors?
   - Does it need session resume?

### Phase 2: Analyze Current State

1. Search for related code:
   ```
   grep "pattern" server/tests/ -r
   grep "pattern" server/app/ -r
   ```

2. Check existing patterns:
   - How do current tests use the SDK?
   - What ClaudeAgentOptions patterns exist?
   - Are there reusable TraceCollector/tool patterns?

3. Identify:
   - Files that need to change
   - New files to create
   - Dependencies and prerequisites
   - Impact on existing tests

### Phase 3: Generate Plan

Create a plan document:

```markdown
# SDK Integration Plan: {TASK}

## Overview
- Integration Type: query() | Subagent | Custom Tool | Hook | Session | Combined
- Files Modified: {list}
- New Files: {list}
- SDK Features Used: {list}
- Breaking Changes: Yes/No

## Design

### ClaudeAgentOptions Configuration

| Field | Value | Reason |
|-------|-------|--------|
| model | haiku | Cost-effective for this use case |
| system_prompt | "..." | Tenant context injection |
| allowed_tools | [...] | Tier-gated tool list |
| agents | {...} | Subagent definitions |
| mcp_servers | {...} | Custom tool servers |
| hooks | [...] | Lifecycle interceptors |
| max_budget_usd | 0.25 | Cost control |

### Implementation Steps

1. {step 1 with code reference}
2. {step 2 with code reference}
3. {step 3 with code reference}

### Message Processing

- How to process SystemMessage (session_id)
- How to process AssistantMessage (content blocks)
- How to process ResultMessage (usage, cost)

## Registration Checklist

- [ ] ClaudeAgentOptions configured
- [ ] Custom tools defined (if applicable)
- [ ] MCP server created (if applicable)
- [ ] Subagents defined (if applicable)
- [ ] Hooks registered (if applicable)
- [ ] TraceCollector or message handler implemented
- [ ] Cost tracking integrated

## Validation

1. Run the new SDK integration
2. Verify message flow (SystemMessage -> AssistantMessage -> ResultMessage)
3. Check cost is within budget
4. Verify session_id extraction
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/claude-sdk-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** - Contains all SDK patterns and conventions
2. **Reference existing test patterns** - test_eagle_sdk_eval.py has proven patterns
3. **Include ClaudeAgentOptions config** - The options object is the main configuration point
4. **Consider cost** - Always set max_budget_usd
5. **Consider multi-tenant** - system_prompt is the tenant context injection point
6. **Include message processing** - How to handle the async generator output

---

## Output Location

Plans are saved to: `.claude/specs/claude-sdk-{feature}.md`
