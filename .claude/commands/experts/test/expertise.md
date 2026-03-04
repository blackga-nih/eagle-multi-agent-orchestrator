---
type: expert-file
parent: "[[test/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, test, pytest, playwright, smoke, performance, cache]
last_updated: 2026-03-04T18:00:00
---

# Test Expertise (Complete Mental Model)

> **Sources**: server/tests/*, client/tests/*, server/pytest.ini, client/playwright.config.ts

---

## Part 1: Test Inventory

### Backend Tests (pytest)

| File | Tests | Type | LLM | Mock Level |
|------|-------|------|-----|------------|
| `test_perf_simple_message.py` | 10 | Unit (mocked) | No | Full — mock DDB, Bedrock |
| `test_chat_endpoints.py` | ~15 | Unit + integration | No | Partial — mock auth |
| `test_test_result_persistence.py` | 18 | Unit (mocked) | No | Full — mock DDB, FastAPI TestClient |
| `test_feedback_store.py` | — | Not yet written | No | Full — mock DDB (gap) |
| `test_document_pipeline.py` | ~12 | Unit + integration | No | Partial — mock S3 |
| `test_strands_eval.py` | 38 | Integration + eval | Yes | None — real AWS |
| `test_strands_poc.py` | 1 | Integration | Yes | None — real Bedrock |
| `test_strands_multi_agent.py` | 3 | Integration | Yes | None — real Bedrock |
| `test_strands_service_integration.py` | 2 | Integration | Yes | None — real Bedrock |
| `test_bedrock_hello.py` | 4 | Integration | Yes | None — real Bedrock |
| `test_bedrock_tools.py` | 1 | Integration | Yes | None — real Bedrock |

### Infrastructure

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Auto-persist test results to DynamoDB (TESTRUN# PK/SK) |
| `app/test_result_store.py` | DDB read/write for test run summaries + individual results |

### Frontend Tests (Playwright E2E)

| File | Tests | Timeout | Auth | Backend |
|------|-------|---------|------|---------|
| `chat.spec.ts` | 4 | 90s (slow) | Yes | Real |
| `intake.spec.ts` | 5 | 30s | Yes | Real |
| `admin-dashboard.spec.ts` | 6 | 30s | Yes | Real |
| `navigation.spec.ts` | 4 | 30s | Yes | Real |
| `documents.spec.ts` | 6 | 30s | Yes | Real |
| `document-pipeline.spec.ts` | 7 | 90s (slow) | Yes | Real |
| `session-memory.spec.ts` | 3 | 90s (slow) | Yes | Real |
| `workflows.spec.ts` | 5 | 30s | Yes | Real |
| `uc-intake.spec.ts` | 1 | 90s | Yes | Real |
| `uc-document.spec.ts` | 1 | 90s | Yes | Real |
| `uc-far-search.spec.ts` | 1 | 90s | Yes | Real |

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

---

## Part 3: Key Coverage Gaps (as of 2026-03-03)

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

### Document Versioning

| Gap | Risk | Priority |
|-----|------|----------|
| Version increment on re-generation | Overwritten documents | HIGH |
| Naming convention compliance | Inconsistent artifact names | MEDIUM |
| Export returns latest version | Wrong version downloaded | MEDIUM |

### Feedback Store (NEW — 2026-03-04)

| Gap | Risk | Priority |
|-----|------|----------|
| `write_feedback()` DDB put_item failure handling | Unhandled ClientError crashes endpoint | HIGH |
| `_detect_feedback_type()` keyword ordering (first match wins) | Wrong type if multiple keyword sets match | MEDIUM |
| `POST /api/feedback` with empty `feedback_text` → 400 | Validated manually, not in pytest | MEDIUM |
| Conversation snapshot serialisation (non-serialisable types) | `json.dumps(default=str)` silently truncates data | LOW |
| CloudWatch log fetch timeout | `filter_log_events` hangs → slow feedback submit | LOW |

---

## Part 4: Running Tests

### Quick Commands

```bash
# Unit tests only (fast, no AWS)
cd server && python -m pytest tests/test_perf_simple_message.py tests/test_chat_endpoints.py -v

# All pytest tests
cd server && python -m pytest tests/ -v

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

# Lint (always run before tests)
cd server && ruff check app/
cd client && npx tsc --noEmit
```

### Validation Matrix

| Change type | Minimum validation |
|-------------|-------------------|
| Backend logic | `ruff check app/` + `pytest tests/` |
| Frontend UI | `tsc --noEmit` + `playwright test` |
| CDK change | `tsc --noEmit` + `cdk synth --quiet` |
| Performance change | `pytest tests/test_perf_simple_message.py -v` |
| Cache change | `pytest tests/test_perf_simple_message.py tests/test_chat_endpoints.py -v` |
| Prompt change | `pytest tests/test_perf_simple_message.py::TestSupervisorDirectHandling -v` |
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
- **Bowser QA agent for slash-command intercept testing**: send `/feedback <text>`, assert no AI response rendered, assert confirmation banner present — reliable for "bypass AI" flow validation (discovered: 2026-03-04, component: feedback-slash-command)
- **DynamoDB smoke test via AWS CLI**: `aws dynamodb query --key-condition-expression "PK = :pk"` with dev-tenant PK to verify real writes end-to-end without a pytest fixture (discovered: 2026-03-04)
- **Next.js proxy route pattern** (`client/app/api/<name>/route.ts`): POST handler forwards headers + body to `FASTAPI_URL`, returns `NextResponse.json(data, { status })` — consistent with health/invoke routes

### patterns_to_avoid

- Testing cache TTL with real `time.sleep()` — makes tests slow and flaky
- Asserting `result == []` when `build_skill_tools()` always appends `_compliance_matrix_tool`
- Using `asyncio.to_thread` assertions when code was changed to `invoke_async`
- Running full eval suite (`test_strands_eval.py`) during unit test passes — costs money
- Using `import tests.conftest` — `tests/` is not a Python package; use `importlib.util.spec_from_file_location()` instead

### common_issues

- E402 lint errors: main.py uses dotenv before imports, all imports trigger E402 (pre-existing, ignore)
- `.pyc` cache staleness: clear with `python -c "import shutil, pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"`
- Port 8000 still bound after kill on Windows: use alternate port or `taskkill //PID N //F`
- Strands `modelStreamErrorException`: transient Bedrock error, not a test bug
- **Next.js dev server hangs after force-kill on Windows**: `.next/trace` file stays locked; solution is to kill all node processes, wait for lock release, then restart — `npm run dev` via PowerShell `Start-Process` is more reliable than MINGW64 background `&`
- **`idb` package missing from node_modules**: was gitignored or never installed; `npm install idb --save` + server restart resolves the "Module not found" 500 error
- **DynamoDB tenant_id mismatch in dev mode**: dev mode uses `DEV_TENANT_ID=dev-tenant` (not `nci`); query with `PK = "FEEDBACK#dev-tenant"` to find records
- **AWS SSO token expiry mid-session**: `botocore.exceptions.TokenRetrievalError` → `aws sso login --profile eagle` to refresh; non-fatal for frontend but fails DDB writes

### tips

- Always `_cache.clear()` at end of cache tests to avoid cross-test contamination
- Use `time.perf_counter()` not `time.time()` for latency assertions (higher resolution)
- `_compliance_matrix_tool` is always appended — account for it in tool count assertions
- Mock `SKILL_AGENT_REGISTRY` and `PLUGIN_CONTENTS` together to fully isolate skill tool building
- Test results auto-persist to DDB via `conftest.py` (TESTRUN# PK/SK pattern, 90-day TTL)
- Disable persistence with `EAGLE_PERSIST_TEST_RESULTS=false` for CI or local-only runs
- API endpoints: `GET /api/admin/test-runs` (list) and `GET /api/admin/test-runs/{run_id}` (detail)
- Admin test viewer at `/admin/tests` — run history with drill-down into individual results
- **Slash-command intercept testing**: use bowser QA agent, not pytest — browser-level assertion of "no AI response rendered + banner visible" is the right layer for UI-intercept verification
- **Feedback store unit test template**: mock `_get_table()` → `put_item`, call `write_feedback(...)`, assert `put_item.call_args` contains correct PK/SK/feedback_type; test `_detect_feedback_type` directly with keyword strings
- **DynamoDB write verification without a test**: `aws dynamodb query --key-condition-expression "PK = :pk" --expression-attribute-values '{":pk":{"S":"FEEDBACK#dev-tenant"}}'` is the fastest smoke check
- **`trailingSlash: true` + Next.js API routes**: POST to `/api/foo` gets 308-redirected to `/api/foo/`; browser `fetch` follows automatically, but `curl` requires `-L`; Next.js App Router route files handle both with/without slash at runtime
