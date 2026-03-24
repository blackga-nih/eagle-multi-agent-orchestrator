# Agentic CI/CD E2E Testing Overhaul — Implementation Plan

**Artifact**: `20260310-120000-plan-agentic-e2e-cicd-v1.md`
**Date**: 2026-03-10
**Sprint**: MVP-1 → MVP-2 bridge
**Owner**: `assignee:greg` + `assignee:fullstack`

---

## Executive Summary

- **Gap**: All 26 Playwright specs in `client/tests/` are static scripts. They hard-code selectors, poll for keywords, and cannot semantically validate AI responses — `bodyText.includes('FAR')` is not meaningful coverage for a $750K acquisition assistant.
- **Solution**: Three-phase overhaul — (1) proper auth state caching with token expiry management, (2) a JSON scenario runner + Claude skill that drives `agent-browser` through acquisition use cases and semantically validates AI output, (3) a new `agent-validate.yml` CI workflow inserting an **L3.5 Agentic Validation** gate with matrix UC execution, S3 video artifacts, and PR comment reporting.
- **Result**: PRs touching any acquisition flow are automatically gated by a 10–15 min agentic walk that records video, validates FAR citations + thresholds semantically, and posts a pass/fail table as a PR comment — not just a string-match check.

---

## Architecture

```
PR pushed / main merged
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  .github/workflows/agent-validate.yml                            │
│                                                                  │
│  ┌─────────────┐   ┌────────────────────────────────────────┐   │
│  │ auth-setup  │──▶│  uc-validate (matrix: 3 scenarios)     │   │
│  │  (job 1)    │   │  ┌──────────────┐  ┌────────────────┐  │   │
│  └─────────────┘   │  │ smoke        │  │ uc-simple-acq  │  │   │
│         │          │  ├──────────────┤  ├────────────────┤  │   │
│  auth state to S3  │  │ uc-complex   │  │ uc-doc-gen     │  │   │
│  cache key: sha    │  └──────────────┘  └────────────────┘  │   │
│                    └────────────────────────────────────────┘   │
│                                  │                               │
│                    ┌─────────────▼──────────────┐               │
│                    │  report (job 3)             │               │
│                    │  - PR comment (pass/fail)   │               │
│                    │  - S3 video upload          │               │
│                    │  - screenshot gallery       │               │
│                    └────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────┘

Agent Browser Skill Layer:
  .claude/skills/agent-e2e-test/SKILL.md
    └── agent-browser CLI (open → snapshot → interact → assert → record)
         └── tests/.auth/user.json  (Cognito session, reused across all scenarios)

Scenario Layer:
  client/tests/scenarios/*.json
    ├── smoke.json
    ├── uc-simple-acquisition.json
    ├── uc-complex-acquisition.json
    └── uc-document-generation.json
```

---

## Validation Ladder — Updated

| Level | Name | Command | Required for |
|-------|------|---------|--------------|
| L1 | Lint | `ruff check app/ + tsc --noEmit` | All changes |
| L2 | Unit Tests | `pytest tests/ -v` | Backend logic |
| L3 | E2E Tests | `playwright test` | Frontend UI (static) |
| **L3.5** | **Agentic Validation** | `just agent-test-all` | **Acquisition flows** |
| L4 | CDK Synth | `cdk synth --quiet` | CDK changes |
| L5 | Integration | `docker compose up --build` | Cross-stack |
| L6 | Eval Suite | `pytest test_eagle_sdk_eval.py` | Production deploy |

**Updated change-type matrix:**

| Change Type | Minimum Level |
|-------------|---------------|
| Typo / copy | L1 |
| Backend logic | L1 + L2 |
| Frontend UI | L1 + L3 |
| **Acquisition flow** | **L1 + L3 + L3.5** |
| CDK change | L1 + L4 |
| Cross-stack | L1 – L5 |
| Production deploy | L1 – L6 |

---

## Phase 1: Auth State Cache & Session Management

**Goal**: Replace the fragile dual-mode `global-setup.ts` hack with a dedicated auth project that manages token expiry.

### Files to create/modify

