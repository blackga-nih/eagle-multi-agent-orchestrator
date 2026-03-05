---
description: "Build test coverage for a use case across all 4 suites — pytest, eval, Playwright, MCP browser — and register in the UC test registry"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Agent
argument-hint: [UC number or description, e.g. "UC-02 micro-purchase" or "new acquisition $2.5M CT scanner"]
model: opus
---

# Test Expert - Use Case Builder

> Given a use case, scaffold and validate tests across all 4 suites, then register them in the UC test registry.

## Purpose

Ensure every use case has validated test coverage in:
1. **Pytest** — deterministic unit tests ($0, <60s)
2. **Eval** — LLM integration tests (~$0.50/test, standalone CLI)
3. **Playwright** — automated E2E browser tests ($0, 1-5min)
4. **MCP Browser** — Claude-driven QA commands ($0, manual)

## Variables

- `UC`: $ARGUMENTS

## Instructions

- **CRITICAL**: You ARE writing code. Implement all tests.
- If no `UC` is provided, STOP and ask the user which use case to build.
- Read the UC test registry first to check existing coverage.
- Read the UC definition from Jira/specs/meeting transcripts.
- Create tests that PASS validation before reporting.

---

## Workflow

### Phase 1: Identify the Use Case

1. Read the UC test registry:
   ```
   Read .claude/specs/uc-test-registry.md
   ```

2. Find the UC section and check current status (COVERED / PARTIAL / GAP).

3. If GAP or PARTIAL, identify which suites are missing.

4. Read source files to understand what the UC exercises:
   - `server/app/compliance_matrix.py` — threshold logic, FAR parts, vehicle suggestion
   - `server/app/agentic_service.py` — tool dispatch, subagent routing
   - `eagle-plugin/agents/*/agent.md` — specialist agent prompts
   - `eagle-plugin/skills/*/SKILL.md` — skill definitions

### Phase 2: Build Pytest Tests

Create or extend a `test_*.py` file with deterministic unit tests:

- Test threshold logic for the UC's dollar value
- Test compliance requirements (FAR parts, document types)
- Test vehicle suggestion for the UC's characteristics
- Mock all external dependencies (DDB, S3, Bedrock)

**Validation:**
```bash
cd server && ruff check tests/{file}.py && python -m pytest tests/{file}.py -v
```

### Phase 3: Build Eval Tests

Add test(s) to `test_strands_eval.py`:

1. Find the next available test ID:
   ```bash
   grep -c "def test_" server/tests/test_strands_eval.py
   ```

2. Add the test function following the eval pattern:
   ```python
   async def test_N_uc_description():
       """UC-XX: Description — scenario details."""
       # Use direct imports for deterministic checks
       from app.compliance_matrix import execute_operation
       result = execute_operation({...})

       # Or use Agent for LLM-backed tests
       agent = Agent(model=_model, system_prompt=system_prompt, tools=[...])
       result = agent("prompt describing the UC scenario")

       # Validate with indicators
       indicators = [check1, check2, check3, check4, check5]
       passed = sum(indicators)
       return passed >= 3  # majority pass threshold
   ```

3. Register in `TEST_REGISTRY` and `test_names` dicts.

**Validation:**
```bash
python server/tests/test_strands_eval.py --tests N
```

### Phase 4: Build Playwright Tests

Create `client/tests/uc-{slug}.spec.ts`:

```typescript
import { test, expect } from '@playwright/test';

test.describe('UC-XX: Description', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('[data-testid="chat-input"]', { timeout: 15000 });
  });

  test('scenario step 1', async ({ page }) => {
    // Type the UC scenario prompt
    const input = page.locator('[data-testid="chat-input"]');
    await input.fill('UC prompt here');
    await input.press('Enter');

    // Wait for response
    await expect(page.locator('.assistant-message')).toBeVisible({ timeout: 60000 });

    // Validate response content
    const response = await page.locator('.assistant-message').last().textContent();
    expect(response).toContain('expected keyword');
  });
});
```

**Validation:**
```bash
cd client && npx playwright test tests/uc-{slug}.spec.ts --reporter=list
```

### Phase 5: Build MCP Browser Command

Create `.claude/commands/mcp-browser/eagle-uc-{slug}-test.md`:

```markdown
---
description: "Test UC-XX: Description"
allowed-tools: [mcp__chrome-devtools__*]
---

# UC-XX: Description Test

## Steps
1. Navigate to EAGLE chat
2. Send the UC scenario prompt
3. Verify response contains expected elements
4. Check specialist delegation occurred
5. Verify document generation (if applicable)

## Pass Criteria
- [ ] Response addresses the UC scenario
- [ ] Correct specialist(s) invoked
- [ ] Expected documents listed
- [ ] No errors in console
```

### Phase 6: Register in UC Test Registry

Update `.claude/specs/uc-test-registry.md`:

1. Add test references under each suite heading
2. Update status: GAP → PARTIAL → COVERED
3. Verify all 4 suites have at least one test

### Phase 7: Validate All Tests

Run all created tests:

```bash
# Pytest
cd server && python -m pytest tests/{file}.py -v -k "uc_keyword"

# Eval (if LLM test added)
python server/tests/test_strands_eval.py --tests N

# Playwright
cd client && npx playwright test tests/uc-{slug}.spec.ts --reporter=list

# MCP Browser — manual (report command path)
```

### Phase 8: Report

```markdown
## Use Case Builder Report: UC-XX

### Use Case: {description}
### Jira: {EAGLE-N}

### Tests Created

| Suite | File | Tests | Status |
|-------|------|-------|--------|
| Pytest | `test_{file}.py` | N | PASS |
| Eval | `test_strands_eval.py` test N | 1 | PASS |
| Playwright | `uc-{slug}.spec.ts` | N | PASS |
| MCP Browser | `eagle-uc-{slug}-test.md` | 1 | CREATED |

### UC Registry Updated
- Status: {GAP → PARTIAL → COVERED}
- Tests added: {count}

### Coverage Summary
- Deterministic checks: {what's tested without LLM}
- LLM integration: {what requires Bedrock}
- UI validation: {what's checked in browser}
- Manual QA: {what MCP browser verifies}
```

---

## Suite Requirements per UC

Every use case MUST have at minimum:

| Suite | Required | What it validates |
|-------|----------|-------------------|
| Pytest | 1+ test class | Threshold logic, compliance rules, store CRUD |
| Eval | 1+ test function | End-to-end LLM orchestration with real Bedrock |
| Playwright | 1+ spec file | Frontend workflow, UI rendering, user interaction |
| MCP Browser | 1+ command | Visual QA, edge cases, real-user flow |

A UC is **COVERED** only when all 4 suites have passing tests.
A UC is **PARTIAL** when 1-3 suites have tests.
A UC is **GAP** when no tests exist.

---

## Important Notes

- **Read the registry first** — don't duplicate existing tests
- **Pytest tests must be deterministic** — no AWS calls, no LLM, pure Python
- **Eval tests use real Bedrock** — keep prompts focused, validate with indicators
- **Playwright tests need the backend running** — use `waitForSelector` with generous timeouts
- **MCP Browser commands are templates** — they run manually via `/mcp-browser:eagle-uc-*-test`
- **All results auto-persist to DynamoDB** — visible at `/admin/tests` (pytest + eval)
