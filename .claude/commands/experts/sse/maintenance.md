---
allowed-tools: Bash, Read, Grep, Glob
description: "Validate SSE pipeline health — event types, tool emission, frontend parsing, end-to-end flow"
argument-hint: [--syntax | --protocol | --emission | --frontend | --full]
---

# SSE Expert - Maintenance Command

Execute SSE pipeline health checks and report status.

## Purpose

Validate the EAGLE SSE streaming pipeline end-to-end — stream protocol integrity, tool result emission coverage, frontend type alignment, and event flow consistency.

## Usage

```
/experts:sse:maintenance --syntax
/experts:sse:maintenance --protocol
/experts:sse:maintenance --emission
/experts:sse:maintenance --frontend
/experts:sse:maintenance --full
```

## Presets

| Flag | Checks | Description |
|------|--------|-------------|
| `--syntax` | Syntax only | Python + TypeScript compile check |
| `--protocol` | Protocol integrity | Event types, writer methods, wire format |
| `--emission` | Tool emission coverage | Every tool has a result_queue path |
| `--frontend` | Frontend alignment | Types match backend, parse handlers exist |
| `--full` | Everything | All checks |

## Workflow

### Phase 1: Syntax Check (always run)

```bash
# Python syntax
cd server && python -c "
import ast
for f in ['app/stream_protocol.py', 'app/streaming_routes.py', 'app/strands_agentic_service.py']:
    ast.parse(open(f).read())
    print(f'  {f}: OK')
"

# TypeScript (if client/ exists)
cd client && npx tsc --noEmit 2>&1 | tail -3
```

If this fails, report the error and stop.

### Phase 2: Protocol Integrity (--protocol, --full)

```bash
# Verify StreamEventType enum matches frontend types
cd server && python -c "
from app.stream_protocol import StreamEventType
backend_types = {e.value for e in StreamEventType}
print(f'Backend event types: {sorted(backend_types)}')
"
```

Then grep frontend types:
```
Grep pattern="StreamEventType" in client/types/stream.ts
```

Compare backend enum values against frontend type union. Report mismatches.

Also verify `MultiAgentStreamWriter` has write methods for all event types:
```
Grep pattern="async def write_" in server/app/stream_protocol.py
```

### Phase 3: Tool Emission Coverage (--emission, --full)

Check that every tool type has a path to emit `tool_result`:

```bash
cd server && python -c "
import ast, re

# Count tool emission patterns
code = open('app/strands_agentic_service.py').read()

# Pattern A: _make_service_tool (has result_queue emission)
service_tools = re.findall(r'\"(\w+)\":\s*\(', code[code.find('_SERVICE_TOOL_DEFS'):code.find('_SERVICE_TOOL_DEFS')+3000])
print(f'Service tools ({len(service_tools)}): {service_tools}')

# Pattern B: _make_subagent_tool (has result_queue emission)
subagent_count = code.count('_make_subagent_tool')
print(f'Subagent tool factory calls: {subagent_count}')

# Pattern C: Factory tools with _emit_tool_result
factory_tools = re.findall(r'def (_make_\w+_tool)\(', code)
print(f'Factory tool builders: {factory_tools}')

# Check _emit_tool_result calls
emit_calls = re.findall(r'_emit_tool_result\(\"(\w+)\"', code)
print(f'_emit_tool_result calls for: {emit_calls}')

# Check for any @tool(name=...) NOT inside a factory
# These would be module-level singletons without result_queue access
import re
standalone = re.findall(r'^@tool\(name=\"(\w+)\"\)', code, re.MULTILINE)
print(f'Standalone @tool singletons: {standalone}')
if standalone:
    print('  WARNING: Standalone tools cannot emit tool_result!')
"
```

### Phase 4: Frontend Alignment (--frontend, --full)

Check frontend type definitions match backend:

```bash
# Check ServerToolResult interface exists
grep -n "ServerToolResult" client/hooks/use-agent-stream.ts

# Check tool_result handler exists in processEventData
grep -n "tool_result" client/hooks/use-agent-stream.ts

# Check onComplete merge logic exists
grep -n "onComplete" client/components/chat-simple/simple-chat-interface.tsx | head -5

# Check canExpand logic
grep -n "canExpand" client/components/chat-simple/tool-use-display.tsx
```

### Phase 5: Event Flow Consistency (--full)

Verify the drain/emit/forward chain:

```bash
cd server && python -c "
code = open('app/strands_agentic_service.py').read()
routes = open('app/streaming_routes.py').read()

# Check _drain_tool_results exists and filters empty names
has_drain = '_drain_tool_results' in code
has_empty_filter = 'if not name' in code
print(f'_drain_tool_results: {\"OK\" if has_drain else \"MISSING\"}'  )
print(f'Empty-name filter (backend): {\"OK\" if has_empty_filter else \"MISSING\"}')

# Check streaming_routes filters empty-name tool_result
has_route_filter = 'if not tr_name' in routes
print(f'Empty-name filter (routes): {\"OK\" if has_route_filter else \"MISSING\"}')

# Check complete event includes tools_called
has_tools_called = 'tools_called' in code
print(f'tools_called tracking: {\"OK\" if has_tools_called else \"MISSING\"}')
"
```