**1a. `client/tests/auth.setup.ts`** (new — replaces global-setup.ts)
```typescript
import { test as setup, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const AUTH_FILE = path.join(__dirname, '.auth/user.json');
const META_FILE = path.join(__dirname, '.auth/user.json.meta');
const TOKEN_TTL_MS = 50 * 60 * 1000; // 50 minutes (Cognito tokens expire at 60)

setup('authenticate', async ({ page }) => {
  // Check if we have a valid cached state
  if (fs.existsSync(META_FILE)) {
    const meta = JSON.parse(fs.readFileSync(META_FILE, 'utf8'));
    const age = Date.now() - meta.savedAt;
    if (age < TOKEN_TTL_MS) {
      console.log(`[auth] Reusing cached state (${Math.round(age / 1000)}s old)`);
      return;
    }
    console.log('[auth] Cached state expired, re-authenticating');
  }

  const baseURL = process.env.BASE_URL || 'http://localhost:3000';
  const email = process.env.TEST_EMAIL ?? 'testuser@example.com';
  const password = process.env.TEST_PASSWORD ?? 'EagleTest2024!';

  await page.goto(`${baseURL}/login`);

  const onLoginPage = await Promise.race([
    page.waitForSelector('#login-email', { timeout: 8000 }).then(() => true),
    page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 8000 }).then(() => false),
  ]).catch(() => false);

  if (onLoginPage) {
    await page.fill('#login-email', email);
    await page.fill('#login-password', password);
    await page.click('button[type="submit"]');
    await page.waitForURL(url => !url.pathname.startsWith('/login'), { timeout: 30000 });
  }

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });
  await page.context().storageState({ path: AUTH_FILE });

  // Write metadata for expiry check
  fs.writeFileSync(META_FILE, JSON.stringify({
    savedAt: Date.now(),
    baseURL,
    email,
    env: process.env.NODE_ENV || 'development',
  }));

  console.log('[auth] Auth state saved to', AUTH_FILE);
});
```

**1b. `client/playwright.config.ts`** — add `auth.setup.ts` as a named project:
```typescript
projects: [
  {
    name: 'setup',
    testMatch: /auth\.setup\.ts/,
    use: { storageState: undefined },
  },
  // ... existing browser projects, all depending on 'setup'
]
```

**1c. `client/tests/.auth/`** — add to `.gitignore`:
```
client/tests/.auth/
```
But cache in CI using `actions/cache` keyed by `${{ hashFiles('client/package-lock.json') }}-auth`.

### Validation
```bash
cd client && npx playwright test --project=setup
# → Should create tests/.auth/user.json and tests/.auth/user.json.meta
```

---

## Phase 2: Scenario Runner + Agent Skill

**Goal**: A JSON-driven scenario format + Claude skill that uses `agent-browser` to walk through acquisition use cases and semantically validates responses.

### 2a. Scenario Spec Format

**`client/tests/scenarios/smoke.json`**
```json
{
  "id": "smoke",
  "description": "Smoke: load 5 key pages, verify no JS errors",
  "timeoutMs": 60000,
  "steps": [
    { "action": "goto", "path": "/" },
    { "action": "assertNoConsoleErrors" },
    { "action": "screenshot", "name": "home" },
    { "action": "goto", "path": "/chat" },
    { "action": "waitForSelector", "selector": "[data-testid='chat-input']" },
    { "action": "screenshot", "name": "chat" },
    { "action": "goto", "path": "/admin" },
    { "action": "assertNoConsoleErrors" },
    { "action": "screenshot", "name": "admin" }
  ]
}
```

**`client/tests/scenarios/uc-simple-acquisition.json`**
```json
{
  "id": "uc-simple-acquisition",
  "description": "UC-1: COR enters $750K IT services requirement",
  "timeoutMs": 180000,
  "steps": [
    { "action": "goto", "path": "/chat" },
    { "action": "waitForSelector", "selector": "[data-testid='chat-input']" },
    { "action": "screenshot", "name": "01-initial" },
    {
      "action": "fill",
      "selector": "[data-testid='chat-input']",
      "value": "I need to procure IT services for NCI. The requirement is for a full-stack development team for 12 months. Total estimated cost is $750,000."
    },
    { "action": "submit" },
    {
      "action": "waitForResponse",
      "timeoutMs": 120000,
      "selector": "[data-testid='message-list'] [data-role='assistant']:last-child"
    },
    { "action": "screenshot", "name": "02-response" },
    {
      "action": "assertSemanticContent",
      "description": "Response should identify acquisition method and request missing details",
      "requiredConcepts": ["acquisition method", "simplified acquisition", "FAR", "statement of work"],
      "forbiddenPhrases": ["I cannot", "I don't know", "error"]
    }
  ]
}
```

