---
description: "Add a new test to the EAGLE eval suite — scaffolds function, registers in all 8 locations, validates"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [test description, tier, and what to validate]
model: opus
---

# Eval Expert - Add New Test

> Scaffold a new test function, register it in all 8 required locations across 4 files, and validate.

## Purpose

Automate the full SOP for adding a new test to `server/tests/test_eagle_sdk_eval.py`. A single missed registration causes silent data loss (test runs but results vanish from dashboards or CloudWatch). This command handles every touchpoint.

## Variables

- `TASK`: $ARGUMENTS

## Instructions

- **CRITICAL**: You ARE writing code. Implement the full test and all registrations.
- If no `TASK` is provided, STOP and ask the user what the test should validate.
- Read `expertise.md` Part 6 (Registration Mappings) and Part 7 (SOP) for exact locations and formats.
- Follow naming conventions strictly: function `test_N_snake_name()`, result key `N_snake_name`.
- Every test that creates AWS resources MUST include cleanup in a try/except block.
- AWS tool tests MUST include boto3 independent confirmation.

---

## Workflow

### Phase 1: Load Context and Determine Test ID

1. Read expertise context:
   ```
   Read .claude/commands/experts/eval/expertise.md
   ```

2. Find the current highest test ID:
   ```
   Grep pattern="^\s+\d+:" path="server/tests/test_eagle_sdk_eval.py" — look at TEST_REGISTRY
   ```

3. Set `N` = highest ID + 1.

4. Parse the TASK to determine:
   - **Tier**: SDK Pattern (uses `query()`), Skill Validation (uses `SKILL_CONSTANTS`), or AWS Tool Integration (uses `execute_tool()`)
   - **Category**: `core`, `traces`, `agents`, `tools`, `skills`, `workflow`, or `aws`
   - **Name**: snake_case for code, Title Case for dashboards
   - **AWS services involved** (if any)

5. Print the plan:
   ```
   Test N: {Title}
   Tier: {tier}
   Category: {category}
   Result key: N_{snake_name}
   Function: test_N_{snake_name}
   ```

### Phase 2: Write the Test Function

1. Read `server/tests/test_eagle_sdk_eval.py` to find the insertion point (before the `# ── Main` section).

2. Read `server/app/agentic_service.py` if the test exercises an AWS tool — understand the handler's params and return shape.

3. Write the test function using the appropriate tier template:

   **SDK Pattern (Tier 1):**
   ```python
   async def test_N_snake_name():
       """Brief description."""
       print(f"\n{'='*60}")
       print("Test N: Title")
       print(f"{'='*60}")
       passed = True
       try:
           from claude_agent_sdk import query
           # ... query() calls with assertions ...
       except Exception as e:
           print(f"\n  EXCEPTION: {e}")
           import traceback; traceback.print_exc()
           passed = False
       print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
       return passed
   ```

   **Skill Validation (Tier 2):**
   ```python
   async def test_N_snake_name():
       """Brief description."""
       print(f"\n{'='*60}")
       print("Test N: Title")
       print(f"{'='*60}")
       passed = True
       try:
           from eagle_skill_constants import SKILL_CONSTANTS
           content = SKILL_CONSTANTS["skill-key"]
           tenant_context = "You are EAGLE... Tenant: test-tenant, Tier: premium"
           system_prompt = tenant_context + "\n\n" + content
           # ... query() with system_prompt, check skill indicators ...
       except Exception as e:
           print(f"\n  EXCEPTION: {e}")
           import traceback; traceback.print_exc()
           passed = False
       print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
       return passed
   ```

   **AWS Tool Integration (Tier 3):**
   ```python
   async def test_N_snake_name():
       """Brief description."""
       print(f"\n{'='*60}")
       print("Test N: Title")
       print(f"{'='*60}")
       passed = True
       tenant_id = "test-tenant"
       session_id = "test-session-001"
       try:
           # Step 1: Call execute_tool()
           print("\n  Step 1: ...")
           result = json.loads(execute_tool("tool_name", {params}, session_id))
           assert result.get("status") == "success"
           print(f"    -> OK")

           # Step 2: boto3 independent confirmation
           print("\n  Step 2: boto3 confirm...")
           client = boto3.client("service", region_name="us-east-1")
           # ... verify ...
           print(f"    -> Confirmed")

           # Cleanup
           try:
               # ... delete test artifacts ...
               print("    -> Cleanup OK")
           except Exception:
               print("    (cleanup failed, non-fatal)")
       except Exception as e:
           print(f"\n  EXCEPTION: {e}")
           import traceback; traceback.print_exc()
           passed = False
       print(f"\n  Result: {'PASS' if passed else 'FAIL'}")
       return passed
   ```

