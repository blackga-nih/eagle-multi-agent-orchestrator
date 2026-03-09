---
type: expert-file
parent: "[[test/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, test, pytest, playwright, smoke, performance, cache, streaming, sse]
last_updated: 2026-03-09T12:00:00
---

# Test Expertise (Complete Mental Model)

> **Sources**: server/tests/*, client/tests/*, server/pytest.ini, client/playwright.config.ts

---

## Part 1: Test Inventory

### Backend Tests (pytest)

272 tests collected across 18 files (excludes real-AWS integration files). Run with `--ignore` for the 4 real-Bedrock files.

| File | Tests | Type | LLM | Mock Level |
|------|-------|------|-----|------------|
| `test_compliance_matrix.py` | 38 | Unit (pure Python) | No | None — deterministic |
| `test_new_endpoints.py` | 30 | Unit (mocked) | No | Full — mock Bedrock, DDB |
| `test_document_pipeline.py` | 26 | Unit + integration | No | Partial — mock S3, TestClient |
| `test_template_service.py` | 25 | Unit (mocked) | No | Full — mock S3 |
| `test_test_result_persistence.py` | 18 | Unit (mocked) | No | Full — mock DDB, FastAPI TestClient |
| `test_chat_endpoints.py` | 18 | Unit + integration | No | Partial — mock auth, sdk_query |
| `test_package_context_service.py` | 17 | Unit (mocked) | No | Full — mock stores |
| `test_document_service.py` | 17 | Unit (mocked) | No | Full — mock S3, DDB |
| `test_feedback_store.py` | 15 | Unit (mocked) | No | Full — mock DDB |
| `test_stream_protocol.py` | 14 | Unit (mocked) | No | None — pure dataclass/writer |
| `test_sdk_query_streaming.py` | 10 | Unit (mocked) | No | Full — mock Agent, Bedrock deps |
| `test_perf_simple_message.py` | 10 | Unit (mocked) | No | Full — mock DDB, Bedrock |
| `test_streaming_error_paths.py` | 9 | Unit (mocked) | No | Full — mock sdk_query_streaming |
| `test_canonical_package_document_flow.py` | 8 | Unit (mocked) | No | Full — mock document_service |
| `test_streaming_routes.py` | 7 | Unit (mocked) | No | Full — mock sdk_query_streaming |
| `test_knowledge_tools.py` | 5 | Unit (mocked) | No | Full — mock DDB/Bedrock KB |
| `test_chat_kb_flow.py` | 4 | Unit (mocked) | No | Partial — import-level wiring |
| `test_tools_endpoint.py` | 1 | Integration (mocked) | No | Partial — mock auth |

**Real-AWS / Real-Bedrock files (excluded from normal pytest runs):**

| File | Tests | Type | LLM | Notes |
|------|-------|------|-----|-------|
| `test_strands_eval.py` | 38 | Integration + eval | Yes | Standalone CLI, not pytest — has argparse crash at module level |
| `test_strands_poc.py` | 1 | Integration | Yes | None — real Bedrock |
| `test_strands_multi_agent.py` | 3 | Integration | Yes | None — real Bedrock |
| `test_strands_service_integration.py` | 2 | Integration | Yes | None — real Bedrock |
| `test_bedrock_bearer.py` | 1 | Integration | Yes | Real Bedrock bearer token auth test |

### Infrastructure

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Auto-persist test results to DynamoDB (TESTRUN# PK/SK) |
| `app/test_result_store.py` | DDB read/write for test run summaries + individual results |

### Frontend Tests (Playwright E2E)

| File | Tests | Timeout | Auth | Backend | Notes |
|------|-------|---------|------|---------|-------|
| `chat.spec.ts` | 4 | 90s (slow) | Yes | Real | |
| `intake.spec.ts` | 5 | 30s | Yes | Real | |
| `admin-dashboard.spec.ts` | 6 | 30s | Yes | Real | |
| `navigation.spec.ts` | 4 | 30s | Yes | Real | |
| `documents.spec.ts` | 6 | 30s | Yes | Real | |
| `document-pipeline.spec.ts` | 7 | 90s (slow) | Yes | Real | |
| `session-memory.spec.ts` | 3 | 90s (slow) | Yes | Real | |
| `workflows.spec.ts` | 5 | 30s | Yes | Real | |
| `uc-intake.spec.ts` | 1 | 90s | Yes | Real | |
| `uc-document.spec.ts` | 1 | 90s | Yes | Real | |
| `uc-far-search.spec.ts` | 1 | 90s | Yes | Real | |
| `admin-workspaces.spec.ts` | 9 | 30s | Yes | Real | |
| `admin-skills.spec.ts` | 11 | 30s | Yes | Real | |
| `admin-templates.spec.ts` | 8 | 30s | Yes | Real | |
| `keyboard-shortcuts.spec.ts` | ~10 | 30s | Yes | Real | |
| `chat-features.spec.ts` | ~13 | 30s | Yes | Real | |
| `uc-micro-purchase.spec.ts` | 3 | 90s | Yes | Real | |
| `uc-option-exercise.spec.ts` | 3 | 90s | Yes | Real | |
| `uc-contract-modification.spec.ts` | 3 | 90s | Yes | Real | |
| `uc-simple-acquisition.spec.ts` | 1 | 180s | No | Real | UC: Simple Acquisition Threshold |
| `uc-complex-acquisition.spec.ts` | 1 | 300s | No | Real | UC: $2.5M IT Services acquisition |
| `validate-sse-pipeline.spec.ts` | 1 | 180s | No | Real | SSE schema, tool pairing, card rendering |
| `validate-uc-simple-acquisition.spec.ts` | 1 | 180s | No | Real | UC quality + SSE stream validation |
| `validate-chat-v2.spec.ts` | ~2 | varies | No | Real | Chat v2 validation |
| `validate-chat-v2-long-wait.spec.ts` | ~1 | varies | No | Real | Chat v2 long-wait variant |
| `_deprecated_validate-tool-cards-chevron.spec.ts` | — | — | — | — | Deprecated — do not run |

---

## Part 2: Test Patterns

### Pattern 1: Mocked Unit Test (No AWS, No LLM)

Used in `test_perf_simple_message.py` and `test_chat_endpoints.py`.

```python
import pytest
from unittest import mock

class TestFeature:
    def test_behavior(self):
        from app.module import function
        with mock.patch("app.module.dependency") as mock_dep:
            mock_dep.return_value = {"key": "value"}
            result = function(arg1, arg2)
        assert result["key"] == "value"
        mock_dep.assert_called_once()
```

Key conventions:
- Import from `app.*` inside test methods (avoids module-level side effects)
- Use `mock.patch()` for DynamoDB `_get_table()`, Bedrock clients, S3
- Clean up caches after each test: `_cache.clear()`
- No `@pytest.mark.asyncio` needed — `pytest.ini` sets `asyncio_mode = auto`

### Pattern 2: Cache Behavior Test

Used in `test_perf_simple_message.py`.

```python
def test_cache_hit_skips_dependency(self):
    from app.module import _cache, _cache_set, function
    _cache_set(key, value)                           # Seed cache
    with mock.patch("app.module._get_table") as m:
        result = function(key)
    assert result == value
    m.assert_not_called()                            # Cache hit = no DDB
    _cache.clear()                                   # Cleanup
```

### Pattern 3: Source Inspection Test

Used for verifying code structure without running it.

```python
import inspect

def test_function_uses_pattern(self):
    from app.module import function
    source = inspect.getsource(function)
    assert "expected_call" in source
    assert "banned_call" not in source
```

### Pattern 4: Async Test

```python
@pytest.mark.asyncio
async def test_async_behavior():
    result = await async_function()
    assert result is not None
```

### Pattern 5: Regex/Pattern Test

```python
def test_regex_matches_expected():
    import re
    pattern = re.compile(r"^(hi|hello)\s*[?!.,]*$", re.IGNORECASE)
    for msg in ["hi", "hello", "Hello!", "HI?"]:
        assert pattern.match(msg), f"Should match: {msg}"
    for msg in ["hello there", "hi buddy", "What is FAR?"]:
        assert not pattern.match(msg), f"Should NOT match: {msg}"
```

### Pattern 6: Fire-and-Forget / Async Resilience

```python
@pytest.mark.asyncio
async def test_fire_and_forget_doesnt_block():
    import asyncio
    errors = []
    def failing_write():
        raise Exception("DDB down")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, failing_write)       # Should not raise
    await asyncio.sleep(0.1)                        # Let executor run
    # Test passes if no exception propagated
```

### Pattern 7: FastAPI TestClient

```python
from fastapi.testclient import TestClient
from app.main import app

def test_endpoint():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
```

### Pattern 8: Eval DynamoDB Persistence

Eval runs now auto-persist to DynamoDB alongside pytest results (trigger: "eval").

```python
# In test_strands_eval.py main(), after CloudWatch emit:
from app.test_result_store import save_test_run, save_test_result

save_test_run(run_id, {
    "timestamp": iso_ts, "total": N, "passed": P, "failed": F,
    "skipped": S, "errors": 0, "duration_s": 0,
    "pass_rate": rate, "model": MODEL_ID,
    "trigger": "eval",                     # <-- distinguishes from pytest
    "hostname": socket.gethostname(),
})

# Per-test results use eval:: prefix for nodeids:
save_test_result(run_id, f"eval::{test_name}", {
    "test_file": "test_strands_eval.py",
    "test_name": test_name,
    "status": "passed" | "failed" | "skipped",
    "duration_s": 0,
    "error": error_text,
})
```

### Pattern 9: Pure Python Unit Test (No Mocks Needed)

Used for deterministic modules like `compliance_matrix.py`.

```python
class TestGetRequirements:
    def test_threshold_logic(self):
        from app.compliance_matrix import get_requirements
        result = get_requirements(value=500_000, contract_type="FFP", method="sealed_bid")
        assert result["threshold_category"] == "SAT"
        assert "FAR 14" in str(result["applicable_far_parts"])
```

### Pattern 10: UC Test Registry Cross-Reference

Tests tagged to use cases via `.claude/specs/uc-test-registry.md`. Each UC requires coverage across 4 suites:
- **Pytest**: deterministic unit tests ($0, <60s)
- **Eval**: LLM integration tests (~$0.50/test, standalone CLI)
- **Playwright**: automated E2E browser tests ($0, 1-5min)
- **MCP Browser**: Claude-driven QA tests ($0, manual trigger)

### Pattern 11: SSE Streaming Test — `_base_patches()` + `_run_with_events()`

Used in `test_sdk_query_streaming.py` to isolate `sdk_query_streaming()` from real AWS and Agent dependencies. Patches all six entry points (build_skill_tools, _build_service_tools, build_supervisor_prompt, _to_strands_messages, fast-path helpers) then mocks `Agent` with a controlled async generator.

```python
def _base_patches():
    """Common patches to isolate sdk_query_streaming from real AWS/Agent deps."""
    return [
        patch("app.strands_agentic_service.build_skill_tools", return_value=[]),
        patch("app.strands_agentic_service._build_service_tools", return_value=[]),
        patch("app.strands_agentic_service.build_supervisor_prompt", return_value="You are EAGLE."),
        patch("app.strands_agentic_service._to_strands_messages", return_value=None),
        patch("app.strands_agentic_service._maybe_fast_path_document_generation",
              new_callable=AsyncMock, return_value=None),
        patch("app.strands_agentic_service._ensure_create_document_for_direct_request",
              new_callable=AsyncMock, return_value=None),
    ]

async def _run_with_events(events: list[dict]) -> list[dict]:
    """Run sdk_query_streaming with a mocked Agent that yields given events."""
    from app.strands_agentic_service import sdk_query_streaming
    async def fake_stream_async(prompt):
        for evt in events:
            yield evt
    mock_agent = MagicMock()
    mock_agent.stream_async = fake_stream_async
    patches = _base_patches() + [patch("app.strands_agentic_service.Agent", return_value=mock_agent)]
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        return await _collect(sdk_query_streaming(
            prompt="test query", tenant_id="test-tenant", user_id="test-user",
            tier="advanced", session_id="sess-001",
        ))
```

### Pattern 12: SSE Route Test — `_parse_sse_events()` + `_collect_stream()`

Used in `test_streaming_routes.py` and `test_streaming_error_paths.py`. Patches `sdk_query_streaming` at the route level, collects raw SSE strings, then parses them to dicts for assertion.

```python
def _parse_sse_events(raw_lines: list[str]) -> list[dict]:
    """Parse SSE strings into dicts, skipping keepalives and blanks."""
    events = []
    for line in raw_lines:
        line = line.strip()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events

async def _collect_stream(gen) -> list[str]:
    lines = []
    async for line in gen:
        lines.append(line)
    return lines
```

### Pattern 13: `CapturingQueue` — Inject into result_queue Mid-Stream

Used in `test_sdk_query_streaming.py::TestResultQueue` to inject items into the internal `asyncio.Queue` used by factory tools, without needing to mock the factory tool itself.

```python
real_queue_cls = asyncio.Queue
captured_queue = None

class CapturingQueue(real_queue_cls):
    def __init__(self, *args, **kwargs):
        nonlocal captured_queue
        super().__init__(*args, **kwargs)
        captured_queue = self

with patch("app.strands_agentic_service.asyncio.Queue", CapturingQueue):
    chunks = []
    async for chunk in sdk_query_streaming(...):
        if chunk.get("type") == "text" and captured_queue:
            await captured_queue.put(result_item)   # inject mid-stream
        chunks.append(chunk)
```

### Pattern 14: StreamEvent Schema Verification

Used in `test_stream_protocol.py`. Constructs `StreamEvent` dataclasses directly and asserts on `to_dict()` and `to_sse()` output — no HTTP layer needed.

```python
from app.stream_protocol import MultiAgentStreamWriter, StreamEvent, StreamEventType

def test_none_fields_omitted(self):
    evt = StreamEvent(type=StreamEventType.TEXT, agent_id="eagle", agent_name="EAGLE", content="hi")
    d = evt.to_dict()
    assert "tool_use" not in d        # None fields must not appear in dict
    assert "tool_result" not in d
    assert "reasoning" not in d

def test_to_sse_format(self):
    sse = evt.to_sse()
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    payload = json.loads(sse[6:].strip())
    assert payload["type"] == "text"
```

---

## Part 3: Key Coverage Gaps (as of 2026-03-09)

### SSE Streaming — RESOLVED (2026-03-09)

| Gap | Risk | Priority | Status |
|-----|------|----------|--------|
| ~~StreamEvent schema not tested~~ | Frontend breaks silently on field rename | HIGH | **RESOLVED** — `test_stream_protocol.py` (14 tests) |
| ~~sdk_query_streaming event flow not tested~~ | Regressions in text/tool_use/complete passthrough | HIGH | **RESOLVED** — `test_sdk_query_streaming.py` (10 tests) |
| ~~streaming_routes.py SSE wire format not tested~~ | Invalid SSE breaks frontend SSE consumer | HIGH | **RESOLVED** — `test_streaming_routes.py` (7 tests) |
| ~~Error paths not covered~~ | Exceptions silently swallowed or misformatted | HIGH | **RESOLVED** — `test_streaming_error_paths.py` (9 tests) |

### Fast-Path (Trivial Message Detection)

| Gap | Risk | Priority |
|-----|------|----------|
| `_TRIVIAL_RE` regex edge cases | False positives route substantive queries to fast-path | HIGH |
| `_fast_trivial_response()` error handling | Bedrock errors crash endpoint | HIGH |
| `_get_bedrock_client()` singleton | Client leak or stale credentials | MEDIUM |
| Fast-path response schema | Missing fields break frontend | MEDIUM |

### Fire-and-Forget Writes

| Gap | Risk | Priority |
|-----|------|----------|
| DDB write failure silently drops data | Lost messages, wrong costs | HIGH |
| Executor exhaustion under load | Writes queued indefinitely | MEDIUM |
| Cost calculation with zero/negative tokens | Incorrect billing | LOW |

### Cache Behavior

| Gap | Risk | Priority |
|-----|------|----------|
| Cache invalidation on create/activate workspace | Stale workspace after switch | HIGH |
| Tier/workspace isolation in skill tools cache | Wrong tools for tenant | HIGH |
| Cache TTL boundary (59.9s vs 60.1s) | Flaky timing tests | LOW |
| Admin reload clears all 6 caches (functional) | Stale data after admin action | MEDIUM |

### Prompt Behavioral

| Gap | Risk | Priority |
|-----|------|----------|
| DIRECT HANDLING actually prevents tool calls | Greetings still delegated (wasted latency) | HIGH |
| Workspace override changes supervisor prompt | Overrides silently ignored | MEDIUM |
| Prompt injection via tenant_id/user_id | Security | LOW |

### Document Export

| Gap | Risk | Priority | Status |
|-----|------|----------|--------|
| ~~DOCX checkbox ordering bug~~ | Checkboxes render as bullets | HIGH | **FIXED 2026-03-05** |
| ~~PDF numbered lists lose numbers~~ | List items render without numbering | HIGH | **FIXED 2026-03-05** |
| ~~PDF missing checkbox handling~~ | Checkboxes fall through to bullets | MEDIUM | **FIXED 2026-03-05** |
| ~~PDF missing blockquote handling~~ | Blockquotes render as plain text | MEDIUM | **FIXED 2026-03-05** |
| Export format visual quality (DOCX+PDF) | No branding, plain headers/tables | MEDIUM | **FIXED 2026-03-05** — NCI branding added |
| Version increment on re-generation | Overwritten documents | HIGH | Open |
| Naming convention compliance | Inconsistent artifact names | MEDIUM | Open |
| Export returns latest version | Wrong version downloaded | MEDIUM | Open |
| Export unit test for checkbox/blockquote output | Bugs could regress without specific assertions | MEDIUM | Open |

### Remaining Gaps (newly identified 2026-03-09)

| Gap | Risk | Priority |
|-----|------|----------|
| `test_strands_eval.py` argparse crash at module level | `pytest tests/` fails unless `--ignore` flag used | HIGH — must always exclude |
| SSE keepalive timing (20s threshold) not unit-tested | Keepalive suppression during slow model calls unverified | MEDIUM |
| tool_result dedup in streaming_routes | Duplicate tool_result events could double-render in UI | MEDIUM |
| Playwright SSE capture tests require running frontend+backend | Can't run in CI without full stack | LOW |
| `validate-sse-pipeline.spec.ts` / `validate-uc-*.spec.ts` have no auth — only work with local dev server | Fail against deployed env without auth | MEDIUM |

---

## Part 4: Running Tests

### Quick Commands

```bash
# Unit tests only (fast, no AWS) — 272 tests
cd server && python -m pytest tests/ -v \
  --ignore=tests/test_strands_eval.py \
  --ignore=tests/test_strands_poc.py \
  --ignore=tests/test_strands_multi_agent.py \
  --ignore=tests/test_strands_service_integration.py \
  --ignore=tests/test_bedrock_bearer.py

# Streaming tests only (fast, fully mocked)
cd server && python -m pytest tests/test_stream_protocol.py tests/test_sdk_query_streaming.py tests/test_streaming_routes.py tests/test_streaming_error_paths.py -v

# Specific test class
python -m pytest tests/test_perf_simple_message.py::TestWorkspaceCache -v

# Specific test method
python -m pytest tests/test_perf_simple_message.py::TestWorkspaceCache::test_cache_hit_skips_dynamodb -v

# Eval suite (custom CLI, not pytest)
python server/tests/test_strands_eval.py --model haiku --tests 16,17,18,19,20

# Playwright E2E
cd client && npx playwright test

# Specific Playwright spec
npx playwright test tests/chat.spec.ts

# SSE validation specs (require running dev server at localhost:3000)
npx playwright test tests/validate-sse-pipeline.spec.ts tests/validate-uc-simple-acquisition.spec.ts

# Lint (always run before tests)
cd server && ruff check app/
cd client && npx tsc --noEmit
```

### Validation Matrix

| Change type | Minimum validation |
|-------------|-------------------|
| Backend logic | `ruff check app/` + `pytest tests/` (with --ignore for real-AWS files) |
| Streaming / SSE change | `pytest tests/test_stream_protocol.py tests/test_sdk_query_streaming.py tests/test_streaming_routes.py tests/test_streaming_error_paths.py -v` |
| Frontend UI | `tsc --noEmit` + `playwright test` |
| CDK change | `tsc --noEmit` + `cdk synth --quiet` |
| Performance change | `pytest tests/test_perf_simple_message.py -v` |
| Cache change | `pytest tests/test_perf_simple_message.py tests/test_chat_endpoints.py -v` |
| Prompt change | `pytest tests/test_perf_simple_message.py::TestSupervisorDirectHandling -v` |
| Document service change | `pytest tests/test_document_service.py tests/test_document_pipeline.py tests/test_canonical_package_document_flow.py -v` |
| Production deploy | All of the above + docker compose |

---

## Part 5: Learnings

### patterns_that_work

- Cache tests: seed cache → call function → assert no DDB call → cleanup (discovered: 2026-03-03)
- Source inspection with `inspect.getsource()` for verifying code patterns without execution
- File-based import with `importlib.util.spec_from_file_location()` for modules outside packages (e.g. conftest.py)
- `_re.IGNORECASE` with anchored regex (`^...$`) for message classification
- `mock.patch()` context managers for clean test isolation
- Import inside test methods to avoid module-level AWS client initialization
- Pure Python tests (no mocks) for deterministic modules like `compliance_matrix.py` — 38 tests, zero AWS cost (discovered: 2026-03-04)
- Eval DDB persistence via `save_test_run(trigger="eval")` — unified admin dashboard for both suites (discovered: 2026-03-04)
- UC test registry (`.claude/specs/uc-test-registry.md`) maps use cases → tests across all 4 suites (discovered: 2026-03-04)
- Direct import from `app.compliance_matrix` in eval tests avoids relative import failure in standalone mode (discovered: 2026-03-04)
- Trigger badge pattern (eval=purple, pytest=blue) for visual suite differentiation in admin UI (discovered: 2026-03-04)
- Markdown parser elif ordering matters: checkbox patterns (`- [ ] `) must come before bullet patterns (`- `) since checkbox strings start with `- ` (discovered: 2026-03-05, component: document_export)
- Existing export tests pass after full rewrite because they assert on HTTP status/content-type/non-empty body, not on internal formatting — resilient test design (discovered: 2026-03-05)
- `_base_patches()` factory returns 6 patches as a list — unpack with individual context managers since `contextlib.ExitStack` is more verbose; must add Agent patch as index [6] (discovered: 2026-03-09, component: streaming)
- `CapturingQueue` subclass pattern lets you inject items into `asyncio.Queue` mid-stream without mocking the producer — ideal for testing result_queue drain logic (discovered: 2026-03-09, component: streaming)
- `_parse_sse_events()` helper skips keepalives and invalid JSON cleanly — reuse across all SSE route tests (discovered: 2026-03-09, component: streaming)
- `StreamEvent.to_dict()` omits None fields — test this explicitly to catch accidental field additions that would bloat SSE payload (discovered: 2026-03-09, component: stream_protocol)
- Playwright SSE capture via `page.on('response', ...)` + `response.text()` — intercepts the `/api/invoke` SSE stream and parses all `data:` lines into event objects for schema validation (discovered: 2026-03-09, component: playwright)
- test_chat_endpoints.py requires `open(..., encoding="utf-8")` on Windows — utf-8 encoding must be explicit to avoid `UnicodeDecodeError` on Windows default cp1252 (discovered: 2026-03-09, component: chat_endpoints)

### patterns_to_avoid

- Testing cache TTL with real `time.sleep()` — makes tests slow and flaky
- Asserting `result == []` when `build_skill_tools()` always appends `_compliance_matrix_tool`
- Using `asyncio.to_thread` assertions when code was changed to `invoke_async`
- Running full eval suite (`test_strands_eval.py`) during unit test passes — costs money
- Using `import tests.conftest` — `tests/` is not a Python package; use `importlib.util.spec_from_file_location()` instead
- Putting more-specific `startswith()` checks after less-specific ones in elif chains — e.g. `- [ ] ` must be checked before `- ` (discovered: 2026-03-05, component: document_export)
- Running `pytest tests/` without `--ignore=tests/test_strands_eval.py` — argparse at module level crashes collection (discovered: 2026-03-09)
- Opening files without explicit `encoding="utf-8"` on Windows — Python defaults to cp1252 and fails on Unicode content (discovered: 2026-03-09, component: chat_endpoints)
- Using `contextlib.ExitStack` for `_base_patches()` — nested `with` statements are cleaner and more explicit for 6-7 patches (discovered: 2026-03-09, component: streaming)

### common_issues

- E402 lint errors: main.py uses dotenv before imports, all imports trigger E402 (pre-existing, ignore)
- `.pyc` cache staleness: clear with `python -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"`
- Port 8000 still bound after kill on Windows: use alternate port or `taskkill //PID N //F`
- Strands `modelStreamErrorException`: transient Bedrock error, not a test bug
- `test_strands_eval.py` argparse crash: has `argparse.parse_args()` at module level — `pytest --collect-only` crashes; always use `--ignore=tests/test_strands_eval.py` (discovered: 2026-03-09)
- Windows encoding: `open()` without `encoding="utf-8"` fails on files with non-ASCII content — affects `test_chat_endpoints.py` (6 fixes applied 2026-03-09)

### tips

- Always `_cache.clear()` at end of cache tests to avoid cross-test contamination
- Use `time.perf_counter()` not `time.time()` for latency assertions (higher resolution)
- `_compliance_matrix_tool` is always appended — account for it in tool count assertions
- Mock `SKILL_AGENT_REGISTRY` and `PLUGIN_CONTENTS` together to fully isolate skill tool building
- Test results auto-persist to DDB via `conftest.py` (TESTRUN# PK/SK pattern, 90-day TTL)
- Disable persistence with `EAGLE_PERSIST_TEST_RESULTS=false` for CI or local-only runs
- API endpoints: `GET /api/admin/test-runs` (list) and `GET /api/admin/test-runs/{run_id}` (detail)
- Admin test viewer at `/admin/tests` — run history with drill-down into individual results
- `document_export.py` rewrite-safe: existing tests assert on HTTP status + content-type + non-empty body, so internal formatting changes pass without test updates
- New coverage gap: no test asserts checkbox `☐`/`☑` or blockquote content in DOCX/PDF output — add targeted export assertions to prevent regression
- SSE event ordering invariant: `complete` must always be the final event — assert `typed_events[-1]["type"] == "complete"` in ordering tests
- tool_use dedup by `toolUseId` — same ID yielded twice from Strands produces exactly one `tool_use` chunk; test explicitly to prevent double tool card render
- `validate-sse-pipeline.spec.ts` and `validate-uc-*.spec.ts` require a running dev server (no auth) — not suitable for CI without full stack; run manually for SSE contract validation