**`client/tests/scenarios/uc-document-generation.json`**
```json
{
  "id": "uc-document-generation",
  "description": "UC-1 full: generate SOW + IGCE, verify download",
  "timeoutMs": 300000,
  "steps": [
    { "action": "goto", "path": "/chat" },
    { "action": "fill", "selector": "[data-testid='chat-input']", "value": "Generate an SOW and IGCE for a $750K IT services contract, 12 months, simplified acquisition threshold." },
    { "action": "submit" },
    { "action": "waitForResponse", "timeoutMs": 180000, "selector": "[data-testid='message-list'] [data-role='assistant']:last-child" },
    { "action": "screenshot", "name": "response" },
    { "action": "waitForSelector", "selector": "[data-testid='download-btn']", "timeoutMs": 30000 },
    { "action": "click", "selector": "[data-testid='download-btn']" },
    { "action": "screenshot", "name": "download-triggered" },
    { "action": "assertSemanticContent", "requiredConcepts": ["SOW", "IGCE", "statement of work", "independent government"] }
  ]
}
```

### 2b. Agent Skill

**`.claude/skills/agent-e2e-test/SKILL.md`**

```markdown
---
name: agent-e2e-test
description: Agentic E2E test runner — loads auth state, walks through a scenario spec using agent-browser, records video, validates responses semantically
argument-hint: <scenario-id> [--headed] [--base-url=<url>]
model: claude-sonnet-4-6
---

# Agent E2E Test Runner

Run an agentic end-to-end test scenario against the EAGLE application.

## Arguments

- `$SCENARIO_ID`: scenario ID from `client/tests/scenarios/*.json` (e.g., `uc-simple-acquisition`)
- `--headed`: show browser window (default: headless)
- `--base-url=<url>`: override base URL (default: http://localhost:3000)

## Workflow

1. Load auth state from `client/tests/.auth/user.json`
   - If missing or expired (>50 min), run `npx playwright test --project=setup` first
2. Load scenario from `client/tests/scenarios/$SCENARIO_ID.json`
3. Start video recording: `agent-browser --session=$SCENARIO_ID record start ./test-results/videos/$SCENARIO_ID.webm`
4. Load auth state: `agent-browser --session=$SCENARIO_ID state load client/tests/.auth/user.json`
5. Execute each step in order:
   - `goto` → `agent-browser --session=$SCENARIO_ID open <baseURL><path>`
   - `waitForSelector` → `agent-browser --session=$SCENARIO_ID wait <selector>`
   - `fill` → `agent-browser --session=$SCENARIO_ID fill <selector> <value>`
   - `submit` → `agent-browser --session=$SCENARIO_ID press Enter` OR click submit btn
   - `waitForResponse` → poll with `agent-browser --session=$SCENARIO_ID wait --text` until stable
   - `screenshot` → `agent-browser --session=$SCENARIO_ID screenshot ./test-results/screenshots/$SCENARIO_ID-<name>.png`
   - `assertSemanticContent` → extract text, evaluate against requiredConcepts using Claude
   - `assertNoConsoleErrors` → `agent-browser --session=$SCENARIO_ID errors`
6. Stop recording: `agent-browser --session=$SCENARIO_ID record stop`
7. Close session: `agent-browser --session=$SCENARIO_ID close`
8. Report: print pass/fail table with step results + artifact paths

## Output Format

```
## Scenario: uc-simple-acquisition — PASS (14.2s)

| Step | Action | Result | Notes |
|------|--------|--------|-------|
| 1 | goto /chat | PASS | 200 OK |
| 2 | waitForSelector chat-input | PASS | found in 340ms |
| 3 | fill + submit | PASS | |
| 4 | waitForResponse | PASS | 8.4s |
| 5 | assertSemanticContent | PASS | found: acquisition method, FAR 13, SOW |
| 6 | screenshot | PASS | saved to test-results/... |

Video: test-results/videos/uc-simple-acquisition.webm
Screenshots: test-results/screenshots/uc-simple-acquisition-*.png
```
```

### 2c. Justfile additions

Add to `Justfile` (or create if missing):
```makefile
# ── Agentic E2E Testing ──────────────────────────────────────────

# Run smoke scenario
agent-smoke:
    claude -p "/agent-e2e-test smoke"

# Run single UC scenario
agent-test scenario:
    claude -p "/agent-e2e-test {{scenario}}"

# Run all scenarios in parallel
agent-test-all:
    claude -p "/agent-e2e-test smoke" &
    claude -p "/agent-e2e-test uc-simple-acquisition" &
    claude -p "/agent-e2e-test uc-complex-acquisition" &
    wait
    echo "All scenarios complete"

# Record a new scenario as video reference (headed, for demo)
agent-record scenario:
    claude -p "/agent-e2e-test {{scenario}} --headed"

# Auth refresh
agent-auth-refresh:
    cd client && npx playwright test --project=setup
```

---

## Phase 3: CI/CD Integration

### 3a. New workflow: `.github/workflows/agent-validate.yml`

```yaml
name: Agentic E2E Validation (L3.5)

on:
  pull_request:
    branches: [main]
    paths:
      - 'client/**'
      - 'server/app/**'
      - 'eagle-plugin/**'
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      scenario:
        description: 'Scenario to run (leave blank for all)'
        required: false
        default: ''

env:
  BASE_URL: ${{ secrets.STAGE_BASE_URL || 'http://localhost:3000' }}
  AWS_REGION: us-east-1

jobs:
  auth-setup:
    name: Auth Setup
    runs-on: [self-hosted, eagle-github-runner]
    outputs:
      auth-cache-key: ${{ steps.cache-key.outputs.key }}
    steps:
      - uses: actions/checkout@v4

      - name: Set cache key
        id: cache-key
        run: echo "key=auth-state-${{ github.sha }}" >> $GITHUB_OUTPUT

      - name: Restore auth cache
        id: auth-cache
        uses: actions/cache@v4
        with:
          path: client/tests/.auth/
          key: ${{ steps.cache-key.outputs.key }}
          restore-keys: auth-state-

      - name: Install Playwright
        if: steps.auth-cache.outputs.cache-hit != 'true'
        run: cd client && npm ci && npx playwright install chromium

      - name: Run auth setup
        if: steps.auth-cache.outputs.cache-hit != 'true'
        env:
          TEST_EMAIL: ${{ secrets.EAGLE_TEST_EMAIL }}
          TEST_PASSWORD: ${{ secrets.EAGLE_TEST_PASSWORD }}
        run: cd client && npx playwright test --project=setup

      - name: Cache auth state
        uses: actions/cache/save@v4
        if: steps.auth-cache.outputs.cache-hit != 'true'
        with:
          path: client/tests/.auth/
          key: ${{ steps.cache-key.outputs.key }}

  uc-validate:
    name: Validate (${{ matrix.scenario }})
    runs-on: [self-hosted, eagle-github-runner]
    needs: [auth-setup]
    strategy:
      fail-fast: false
      matrix:
        scenario:
          - smoke
          - uc-simple-acquisition
          - uc-document-generation
    steps:
      - uses: actions/checkout@v4

      - name: Restore auth state
        uses: actions/cache/restore@v4
        with:
          path: client/tests/.auth/
          key: ${{ needs.auth-setup.outputs.auth-cache-key }}

      - name: Install dependencies
        run: cd client && npm ci && npx playwright install chromium

      - name: Run scenario
        id: run-scenario
        env:
          BASE_URL: ${{ env.BASE_URL }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          mkdir -p test-results/videos test-results/screenshots
          npx tsx client/tests/agent-runner.ts --scenario=${{ matrix.scenario }} \
            --base-url=${{ env.BASE_URL }} \
            --output=test-results/${{ matrix.scenario }}-result.json
        continue-on-error: true

      - name: Upload artifacts to S3
        env:
          AWS_ROLE_ARN: ${{ secrets.EAGLE_DEPLOY_ROLE_ARN }}
        run: |
          aws s3 cp test-results/ \
            s3://eagle-test-artifacts/${{ github.sha }}/${{ matrix.scenario }}/ \
            --recursive --include "*.png" --include "*.webm" --include "*.json"

      - name: Upload test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: ${{ matrix.scenario }}-results
          path: test-results/${{ matrix.scenario }}-*
          retention-days: 14

  report:
    name: Post PR Report
    runs-on: [self-hosted, eagle-github-runner]
    needs: [uc-validate]
    if: always() && github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4

      - name: Download all artifacts
        uses: actions/download-artifact@v4
        with:
          path: test-results/

      - name: Generate PR comment
        id: generate-comment
        run: |
          python3 scripts/generate-test-report.py \
            --results-dir test-results/ \
            --sha ${{ github.sha }} \
            --s3-base "https://eagle-test-artifacts.s3.amazonaws.com/${{ github.sha }}" \
            > /tmp/pr-comment.md

      - name: Post PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const body = fs.readFileSync('/tmp/pr-comment.md', 'utf8');
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body,
            });
```

### 3b. PR comment format (`scripts/generate-test-report.py`)

Output format:
```markdown
## 🤖 Agentic E2E Validation — L3.5

| Scenario | Status | Duration | Video |
|----------|--------|----------|-------|
| smoke | ✅ PASS | 12s | [watch](https://...) |
| uc-simple-acquisition | ✅ PASS | 43s | [watch](https://...) |
| uc-document-generation | ❌ FAIL | 180s (timeout) | [watch](https://...) |

**Failed step**: `waitForResponse` timed out after 180s — no response from agent

<details>
<summary>Screenshots</summary>

![step-01](https://eagle-test-artifacts.s3.../01-initial.png)
![step-02](https://eagle-test-artifacts.s3.../02-response.png)

</details>
```

### 3c. GitHub Actions secrets required

Add to repo settings → Secrets:
| Secret | Value |
|--------|-------|
| `EAGLE_TEST_EMAIL` | Test user email for Cognito |
| `EAGLE_TEST_PASSWORD` | Test user password |
| `STAGE_BASE_URL` | ECS ALB URL for stage environment |
| `EAGLE_TEST_ARTIFACTS_BUCKET` | S3 bucket name for artifacts |

---

## New Files Summary

| File | Action | Phase |
|------|--------|-------|
| `client/tests/auth.setup.ts` | Create | 1 |
| `client/tests/.auth/.gitkeep` | Create (gitignore the dir itself) | 1 |
| `client/tests/scenarios/smoke.json` | Create | 2 |
| `client/tests/scenarios/uc-simple-acquisition.json` | Create | 2 |
| `client/tests/scenarios/uc-complex-acquisition.json` | Create | 2 |
| `client/tests/scenarios/uc-document-generation.json` | Create | 2 |
| `client/tests/agent-runner.ts` | Create | 2 |
| `.claude/skills/agent-e2e-test/SKILL.md` | Create | 2 |
| `scripts/generate-test-report.py` | Create | 3 |
| `.github/workflows/agent-validate.yml` | Create | 3 |
| `Justfile` | Modify (add 5 commands) | 3 |
| `CLAUDE.md` | Modify (add L3.5 to ladder) | 3 |
| `client/playwright.config.ts` | Modify (add auth.setup.ts project) | 1 |
| `docs/architecture/diagrams/excalidraw/20260226-161925-arch-validation-just-workflow-v1.excalidraw.md` | Modify (add L3.5 node) | 3 |

---

## Validation Commands (per phase)

```bash
# Phase 1: Auth state works
cd client && npx playwright test --project=setup
# → creates client/tests/.auth/user.json + user.json.meta

# Phase 2: Single scenario runs locally
just agent-test smoke
# → prints pass/fail table, creates test-results/videos/smoke.webm

# Phase 3: Full CI workflow (dry run)
act pull_request -W .github/workflows/agent-validate.yml --dry-run
# → shows job matrix execution plan
```

---

## Open Questions / Risks

| # | Question | Risk | Mitigation |
|---|----------|------|-----------|
| 1 | `agent-browser` is a Windows WSL2 proxy — does it work inside the self-hosted GitHub runner? | High | Test manually on runner before wiring CI; fallback to native Playwright SDK |
| 2 | `assertSemanticContent` requires Claude API call — adds cost per CI run | Medium | Cache semantic assertions per SHA; use Haiku model for cost |
| 3 | `tests/.auth/user.json` in S3 cache with real Cognito tokens | Medium | Use short-lived tokens (50 min TTL); encrypt S3 bucket at rest |
| 4 | Scenario video files can be large (50-100MB/scenario) | Low | Set S3 lifecycle to 14-day expiry; compress with ffmpeg in CI |
| 5 | Dev-mode bypass vs prod Cognito auth — two different code paths | Low | `auth.setup.ts` handles both automatically (already in global-setup.ts) |

---

## Suggested Build Order

1. **Phase 1** (1-2 hours): `auth.setup.ts` + update `playwright.config.ts` + gitignore `.auth/`
2. **Phase 2a** (2-3 hours): 4 scenario JSON files + `agent-runner.ts` conductor
3. **Phase 2b** (1 hour): `.claude/skills/agent-e2e-test/SKILL.md` + Justfile commands
4. **Phase 3** (2-3 hours): `agent-validate.yml` + `generate-test-report.py` + update CLAUDE.md

**Total estimate**: ~8-10 hours engineering time. Phase 1 can ship independently as a standalone improvement to auth state management.
