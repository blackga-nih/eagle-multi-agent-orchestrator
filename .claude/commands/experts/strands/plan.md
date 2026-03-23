---
description: "Plan Strands SDK integrations — new tools, subagents, plugin entries — using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature description or tool/agent to add]
---

# Strands SDK Expert - Plan Mode

> Create detailed plans for Strands SDK integrations informed by expertise.

## Purpose

Generate a plan for adding new @tool functions, subagent definitions, service tool handlers, plugin entries, or streaming patterns, using:
- Expertise from `.claude/commands/experts/strands/expertise.md`
- Current Strands usage patterns in `server/app/strands_agentic_service.py`
- Plugin system in `eagle-plugin/` and `eagle_skill_constants.py`
- Validation-first methodology

## Usage

```
/experts:strands:plan [feature description or tool/agent to add]
```

## Variables

- `TASK`: $ARGUMENTS

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/strands/expertise.md` for:
   - @tool decorator patterns
   - Three tool types (service, subagent, utility)
   - Plugin auto-discovery pipeline
   - TOOL_DISPATCH registration
   - Streaming/SSE integration

2. Search current Strands usage:
   ```
   grep "from strands" server/ -r
   grep "@tool" server/app/strands_agentic_service.py
   grep "TOOL_DISPATCH" server/app/agentic_service.py
   ```

3. Understand the TASK:
   - Is this a new service tool (AWS handler)?
   - Is this a new subagent (specialist agent)?
   - Is this a new utility tool (progressive disclosure)?
   - Does it need SSE streaming integration?

### Phase 2: Analyze Current State

1. Check existing tools:
   - `_SERVICE_TOOL_DEFS` keys in `strands_agentic_service.py`
   - `TOOL_DISPATCH` keys in `agentic_service.py`
   - `plugin.json` agents/skills lists
   - `SKILL_AGENT_REGISTRY` entries

2. Identify:
   - Files that need to change
   - New files to create
   - Dependencies and prerequisites
   - Impact on existing tools

### Phase 3: Generate Plan

Create a plan document in `.claude/specs/strands-{feature}.md`:

```markdown
# Strands Integration Plan: {TASK}

## Overview
- Tool Type: service | subagent | utility
- Files Modified: {list}
- New Files: {list}

## Implementation Steps
1. {step with file reference}
2. {step with file reference}

## Registration Checklist
- [ ] Handler / factory / plugin entry
- [ ] TOOL_DISPATCH (if service)
- [ ] _SERVICE_TOOL_DEFS (if service)
- [ ] plugin.json (if subagent)
- [ ] _build_service_tools() (if utility)

## Validation
- ruff check
- import check
- tool count verification
```

---

## Instructions

1. **Always read expertise.md first** - Contains all Strands patterns
2. **Determine tool type early** - Service vs subagent vs utility changes the workflow
3. **Include registration checklist** - Missing registrations are the #1 failure mode
4. **Consider streaming** - Does the tool need to emit SSE events via result_queue?
5. **Consider multi-tenant** - Does the tool need tenant_id scoping?
