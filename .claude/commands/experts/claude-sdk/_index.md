---
type: expert-file
file-type: index
domain: claude-sdk
tags: [expert, claude-agent-sdk, query, sessions, subagents, mcp, hooks, telemetry, cost, bedrock]
---

# Claude Agent SDK Expert

> Claude Agent SDK specialist for `query()`, sessions, subagents, custom tools/MCP, hooks, telemetry, cost tracking, and multi-tenant integration.

## Domain Scope

This expert covers:
- **Core API** - `query()` async generator, `ClaudeAgentOptions`, `ClaudeSDKClient`
- **Sessions** - Creation, resume, `session_id` extraction from SystemMessage/ResultMessage
- **Subagents** - `AgentDefinition`, `agents={}` config, `parent_tool_use_id` tracking
- **Custom Tools** - `@tool` decorator, `create_sdk_mcp_server()`, MCP naming convention
- **Hooks** - `HookMatcher`, PreToolUse/PostToolUse/Stop/SubagentStop/PreCompact callbacks
- **Telemetry** - TraceCollector pattern, message types, streaming protocol
- **Cost Tracking** - `ResultMessage.usage`, token accounting, budget limits
- **Multi-Tenant** - `system_prompt` injection, tenant scoping, tier-gated tools
- **Bedrock Backend** - `CLAUDE_CODE_USE_BEDROCK=1`, `toolu_bdrk_` prefix detection

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:claude-sdk:question` | Answer SDK questions without coding |
| `/experts:claude-sdk:plan` | Plan SDK integrations using expertise context |
| `/experts:claude-sdk:self-improve` | Update expertise after SDK usage sessions |
| `/experts:claude-sdk:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:claude-sdk:maintenance` | SDK health checks and validation |
| `/experts:claude-sdk:cheat-sheet` | Quick-reference with code samples |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for Claude Agent SDK (~500 lines) |
| `cheat-sheet.md` | Quick-reference with copy-pasteable code samples |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for SDK integrations |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation and health check command |

## Architecture

```
claude-agent-sdk (pip package >= 0.1.29)
  |
  |-- query(prompt, options) -> AsyncGenerator[Message]
  |     |-- SystemMessage: session_id in data dict
  |     |-- AssistantMessage: content blocks (Text, Thinking, ToolUse)
  |     |-- UserMessage: content blocks (ToolResult)
  |     |-- ResultMessage: usage dict, session_id, total_cost_usd
  |
  |-- ClaudeAgentOptions
  |     |-- model: "haiku" | "sonnet" | "opus"
  |     |-- system_prompt: str (tenant context injection point)
  |     |-- allowed_tools: list[str] (tier-gated)
  |     |-- agents: dict[str, AgentDefinition] (subagent registry)
  |     |-- mcp_servers: dict[str, MCPServer] (custom tool servers)
  |     |-- hooks: list[HookMatcher] (lifecycle callbacks)
  |     |-- permission_mode: "bypassPermissions" | "default"
  |     |-- max_turns: int
  |     |-- max_budget_usd: float
  |     |-- resume: str (session_id for multi-turn)
  |     |-- cwd: str
  |     |-- env: dict[str, str]
  |
  |-- AgentDefinition
  |     |-- description: str (when to use this agent)
  |     |-- prompt: str (agent behavior instructions)
  |     |-- tools: list[str] (scoped tool access)
  |     |-- model: str (can differ from parent)
  |
  |-- ClaudeSDKClient
  |     |-- connect() / disconnect()
  |     |-- query(prompt) -> send prompt
  |     |-- receive_response() -> AsyncGenerator[Message]
  |     |-- Session maintained across multiple queries
  |
  |-- @tool(name, description, InputDataclass)
  |     |-- Decorator for custom tool functions
  |     |-- Input: @dataclass with typed fields
  |     |-- Return: {"content": [{"type": "text", "text": "..."}]}
  |
  |-- create_sdk_mcp_server(name, tools=[...])
  |     |-- Factory for MCP tool servers
  |     |-- Tool naming: mcp__{server_name}__{tool_name}
  |
  |-- HookMatcher
  |     |-- matcher: str (PreToolUse, PostToolUse, Stop, etc.)
  |     |-- hooks: list[async callback]
  |     |-- timeout: int (ms)
  |
  |-- Hook Types
        |-- PreToolUseHookInput -> permissionDecision, updatedInput
        |-- PostToolUseHookInput -> additionalContext
        |-- StopHookInput -> decision (stop/continue)
        |-- SubagentStartHookInput / SubagentStopHookInput
        |-- PreCompactHookInput
```

## Key Source Files

| File | Content |
|------|---------|
| `server/tests/test_eagle_sdk_eval.py` | TraceCollector, query() patterns, session mgmt, cost tracking |
| `server/tests/test_agent_sdk.py` | @tool decorator, MCP server, ClaudeSDKClient, hooks, subagents |
| `server/app/agentic_service.py` | Bedrock config, model selection, tool dispatch |
| `server/app/session_store.py` | DynamoDB session schema, create/resume patterns |
| `server/app/admin_service.py` | Cost calculation, usage recording |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Write SDK integrations using query(), sessions, subagents, tools, hooks
LEARN  ->  Update expertise.md with SDK behaviors and gotchas
REUSE  ->  Apply patterns to future SDK-powered features
```
