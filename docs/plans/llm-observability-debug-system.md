# EAGLE LLM Observability & Debug System

## Context

**Problem**: EAGLE chat responses are slow, and there's no way to see what prompts, context, and tools are being sent to the LLM (Bedrock/Claude via Strands SDK). Developers need visibility into:
- Full system prompts being constructed
- All tools registered with each Agent() call
- Token/character counts before sending
- Performance timing breakdown
- Raw API payloads when debugging Bedrock issues

**Current State**:
- `callback_handler=None` on all Agent() instances (SDK handles loops internally)
- `stream_async()` yields events but not prompt content
- Existing telemetry captures tokens/costs/tool calls but NOT prompts
- Log level hardcoded to INFO with no debug override
- No request-level debug flag

**Outcome**: A debug mode that logs full prompts, tools, and timing without impacting production performance.

---

## Implementation Plan

### Phase 1: Debug Configuration Module

**New file**: `server/app/debug_config.py`

```python
import os
import logging
from contextvars import ContextVar

# Environment flags
EAGLE_DEBUG = os.getenv("EAGLE_DEBUG", "0") == "1"
EAGLE_DEBUG_BOTOCORE = os.getenv("EAGLE_DEBUG_BOTOCORE", "0") == "1"
EAGLE_DEBUG_PROMPTS = os.getenv("EAGLE_DEBUG_PROMPTS", "0") == "1"

# Request-level debug (set via header/query)
_request_debug: ContextVar[bool] = ContextVar("request_debug", default=False)

def is_debug_enabled() -> bool:
    return EAGLE_DEBUG or _request_debug.get()

def set_request_debug(enabled: bool):
    _request_debug.set(enabled)

def configure_debug_logging():
    """Call after configure_logging() in main.py"""
    if EAGLE_DEBUG:
        logging.getLogger("eagle").setLevel(logging.DEBUG)
        logging.getLogger("eagle.strands_agent").setLevel(logging.DEBUG)
    if EAGLE_DEBUG_BOTOCORE:
        logging.getLogger("botocore").setLevel(logging.DEBUG)
```

**Integration**: `server/app/main.py` line 127
```python
from .debug_config import configure_debug_logging
configure_debug_logging()
```

---

### Phase 2: Prompt Snapshot Capture

**New file**: `server/app/telemetry/prompt_snapshot.py`

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json

