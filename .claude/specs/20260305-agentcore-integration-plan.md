# AgentCore Integration Plan

> Integrate Bedrock AgentCore SDK (Memory, Browser, Code Interpreter) + custom Web Search into EAGLE backend.

## Scope

| Tool | Source | Description |
|------|--------|-------------|
| `workspace_memory` | AgentCore Memory | Persistent scratchpad via MemorySessionManager |
| `web_search` | Custom (Brave + GovInfo) | Web/news/gov search |
| `browse_url` | AgentCore Browser | Managed Playwright sandbox |
| `code_execute` | AgentCore Code Interpreter | Python/JS/TS execution sandbox |

## New Files

| File | Purpose |
|------|---------|
| `server/app/agentcore_memory.py` | MemoryClient + MemorySessionManager wrapper |
| `server/app/search_service.py` | Brave Search + GovInfo API clients |
| `server/app/agentcore_browser.py` | BrowserClient wrapper |
| `server/app/agentcore_code.py` | CodeInterpreter wrapper |

## Modified Files

| File | Changes |
|------|---------|
| `server/app/agentic_service.py` | 4 new handlers + TOOL_DISPATCH + EAGLE_TOOLS |
| `server/app/strands_agentic_service.py` | _SERVICE_TOOL_DEFS + TIER_TOOLS + EAGLE_TOOLS |
| `server/requirements.txt` | Add `bedrock-agentcore` |

## Registration Checklist (per tool)

- [ ] Handler `_exec_{tool}()` in agentic_service.py
- [ ] TOOL_DISPATCH entry
- [ ] TOOLS_NEEDING_SESSION if per-user scoped
- [ ] EAGLE_TOOLS schema (both agentic_service.py and strands_agentic_service.py)
- [ ] _SERVICE_TOOL_DEFS in strands_agentic_service.py
- [ ] TIER_TOOLS gating (advanced/premium)
- [ ] SYSTEM_PROMPT guidance (optional)

## Tier Gating

| Tool | basic | advanced | premium |
|------|-------|----------|---------|
| workspace_memory | - | Yes | Yes |
| web_search | - | Yes | Yes |
| browse_url | - | - | Yes |
| code_execute | - | - | Yes |

## Environment Variables

```
BRAVE_SEARCH_API_KEY   — Brave Search API key
DATA_GOV_API_KEY       — GovInfo API key
AGENTCORE_MEMORY_ID    — AgentCore memory instance ID
```

## Validation

```bash
python -c "import py_compile; py_compile.compile('server/app/agentic_service.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/strands_agentic_service.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/agentcore_memory.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/search_service.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/agentcore_browser.py', doraise=True)"
python -c "import py_compile; py_compile.compile('server/app/agentcore_code.py', doraise=True)"
```
