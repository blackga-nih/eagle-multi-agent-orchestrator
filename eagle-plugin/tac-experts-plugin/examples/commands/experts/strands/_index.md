---
type: expert-file
file-type: index
domain: strands
tags: [expert, strands-agents-sdk, bedrock, agent, tool, swarm, graph, multi-agent, streaming, sessions, hooks]
---

# Strands Agents SDK Expert

> Strands Agents SDK specialist for `Agent()`, `@tool`, multi-agent patterns (agents-as-tools, swarm, graph), BedrockModel, streaming, sessions, hooks, and AgentSkills integration.

## Domain Scope

This expert covers:
- **Core API** — `Agent()` constructor, `agent("prompt")` invocation, `stream_async()`
- **Model Providers** — `BedrockModel`, `AnthropicModel`, `LiteLLMModel`, custom providers
- **Tools** — `@tool` decorator, `ToolContext`, `tool_use_id`, `invocation_state`, hot-reload via `ToolWatcher`
- **Multi-Agent** — Agents-as-tools, Swarm (autonomous handoff), Graph (deterministic DAG), Workflow
- **Sessions** — `SessionManager`, `S3SessionManager`, `FileSessionManager`, conversation persistence
- **Streaming** — `callback_handler`, async iterators, `stream_async()`, custom `CallbackHandler`
- **Hooks** — `BeforeInvocationEvent`, `AfterInvocationEvent`, `HookRegistry`, lifecycle callbacks
- **Agent Skills** — AgentSkills.io spec, `discover_skills()`, `generate_skills_prompt()`, progressive disclosure
- **Concurrency** — Thread lock modes (THROW, REENTRANT), concurrent agent invocations
- **EAGLE Migration** — Claude Agent SDK → Strands migration patterns, prompt infrastructure reuse
- **Bridge Pattern** — Layer Strands on top of existing Claude SDK backend via `@tool` wrappers (incremental migration)

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:strands:question` | Answer Strands SDK questions without coding |
| `/experts:strands:plan` | Plan Strands integrations using expertise context |
| `/experts:strands:self-improve` | Update expertise after Strands usage sessions |
| `/experts:strands:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:strands:maintenance` | SDK health checks and validation |
| `/experts:strands:cheat-sheet` | Quick-reference with code samples |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for Strands Agents SDK |
| `cheat-sheet.md` | Quick-reference with copy-pasteable code samples |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for Strands integrations |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation and health check command |

## Architecture

```
strands-agents (pip package)
  |
  |-- Agent(model, system_prompt, tools, callback_handler, ...)
  |     |-- agent("prompt") -> AgentResult (sync)
  |     |-- agent.stream_async("prompt") -> AsyncIterator (async)
  |     |-- agent.system_prompt = "..." (mutable setter)
  |     |-- agent.tool  -> ToolRegistry
  |     |-- agent.conversation_manager -> ConversationManager
  |
  |-- BedrockModel(model_id, region_name, ...)
  |     |-- boto3 bedrock-runtime client
  |     |-- converse_stream() / converse()
  |     |-- Supports all Bedrock-hosted models
  |
  |-- @tool(name=...) decorator
  |     |-- Extracts JSON schema from docstring + type hints
  |     |-- ToolContext for invocation_state, agent access
  |     |-- Returns str or dict
  |
  |-- Multi-Agent Patterns
  |     |-- Agents-as-Tools: @tool-wrapped Agent (supervisor pattern)
  |     |-- Swarm: autonomous handoff via handoff_to_agent()
  |     |-- Graph: deterministic DAG with conditional edges
  |     |-- Workflow: acyclic task pipeline
  |
  |-- SessionManager
  |     |-- FileSessionManager (local disk)
  |     |-- S3SessionManager (cloud persistence)
  |     |-- Custom: implement read/write interface
  |
  |-- AgentSkills (agent-skills-sdk)
        |-- discover_skills(path) -> List[Skill]
        |-- generate_skills_prompt(skills) -> str
        |-- create_skill_tool(skills) -> @tool
        |-- create_skill_agent_tool(skills, tools) -> @tool
```

## Key Source Files

| File | Content |
|------|---------|
| `docs/development/20260302-*-report-claude-sdk-vs-strands-v1.md` | Architecture comparison report |
| `server/app/sdk_agentic_service.py` | Current Claude SDK service (migration source) |
| `server/eagle_skill_constants.py` | Skill discovery (reusable with Strands) |
| `server/app/plugin_store.py` | DynamoDB prompt store (reusable with Strands) |
| `eagle-plugin/` | Agent/skill definitions (format portable to Strands) |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Build Strands integrations using Agent(), @tool, multi-agent patterns
LEARN  ->  Update expertise.md with Strands behaviors and gotchas
REUSE  ->  Apply patterns to future Strands-powered features
```