@dataclass
class PromptSnapshot:
    """Captures full prompt context before LLM call."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_type: str = ""  # "supervisor" | "subagent:{name}"

    # Prompt content
    system_prompt: str = ""
    system_prompt_chars: int = 0
    system_prompt_tokens_est: int = 0  # chars // 4

    user_message: str = ""
    user_message_chars: int = 0

    # History
    history_message_count: int = 0
    history_chars: int = 0

    # Tools
    tool_names: list = field(default_factory=list)
    tool_count: int = 0

    # Context
    tenant_id: str = ""
    user_id: str = ""
    session_id: str = ""
    workspace_id: str = ""
    tier: str = ""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 4

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent_type": self.agent_type,
            "system_prompt_chars": self.system_prompt_chars,
            "system_prompt_tokens_est": self.system_prompt_tokens_est,
            "user_message_chars": self.user_message_chars,
            "history_message_count": self.history_message_count,
            "history_chars": self.history_chars,
            "tool_names": self.tool_names,
            "tool_count": self.tool_count,
            "tenant_id": self.tenant_id,
            "tier": self.tier,
        }

    def to_full_dict(self) -> dict:
        """Include full prompt text (for detailed debug)."""
        d = self.to_dict()
        d["system_prompt"] = self.system_prompt
        d["user_message"] = self.user_message
        return d
```

---

### Phase 3: Prompt Debugger Class

**New file**: `server/app/telemetry/prompt_debugger.py`

```python
import time
import json
import logging
from typing import Any
from .prompt_snapshot import PromptSnapshot

logger = logging.getLogger("eagle.debug")

class PromptDebugger:
    """Captures and logs prompt snapshots with timing."""

    def __init__(self, tenant_id: str, user_id: str, session_id: str = ""):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.session_id = session_id
        self.snapshots: list[PromptSnapshot] = []
        self._timings: dict[str, float] = {}

    def capture_supervisor(
        self,
        system_prompt: str,
        user_message: str,
        tools: list,
        messages: list | None,
        workspace_id: str = "",
        tier: str = "",
    ) -> PromptSnapshot:
        history_chars = sum(len(str(m)) for m in (messages or []))
        snapshot = PromptSnapshot(
            agent_type="supervisor",
            system_prompt=system_prompt,
            system_prompt_chars=len(system_prompt),
            system_prompt_tokens_est=PromptSnapshot.estimate_tokens(system_prompt),
            user_message=user_message,
            user_message_chars=len(user_message),
            history_message_count=len(messages or []),
            history_chars=history_chars,
            tool_names=[getattr(t, "__name__", str(t)) for t in tools],
            tool_count=len(tools),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            session_id=self.session_id,
            workspace_id=workspace_id,
            tier=tier,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def capture_subagent(
        self,
        skill_name: str,
        system_prompt: str,
        query: str,
    ) -> PromptSnapshot:
        snapshot = PromptSnapshot(
            agent_type=f"subagent:{skill_name}",
            system_prompt=system_prompt,
            system_prompt_chars=len(system_prompt),
            system_prompt_tokens_est=PromptSnapshot.estimate_tokens(system_prompt),
            user_message=query,
            user_message_chars=len(query),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            session_id=self.session_id,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def log_snapshot(self, snapshot: PromptSnapshot, include_full: bool = False):
        """Log snapshot at DEBUG level."""
        from ..debug_config import is_debug_enabled, EAGLE_DEBUG_PROMPTS
        if not is_debug_enabled():
            return

        if EAGLE_DEBUG_PROMPTS or include_full:
            logger.debug("PROMPT_SNAPSHOT: %s", json.dumps(snapshot.to_full_dict()))
        else:
            logger.debug("PROMPT_SNAPSHOT: %s", json.dumps(snapshot.to_dict()))

    def start_timing(self, phase: str):
        self._timings[f"{phase}_start"] = time.time()

    def end_timing(self, phase: str) -> int:
        start = self._timings.get(f"{phase}_start", 0)
        if start:
            duration_ms = int((time.time() - start) * 1000)
            self._timings[f"{phase}_ms"] = duration_ms
            return duration_ms
        return 0

    def get_timing_summary(self) -> dict:
        return {k: v for k, v in self._timings.items() if k.endswith("_ms")}
```

---

### Phase 4: Integrate into Strands Agentic Service

**File**: `server/app/strands_agentic_service.py`

#### 4.1 Add imports (after line 45)
```python
from .debug_config import is_debug_enabled, EAGLE_DEBUG_PROMPTS
from .telemetry.prompt_debugger import PromptDebugger
```

#### 4.2 Modify `sdk_query()` (around line 1574)

Before the `supervisor = Agent(...)` call, add:
```python
# Create debugger for this request
debugger = PromptDebugger(tenant_id, user_id, session_id or "")

if is_debug_enabled():
    debugger.start_timing("prompt_build")

# ... existing build_supervisor_prompt() call ...

if is_debug_enabled():
    debugger.end_timing("prompt_build")
    snapshot = debugger.capture_supervisor(
        system_prompt=system_prompt,
        user_message=prompt,
        tools=skill_tools + service_tools,
        messages=messages,
        workspace_id=resolved_workspace_id or "",
        tier=tier,
    )
    debugger.log_snapshot(snapshot)
    debugger.start_timing("api_call")

# supervisor = Agent(...) call here

# After result = supervisor(prompt):
if is_debug_enabled():
    debugger.end_timing("api_call")
    logger.debug("TIMING: %s", debugger.get_timing_summary())
```

#### 4.3 Modify `sdk_query_streaming()` (around line 1730)

Same pattern as above before/after `supervisor.stream_async()`.

#### 4.4 Modify `_make_subagent_tool()` (line 859)

Inside the `subagent_tool()` inner function:
```python
@tool(name=safe_name)
def subagent_tool(query: str) -> str:
    if is_debug_enabled():
        logger.debug(
            "SUBAGENT_CALL: skill=%s prompt_chars=%d query_chars=%d",
            skill_name, len(prompt_body), len(query)
        )
        if EAGLE_DEBUG_PROMPTS:
            logger.debug("SUBAGENT_PROMPT: %s", prompt_body[:2000])

    agent = Agent(...)  # existing code
```

---

### Phase 5: Request-Level Debug Flag

**File**: `server/app/streaming_routes.py`

#### 5.1 Modify `chat_stream()` handler (line 241)

```python
from fastapi import Query

@router.post("/api/chat/stream")
async def chat_stream(
    message: ChatMessage,
    authorization: Optional[str] = Header(None),
    debug: bool = Query(False, description="Enable debug logging for this request"),
    x_eagle_debug: Optional[str] = Header(None, alias="X-Eagle-Debug"),
):
    # Set request-level debug
    from .debug_config import set_request_debug
    if debug or x_eagle_debug == "1":
        set_request_debug(True)
        logger.info("Debug mode enabled for request")

    # ... rest of handler unchanged ...
```

**File**: `server/app/main.py`

Same pattern for `POST /api/chat` endpoint (around line 209).

---

### Phase 6: Debug API Endpoints

**File**: `server/app/main.py`

Add after line 370:

```python
# ── Debug Endpoints ─────────────────────────────────────────────────
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

@app.get("/api/debug/config")
async def get_debug_config():
    """Return current debug configuration (no auth required)."""
    from .debug_config import EAGLE_DEBUG, EAGLE_DEBUG_BOTOCORE, EAGLE_DEBUG_PROMPTS
    from .strands_agentic_service import MODEL
    return {
        "EAGLE_DEBUG": EAGLE_DEBUG,
        "EAGLE_DEBUG_BOTOCORE": EAGLE_DEBUG_BOTOCORE,
        "EAGLE_DEBUG_PROMPTS": EAGLE_DEBUG_PROMPTS,
        "model": MODEL,
        "bedrock_timeout": os.getenv("EAGLE_BEDROCK_READ_TIMEOUT", "300"),
        "dev_mode": DEV_MODE,
    }

@app.get("/api/debug/traces")
async def get_debug_traces(
    limit: int = Query(20, le=100),
    authorization: Optional[str] = Header(None),
):
    """Fetch recent traces (DEV_MODE only)."""
    if not DEV_MODE:
        raise HTTPException(403, "Debug endpoints disabled in production")

    from .telemetry.trace_store import get_traces
    user, _ = extract_user_context(authorization)
    traces = get_traces(tenant_id=user.tenant_id, limit=limit)
    return {"traces": traces}

@app.get("/api/debug/traces/{trace_id}")
async def get_debug_trace_detail(
    trace_id: str,
    date: str = Query(None),
    authorization: Optional[str] = Header(None),
):
    """Fetch single trace with full details (DEV_MODE only)."""
    if not DEV_MODE:
        raise HTTPException(403, "Debug endpoints disabled in production")

    from .telemetry.trace_store import get_trace_detail
    user, _ = extract_user_context(authorization)
    detail = get_trace_detail(user.tenant_id, trace_id, date)
    if not detail:
        raise HTTPException(404, "Trace not found")
    return detail
```

---

### Phase 7: Extend Trace Collector (Optional Enhancement)

**File**: `server/app/telemetry/trace_collector.py`

Add prompt snapshot storage:
```python
def __init__(self, ...):
    ...
    self.prompt_snapshots: list[dict] = []

def add_prompt_snapshot(self, snapshot):
    """Store prompt snapshot for post-hoc analysis."""
    self.prompt_snapshots.append(snapshot.to_dict())

def to_trace_json(self) -> list:
    trace = [...]  # existing code
    if self.prompt_snapshots:
        trace.insert(0, {"type": "prompt_snapshots", "snapshots": self.prompt_snapshots})
    return trace
```

---

## Files Summary

| File | Action | Lines to Modify |
|------|--------|-----------------|
| `server/app/debug_config.py` | **CREATE** | New file |
| `server/app/telemetry/prompt_snapshot.py` | **CREATE** | New file |
| `server/app/telemetry/prompt_debugger.py` | **CREATE** | New file |
| `server/app/main.py` | **MODIFY** | Line 127 (add debug config), ~370 (add endpoints) |
| `server/app/streaming_routes.py` | **MODIFY** | Line 241 (add debug param) |
| `server/app/strands_agentic_service.py` | **MODIFY** | Lines 45, 1574, 1730, 859 |
| `server/app/telemetry/trace_collector.py` | **MODIFY** | Add prompt_snapshots (optional) |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EAGLE_DEBUG` | `0` | Enable debug logging (prompts, tools, timing) |
| `EAGLE_DEBUG_PROMPTS` | `0` | Include full prompt text in logs (verbose) |
| `EAGLE_DEBUG_BOTOCORE` | `0` | Enable botocore DEBUG for raw API payloads |

---

## Usage

### Enable Debug Mode
```bash
EAGLE_DEBUG=1 uvicorn app.main:app --reload --port 8000
```

### Full Prompt Visibility
```bash
EAGLE_DEBUG=1 EAGLE_DEBUG_PROMPTS=1 uvicorn app.main:app --reload
```

### Per-Request Debug
```bash
# Query parameter
curl "http://localhost:8000/api/chat/stream?debug=true" -X POST -d '{"message":"Hello"}'

# Header
curl http://localhost:8000/api/chat/stream -X POST \
  -H "X-Eagle-Debug: 1" \
  -d '{"message":"Hello"}'
```

### Check Config
```bash
curl http://localhost:8000/api/debug/config
```

### View Traces
```bash
curl http://localhost:8000/api/debug/traces?limit=10
```

---

## Verification

1. **Unit test**: Run `python -m pytest server/tests/ -v -k "debug or trace"`
2. **Manual test**:
   ```bash
   EAGLE_DEBUG=1 uvicorn app.main:app --reload
   # Send a chat message via frontend or curl
   # Check terminal for PROMPT_SNAPSHOT and TIMING logs
   ```
3. **Debug endpoint test**:
   ```bash
   curl http://localhost:8000/api/debug/config
   # Should return {"EAGLE_DEBUG": true, ...}
   ```
4. **Lint check**: `ruff check server/app/`
5. **Type check**: `cd server && python -m mypy app/debug_config.py app/telemetry/prompt_snapshot.py app/telemetry/prompt_debugger.py`

---

## Reusable Components

- **Existing**: `server/app/telemetry/log_context.py` - contextvars pattern for request-scoped state
- **Existing**: `server/app/telemetry/trace_collector.py` - trace aggregation infrastructure
- **Existing**: `server/app/telemetry/local_trace_store.py` - file-based trace persistence (traces.json)
- **Pattern**: Use `is_debug_enabled()` guard to ensure zero overhead when disabled