### Phase 6: Diagram Drift Check (--full)

Compare current pipeline state against the architecture diagram:

```
Read .claude/commands/experts/sse/diagrams/sse-pipeline-architecture.excalidraw.md
```

Check for drift:
- **New event types** — if backend `StreamEventType` has types not shown in the diagram's Layer 4 enum list, flag it
- **New tool emission patterns** — if new `_make_*_tool` factories exist that aren't in Layer 1, flag it
- **New frontend handlers** — if `processEventData()` routes types not shown in Layer 5, flag it
- **Test coverage changes** — if new test files exist in `client/tests/validate-*.spec.ts` not in the footer matrix, flag it

If any drift is found, include in the report:

```markdown
### Diagram Drift

The architecture diagram at `.claude/commands/experts/sse/diagrams/sse-pipeline-architecture.excalidraw.md` is out of date:

- [ ] {description of what changed and which layer to update}

**To update:** Run the excalidraw-agent or manually edit the diagram to reflect:
- Layer {N}: Add {new element}
- Footer: Add row for {new test file}
```

If no drift, report: `Diagram: UP TO DATE`

### Phase 7: Analyze and Report

## Report Format

```markdown
## SSE Maintenance Report

**Date**: {timestamp}
**Preset**: {flag}
**Status**: HEALTHY | DEGRADED | FAILED

### Syntax Check

| File | Status |
|------|--------|
| server/app/stream_protocol.py | PASS/FAIL |
| server/app/streaming_routes.py | PASS/FAIL |
| server/app/strands_agentic_service.py | PASS/FAIL |
| client/ TypeScript | PASS/FAIL |

### Protocol Integrity (if checked)

| Metric | Value |
|--------|-------|
| Backend event types | {list} |
| Frontend event types | {list} |
| Type alignment | OK / MISMATCH |
| Writer methods | {count} |

### Tool Emission Coverage (if checked)

| Tool Category | Count | Has Result Emission |
|--------------|-------|-------------------|
| Service tools (_make_service_tool) | {N} | YES |
| Subagent tools (_make_subagent_tool) | {N} | YES |
| Factory tools (_make_*_tool) | {N} | YES/NO |
| Standalone @tool singletons | {N} | NO (WARNING) |

### Frontend Alignment (if checked)

| Check | Status |
|-------|--------|
| ServerToolResult interface | OK/MISSING |
| tool_result handler | OK/MISSING |
| onComplete merge logic | OK/MISSING |
| canExpand logic | OK/MISSING |

### Diagram Drift (if checked)

- Status: UP TO DATE | STALE
- Stale layers: {list of layers needing update}
- Action: {edit instructions or "none needed"}

### Issues Found

- {issue description and recommended fix}

### Next Steps

- {recommended actions}
```

## Quick Checks

```bash
# Fastest: just syntax
cd server && python -c "import ast; ast.parse(open('app/stream_protocol.py').read()); print('OK')"

# Count event types
cd server && python -c "from app.stream_protocol import StreamEventType; print([e.value for e in StreamEventType])"

# Check tool emission coverage
cd server && grep -c "_emit_tool_result\|result_queue.put_nowait" app/strands_agentic_service.py

# Check for standalone @tool singletons (should be zero)
cd server && grep -n "^@tool(name=" app/strands_agentic_service.py
```

## Troubleshooting

### Missing Chevron on Tool Card
1. Check if the tool emits `tool_result` via `_emit_tool_result()` or `result_queue.put_nowait()`
2. Check if the tool name matches between `tool_use` and `tool_result` events
3. Check if `_drain_tool_results()` filters it out (empty name?)
4. Check `streaming_routes.py` empty-name filter
5. Check `canExpand` logic in `tool-use-display.tsx`

### Duplicate Tool Events
1. Check `_current_tool_id` dedup in stream event handler
2. Verify only one of `current_tool_use` / `contentBlockStart` fires

### tool_result Not Matching Tool Card
1. Verify `tool_name` in `_emit_tool_result()` matches the `@tool(name=...)` decorator
2. Check FIFO ordering in `onComplete` — if tool called twice, order matters
3. Check `resultsByName` Map construction in `simple-chat-interface.tsx`

### Stale Server Serving Old Code
1. Kill zombie processes: `netstat -ano | grep :8000 | grep LISTENING`
2. Tree kill: `taskkill /F /T /PID {pid}`
3. Verify reload: check uvicorn logs for file change detection
