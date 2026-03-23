---
description: "Add a new Strands @tool to EAGLE — scaffolds handler, registers in dispatch + service defs, validates"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [tool name, type (service|subagent|utility), and what it does]
model: opus
---

# Strands SDK Expert - Add New Tool

> Scaffold a new Strands `@tool` for the EAGLE supervisor agent. Handles all registration touchpoints so nothing is missed.

## Purpose

Adding a tool to the Strands-based EAGLE backend requires changes across multiple files depending on the tool type. A missed registration means the supervisor can't see or call the tool. This command handles every touchpoint.

## Variables

- `TASK`: $ARGUMENTS

## Instructions

- **CRITICAL**: You ARE writing code. Implement the full tool and all registrations.
- If no `TASK` is provided, STOP and ask the user: tool name, type (service / subagent / utility), and what it should do.
- Read `expertise.md` Part 9 (Adding New Tools) for exact patterns and file locations.

---

## Step 1: Determine Tool Type

| Type | When to use | Files touched |
|------|-------------|---------------|
| **Service** | AWS-backed operations (S3, DynamoDB, API calls) | `agentic_service.py` + `strands_agentic_service.py` |
| **Subagent** | Specialist agent with own system prompt | `eagle-plugin/` + `plugin.json` |
| **Utility** | Lightweight, no AWS, progressive disclosure | `strands_agentic_service.py` only |

---

## Step 2a: Service Tool (AWS-backed)

### 2a.1 — Write handler in `server/app/agentic_service.py`

Read the file to find existing handlers (search for `def _exec_`). Add new handler:

```python
def _exec_{tool_name}(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Description of what this tool does."""
    operation = params.get("operation", "default")
    # ... implementation ...
    return {"status": "success", "data": {...}}
```

**Rules**: Signature `(params, tenant_id, session_id=None) -> dict`. Never raise — wrap errors.

### 2a.2 — Register in `TOOL_DISPATCH` (~line 2548)

```python
TOOL_DISPATCH = { ..., "{tool_name}": _exec_{tool_name} }
```

If needs session: add to `TOOLS_NEEDING_SESSION`.

### 2a.3 — Add to `_SERVICE_TOOL_DEFS` (~line 1256 in `strands_agentic_service.py`)

```python
_SERVICE_TOOL_DEFS = { ..., "{tool_name}": "Clear description with JSON input format." }
```

### 2a.4 — (Optional) Add schema to `EAGLE_TOOLS` (~line 345)

---

## Step 2b: Subagent Tool (Specialist Agent)

### 2b.1 — Create definition file

`eagle-plugin/agents/{name}/agent.md` or `eagle-plugin/skills/{name}/SKILL.md` with YAML frontmatter.

### 2b.2 — Register in `eagle-plugin/plugin.json`

---

## Step 2c: Utility Tool (Lightweight)

### 2c.1 — Write factory in `strands_agentic_service.py`

### 2c.2 — Append in `_build_service_tools()`

---

## Step 3: Validate

```bash
cd server && ruff check app/ --select E,F,W

cd server && python -c "
import sys; sys.path.insert(0, '.')
from app.agentic_service import TOOL_DISPATCH
assert '{tool_name}' in TOOL_DISPATCH, 'Missing from TOOL_DISPATCH!'
print('OK: registered')
"
```

---

## Registration Checklist

### Service Tool
- [ ] Handler `_exec_{name}()` in `agentic_service.py`
- [ ] Entry in `TOOL_DISPATCH`
- [ ] Entry in `TOOLS_NEEDING_SESSION` (if needed)
- [ ] Entry in `_SERVICE_TOOL_DEFS`
- [ ] (Optional) Schema in `EAGLE_TOOLS`
- [ ] `ruff check` passes

### Subagent Tool
- [ ] `agent.md` or `SKILL.md` with YAML frontmatter
- [ ] Entry in `plugin.json`
- [ ] `ruff check` passes

### Utility Tool
- [ ] Factory `_make_{name}_tool()` in `strands_agentic_service.py`
- [ ] Appended in `_build_service_tools()`
- [ ] `ruff check` passes
