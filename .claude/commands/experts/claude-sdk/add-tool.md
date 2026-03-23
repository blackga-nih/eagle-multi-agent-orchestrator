---
description: "Add a new Strands @tool to EAGLE — scaffolds handler, registers in dispatch + service defs, validates"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [tool name, type (service|subagent|utility), and what it does]
model: opus
---

# Claude SDK Expert - Add New Tool

> Scaffold a new Strands `@tool` for the EAGLE supervisor agent. Handles all registration touchpoints so nothing is missed.

## Purpose

Adding a tool to the Strands-based EAGLE backend requires changes across multiple files depending on the tool type. A missed registration means the supervisor can't see or call the tool. This command handles every touchpoint.

## Variables

- `TASK`: $ARGUMENTS

## Instructions

- **CRITICAL**: You ARE writing code. Implement the full tool and all registrations.
- If no `TASK` is provided, STOP and ask the user: tool name, type (service / subagent / utility), and what it should do.
- Read `expertise.md` Part 11 (Strands Agents SDK) for exact patterns and file locations.

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

Read the file to find the existing handler functions (search for `def _exec_`). Add the new handler following the same pattern:

```python
def _exec_{tool_name}(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Description of what this tool does."""
    operation = params.get("operation", "default")
    # ... implementation ...
    return {"status": "success", "data": {...}}
```

**Rules**:
- Signature: `(params: dict, tenant_id: str, session_id: str = None) -> dict`
- Return dict — never raise (wrap errors in `{"error": str(exc)}`)
- Use `tenant_id` for scoping all AWS resources
- Use `session_id` only if tool needs per-user isolation (S3 prefix, etc.)

### 2a.2 — Register in `TOOL_DISPATCH` (~line 2548)

```python
TOOL_DISPATCH = {
    ...
    "{tool_name}": _exec_{tool_name},
}
```

If the tool needs `session_id`, also add to `TOOLS_NEEDING_SESSION`:

```python
TOOLS_NEEDING_SESSION = {"s3_document_ops", "create_document", "get_intake_status", "{tool_name}"}
```

### 2a.3 — Add to `_SERVICE_TOOL_DEFS` in `server/app/strands_agentic_service.py` (~line 1256)

```python
_SERVICE_TOOL_DEFS = {
    ...
    "{tool_name}": (
        "Clear description of what this tool does. "
        "Specify the expected JSON input format and available operations."
    ),
}
```

This is all that's needed — `_build_service_tools()` auto-wraps via `_make_service_tool()`.

### 2a.4 — (Optional) Add observability schema to `EAGLE_TOOLS` list (~line 345)

Add a schema dict for the `/tools` health endpoint:

```python
{
    "name": "{tool_name}",
    "description": "...",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "description": "..."},
        },
    },
},
```

---

## Step 2b: Subagent Tool (Specialist Agent)

### 2b.1 — Create agent/skill definition file

For an agent: `eagle-plugin/agents/{name}/agent.md`
For a skill: `eagle-plugin/skills/{name}/SKILL.md`

```yaml
---
name: {name}
description: "One-line description the supervisor sees for routing decisions"
triggers:
  - "keyword1"
  - "keyword2"
tools: []
model: null
---

# System prompt content for the subagent
...
```

### 2b.2 — Register in `eagle-plugin/plugin.json`

Add to the `agents` or `skills` array:

```json
{
  "agents": [..., "{name}"],
  "skills": [..., "{name}"]
}
```

Auto-discovery handles the rest: `eagle_skill_constants.py` -> `_build_registry()` -> `build_skill_tools()` -> `_make_subagent_tool()`.

---

## Step 2c: Utility Tool (Lightweight, No AWS)

### 2c.1 — Write factory function in `server/app/strands_agentic_service.py`

Add near the other `_make_*_tool()` factories (~line 825-1140):

```python
def _make_{tool_name}_tool(result_queue=None, loop=None):
    @tool(name="{tool_name}")
    def {tool_name}_tool(param: str) -> str:
        """Description for the model."""
        # lightweight logic — no AWS calls needed
        return json.dumps({...})

    return {tool_name}_tool
```

### 2c.2 — Append in `_build_service_tools()` (~line 1332)

```python
tools.append(_make_{tool_name}_tool(result_queue, loop))
```

---

## Step 3: Validate

Run these checks after implementation:

```bash
# Lint
cd server && ruff check app/ --select E,F,W

# Verify tool is discoverable (Python import check)
cd server && python -c "
from app.strands_agentic_service import _build_service_tools, build_skill_tools
print('Service tools:', len(_build_service_tools('test', 'test', None)))
print('Skill tools:', len(build_skill_tools()))
"
```

For service tools, also verify the dispatch:
```bash
cd server && python -c "
from app.agentic_service import TOOL_DISPATCH
assert '{tool_name}' in TOOL_DISPATCH, 'Missing from TOOL_DISPATCH!'
print('OK: {tool_name} registered in TOOL_DISPATCH')
"
```

---

## Registration Checklist

### Service Tool
- [ ] Handler function `_exec_{name}()` in `agentic_service.py`
- [ ] Entry in `TOOL_DISPATCH` dict
- [ ] Entry in `TOOLS_NEEDING_SESSION` (if needed)
- [ ] Entry in `_SERVICE_TOOL_DEFS` in `strands_agentic_service.py`
- [ ] (Optional) Schema in `EAGLE_TOOLS` list
- [ ] `ruff check` passes
- [ ] Import check passes

### Subagent Tool
- [ ] `agent.md` or `SKILL.md` file with YAML frontmatter
- [ ] Entry in `plugin.json` agents/skills array
- [ ] (Optional) Triggers array for auto-routing
- [ ] `ruff check` passes

### Utility Tool
- [ ] Factory function `_make_{name}_tool()` in `strands_agentic_service.py`
- [ ] Appended in `_build_service_tools()`
- [ ] `ruff check` passes
- [ ] Import check passes
