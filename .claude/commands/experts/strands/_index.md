---
user-invocable: false
description: "Internal domain index for the strands expert (Strands Agents SDK, @tool patterns, BedrockModel). Use /experts:strands:question to query, /experts:strands:plan to plan, /experts:strands:maintenance to check health."
type: expert-file
file-type: index
domain: strands
tags: [expert, strands-agents, bedrock, tool, agent, subagent, streaming, multi-tenant, supervisor, skill-registry]
---

# Strands Agents SDK Expert

> Strands Agents SDK specialist for `Agent()`, `@tool` factories, `BedrockModel`, subagent orchestration, skill registry, plugin auto-discovery, SSE streaming, and multi-tenant tool dispatch.

## Domain Scope

This expert covers:
- **Core API** - `Agent()` constructor, `@tool` decorator, `BedrockModel` provider
- **Tool Types** - Service tools, subagent tools, utility tools, progressive disclosure tools
- **Subagents** - `_make_subagent_tool()` factory, fresh Agent per call, prompt truncation
- **Service Tools** - `_make_service_tool()` factory, `TOOL_DISPATCH`, `TOOLS_NEEDING_SESSION`
- **Plugin System** - `eagle_skill_constants.py` auto-discovery, `plugin.json` manifest, `SKILL_AGENT_REGISTRY`
- **Supervisor** - `build_supervisor_prompt()`, progressive disclosure layers, agent list injection
- **Streaming** - `result_queue` + `asyncio.Queue` + SSE events via `MultiAgentStreamWriter`
- **Multi-Tenant** - Tenant-scoped session IDs, per-user S3 paths, tier-gated tool sets
- **Bedrock Backend** - boto3-native `converse` API, model ID selection, SSO/IAM credentials

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:strands:question` | Answer Strands SDK questions without coding |
| `/experts:strands:plan` | Plan Strands integrations using expertise context |
| `/experts:strands:self-improve` | Update expertise after Strands usage sessions |
| `/experts:strands:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:strands:maintenance` | SDK health checks and validation |
| `/experts:strands:cheat-sheet` | Quick-reference with code samples |
| `/experts:strands:add-tool` | Scaffold a new @tool (service, subagent, or utility) |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for Strands Agents SDK in EAGLE |
| `add-tool.md` | Scaffold new @tool (service, subagent, or utility) |
| `cheat-sheet.md` | Quick-reference with copy-pasteable code samples |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for SDK integrations |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation and health check command |

## Architecture

```
strands-agents (pip) + strands-agents-bedrock (pip)
  |
  |-- Agent(model, system_prompt, tools, callback_handler)
  |     |-- model: BedrockModel instance (shared singleton)
  |     |-- system_prompt: str (supervisor or subagent prompt)
  |     |-- tools: list[@tool-decorated functions]
  |     |-- callback_handler: None (streaming via queue instead)
  |     |-- agent(prompt) -> str (sync call, Strands handles agentic loop)
  |
  |-- @tool(name=str)
  |     |-- Decorator for custom tool functions
  |     |-- Docstring = description for the model
  |     |-- Type hints = input schema
  |     |-- Return: str (JSON-serialized result)
  |
  |-- BedrockModel(model_id, region_name)
  |     |-- boto3-native converse API
  |     |-- No credential bridging — uses SSO/IAM natively
  |     |-- Shared across all Agent instances
  |
  |-- Tool Factories (EAGLE-specific)
  |     |-- _make_subagent_tool() -> @tool wrapping Agent()
  |     |-- _make_service_tool() -> @tool wrapping TOOL_DISPATCH handlers
  |     |-- _make_*_tool() -> utility/progressive disclosure tools
  |
  |-- Plugin System
  |     |-- eagle_skill_constants.py: auto-discovers agent.md + SKILL.md
  |     |-- plugin.json: active agents/skills manifest
  |     |-- SKILL_AGENT_REGISTRY: runtime registry for build_skill_tools()
  |
  |-- Streaming
        |-- result_queue: asyncio.Queue for tool results + metadata
        |-- loop.call_soon_threadsafe(): bridge sync agent -> async SSE
        |-- SSE events: text, tool_use, tool_result, metadata, complete, error
```

## Key Source Files

| File | Content |
|------|---------|
| `server/app/strands_agentic_service.py` | Strands orchestration, @tool factories, Agent instantiation |
| `server/app/agentic_service.py` | Tool handler implementations, TOOL_DISPATCH, TOOLS_NEEDING_SESSION |
| `server/app/tools/knowledge_tools.py` | Knowledge base tool schemas + handlers |
| `server/eagle_skill_constants.py` | Plugin auto-discovery: AGENTS, SKILLS, PLUGIN_CONTENTS |
| `eagle-plugin/plugin.json` | Active agents/skills manifest |
| `server/app/streaming_routes.py` | SSE endpoint, calls sdk_query_streaming() |
| `server/app/stream_protocol.py` | MultiAgentStreamWriter, SSE event format |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Write Strands integrations: tools, subagents, plugin entries
LEARN  ->  Update expertise.md with Strands behaviors and gotchas
REUSE  ->  Apply patterns to future tool/agent additions
```