4. Insert the function using Edit before the `# ── Main` marker.

### Phase 3: Register in Backend (5 edits in server/tests/test_eagle_sdk_eval.py)

All 5 edits target `server/tests/test_eagle_sdk_eval.py`. Make them in order:

**3a. `TEST_REGISTRY`** — find `TEST_REGISTRY = {` in `_run_test()` (~line 2319). Add:
```python
N: ("N_snake_name", test_N_snake_name),
```

**3b. `test_names`** — find `test_names = {` in `emit_to_cloudwatch()` (~line 2252). Add:
```python
N: "N_snake_name",
```

**3c. `result_key`** — find `result_key = {` in `main()` (~line 2479). Add:
```python
N: "N_snake_name",
```

**3d. Summary printout** — find the appropriate tier section in `main()` summary. Add:
```python
print(f"  Test N  {'PASS' if results.get('N_snake_name') else 'FAIL':6s}  Title")
```

**3e. `selected_tests` default range** — update `range(1, M)` to `range(1, N+1)`.

### Phase 4: Register in Frontend (3 files, 4 edits)

**4a. `test_results_dashboard.html` — `TEST_DEFS`** (~line 123):
```javascript
{ id: N, name: "Title", desc: "One-line description", category: "category" },
```

**4b. `test_results_dashboard.html` — readiness panel** (~line 305):
```javascript
{ label: "Descriptive readiness label", ready: results[N]?.status === 'pass' },
```

**4c. `client/app/admin/tests/page.tsx` — `TEST_NAMES`** (~line 28):
```typescript
'N': 'Title',
```

**4d. `client/app/admin/eval/page.tsx` — `SKILL_TEST_MAP`** (~line 446):
Only if the test maps to a tool/skill key:
```typescript
tool_key: [N],
```

### Phase 5: Validate

Run these commands in sequence:

1. **Syntax check**:
   ```bash
   python -c "import py_compile; py_compile.compile('server/tests/test_eagle_sdk_eval.py', doraise=True)"
   ```

2. **Verify registrations** — grep for the new test ID in all 4 files:
   ```bash
   grep -n "N_snake_name\|id: N\|'N':" server/tests/test_eagle_sdk_eval.py test_results_dashboard.html client/app/admin/tests/page.tsx client/app/admin/eval/page.tsx
   ```

3. **Count registrations** — must find 8 (or 7 if SKILL_TEST_MAP not applicable):
   ```
   Expected: TEST_REGISTRY, test_names, result_key, summary print, TEST_DEFS, readiness, TEST_NAMES, SKILL_TEST_MAP
   ```

4. **Run the test** (if AWS credentials available):
   ```bash
   python server/tests/test_eagle_sdk_eval.py --model haiku --tests N
   ```

5. **Verify trace output**:
   ```bash
   python -c "import json; d=json.load(open('trace_logs.json')); print('Test N:', 'N' in str(d.get('results',{}).keys()))"
   ```

### Phase 6: Report

Print a summary:

```
New Test Added

  Test ID:    N
  Function:   test_N_snake_name()
  Result Key: N_snake_name
  Tier:       {tier}
  Category:   {category}
  Title:      {Title}

  Registrations: 8/8 complete
    [x] TEST_REGISTRY        (server/tests/test_eagle_sdk_eval.py)
    [x] test_names            (server/tests/test_eagle_sdk_eval.py)
    [x] result_key            (server/tests/test_eagle_sdk_eval.py)
    [x] summary printout      (server/tests/test_eagle_sdk_eval.py)
    [x] selected_tests range  (server/tests/test_eagle_sdk_eval.py)
    [x] TEST_DEFS             (test_results_dashboard.html)
    [x] readiness panel       (test_results_dashboard.html)
    [x] TEST_NAMES            (tests/page.tsx)
    [x] SKILL_TEST_MAP        (eval/page.tsx) — {added / N/A}

  Syntax Check: PASS
  Test Run:     {PASS / SKIP — not run}
```

---

## Important Notes

- **Never skip registrations** — a missing entry causes silent data loss
- **Line numbers are approximate** — always search for the variable name, don't rely on exact line numbers
- **Cleanup is mandatory** — any test creating S3 objects, DDB items, or other resources must delete them
- **boto3 confirmation is required** for all AWS tool tests (tier 3)
- **Keep tests idempotent** — use unique keys with UUID to avoid collisions
- **Test 2 is special** — it receives session_id from Test 1 (None in registry, handled in _run_test)
- Update `expertise.md` Part 4/5 if the new test covers a new tool or pattern not yet documented
