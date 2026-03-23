---
description: "Query Strands Agents SDK features, @tool patterns, Agent class, or get answers without making changes"
allowed-tools: Read, Glob, Grep, Bash
---

# Strands SDK Expert - Question Mode

> Read-only command to query Strands SDK knowledge without making any changes.

## Purpose

Answer questions about the Strands Agents SDK — `Agent()`, `@tool` decorator, `BedrockModel`, subagent orchestration, plugin system, tool dispatch — **without making any code changes**.

## Usage

```
/experts:strands:question [question]
```

## Allowed Tools

`Read`, `Glob`, `Grep`, `Bash` (read-only commands only)

## Question Categories

### Category 1: Agent & Model Questions

Questions about `Agent()`, `BedrockModel`, model selection.

**Resolution**:
1. Read `.claude/commands/experts/strands/expertise.md` -> Parts 1-2
2. If needed, read `server/app/strands_agentic_service.py` for working code
3. Provide formatted answer with code sample

### Category 2: @tool Decorator Questions

Questions about tool creation, naming, signatures, return types.

**Resolution**:
1. Read `.claude/commands/experts/strands/expertise.md` -> Part 3
2. If needed, read factory functions in `strands_agentic_service.py`
3. Provide answer with decorator pattern

### Category 3: Tool Type Questions

Questions about service tools, subagent tools, utility tools.

**Resolution**:
1. Read `.claude/commands/experts/strands/expertise.md` -> Part 4
2. If needed, read `_make_subagent_tool()`, `_make_service_tool()` in code
3. Provide answer with the relevant factory pattern

### Category 4: Plugin System Questions

Questions about auto-discovery, plugin.json, SKILL_AGENT_REGISTRY.

**Resolution**:
1. Read `.claude/commands/experts/strands/expertise.md` -> Part 5
2. If needed, read `server/eagle_skill_constants.py` and `eagle-plugin/plugin.json`
3. Provide answer with discovery pipeline details

### Category 5: Tool Registration Questions

Questions about TOOL_DISPATCH, _SERVICE_TOOL_DEFS, how to add tools.

**Resolution**:
1. Read `.claude/commands/experts/strands/expertise.md` -> Parts 6, 9
2. If needed, read `server/app/agentic_service.py` TOOL_DISPATCH section
3. Provide step-by-step registration answer

### Category 6: Streaming & SSE Questions

Questions about result_queue, SSE events, sync-to-async bridge.

**Resolution**:
1. Read `.claude/commands/experts/strands/expertise.md` -> Part 8
2. If needed, read `server/app/streaming_routes.py` and `stream_protocol.py`
3. Provide answer with queue/SSE pattern

---

## Instructions

1. **Read expertise.md first** - All knowledge is stored there
2. **Never modify files** - This is a read-only command
3. **Include code samples** - SDK answers are most useful with working code
4. **Be specific** - Reference exact parts, sections, and line numbers
5. **Suggest next steps** - If appropriate, suggest what command to run next
