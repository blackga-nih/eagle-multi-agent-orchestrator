---
name: e2e-judge
description: >
  Screenshot-based E2E testing with LLM-as-judge for the EAGLE application.
  Captures screenshots at every test step using Playwright, sends them to Claude
  Sonnet via Bedrock converse for structured pass/fail evaluation with UI quality
  scoring. Caches judgments by screenshot SHA-256 hash so repeated runs are
  near-free. Targets the deployed ALB URL from the EC2 dev box inside the VPC.
  Use this skill whenever someone asks to run E2E tests, visual QA, screenshot
  testing, UI validation, vision-based testing, or wants to check if the deployed
  EAGLE app looks correct. Also use when asked about "e2e judge", "screenshot
  judge", "visual regression", or "UI quality check".
---

# E2E Judge — Screenshot + Vision Evaluation Pipeline

Run visual QA against the deployed EAGLE application. Playwright captures
screenshots at every meaningful step, Sonnet evaluates each screenshot via
Bedrock converse (image content blocks), and results are cached + reported.

## Architecture

```
EC2 dev box (in VPC) or local machine
  -> e2e_judge_orchestrator.py (CLI entry point)
    -> ScreenshotCapture (Playwright headless, Cognito auth)
      -> VisionJudge (Bedrock converse, Sonnet vision)
        -> JudgeCache (SHA-256 keyed, file-based)
          -> Results JSON + Markdown report
```

**Model split**:
- **Vision judge**: Claude Sonnet (`E2E_JUDGE_MODEL` env var) — evaluates screenshots
- **EAGLE app**: Haiku 4.5 (`STRANDS_MODEL_ID` env var) — cheap responses during test interactions

## Prerequisites

```bash
pip install playwright boto3
playwright install chromium --with-deps
```

AWS credentials must have `bedrock:InvokeModel` access (EC2 instance role or AWS SSO profile).

## Running

### Full pipeline (all journeys)
```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys all
```

Auth credentials come from `EAGLE_TEST_EMAIL` / `EAGLE_TEST_PASSWORD` env vars, or
pass `--auth-email` / `--auth-password` flags. Real users are in Cognito pool
`us-east-1_ChGLHtmmp` (the active `eagle-users-dev` pool). Never hardcode passwords
in commands — use env vars or prompt the user for credentials.

When `--upload-s3` is used, always tell the user results are viewable at
`/admin/e2e-judge` on the deployed app.

### Specific journeys
```bash
python -m tests.e2e_judge_orchestrator --journeys chat,home,admin
```

### With S3 upload (for dashboard)
```bash
python -m tests.e2e_judge_orchestrator --journeys all --upload-s3
```

### Local development testing
```bash
python -m tests.e2e_judge_orchestrator --base-url http://localhost:3000 --journeys login,home
```

### Flags
| Flag | Description |
|------|-------------|
| `--base-url` | Target URL (env: `BASE_URL`, default: localhost:3000) |
| `--auth-email` | Cognito email (env: `EAGLE_TEST_EMAIL`) |
| `--auth-password` | Cognito password (env: `EAGLE_TEST_PASSWORD`) |
| `--journeys` | Comma-separated or `all` (default: all) |
| `--headed` | Show browser window (for debugging) |
| `--purge-cache` | Clear cached judgments first |
| `--upload-s3` | Push results + screenshots to S3 eval bucket |
| `--output` | Custom output directory |
| `-v` | Verbose logging |

## Available Journeys

| Journey | What it tests | ~Screenshots |
|---------|---------------|-------------|
| `login` | Login page, Cognito auth flow, redirect | 3 |
| `home` | Home page, feature cards, sidebar navigation | 4-5 |
| `chat` | Multi-turn chat: 2 messages, pre-send screenshots, 30s streaming intervals | 10-15+ |
| `admin` | Admin dashboard + sub-pages (skills, templates, traces, costs) | 6-7 |
| `documents` | Document list, detail view, templates | 3-4 |
| `responsive` | Key pages at mobile (375px) and tablet (768px) | 6 |
| `acquisition_package` | Full UC-1 lifecycle: intake → doc generation → checklist → revision → finalize → export | 25-35+ |

## Output

**Results JSON** → `data/e2e-judge/results/{run-id}.json` (+ `latest.json`)
**Markdown report** → `data/e2e-judge/results/{run-id}-report.md`
**Screenshots** → `data/e2e-judge/screenshots/{run-id}/{journey}/{step}.png`
**Cache** → `data/e2e-judge/cache/{sha256}.json`

Each step produces a structured judgment:
```json
{
  "verdict": "pass",
  "confidence": 0.92,
  "reasoning": "Chat page loads correctly with sidebar, input area, and welcome message",
  "ui_quality_score": 8,
  "issues": [],
  "cached": false
}
```

## Caching

Screenshots are hashed (SHA-256). Identical UI renders produce identical hashes,
which means the same page that looks the same = free cache hit. Any pixel change
(layout shift, new content, different data) invalidates the cache and triggers a
fresh Sonnet evaluation. Cache TTL: 7 days (configurable via `E2E_JUDGE_CACHE_TTL_DAYS`).

## Cost

- Sonnet vision: ~$0.004/screenshot (for judge evaluation)
- Haiku 4.5: ~$0.001/response (for EAGLE app during tests)
- Full run (~40 screenshots, excl. acquisition_package): ~$0.16 + app costs
- Full run with acquisition_package (~70+ screenshots): ~$0.30 + app costs
- Cached repeat runs: $0

**Note:** The `acquisition_package` journey is significantly longer than other journeys
(7 chat turns, ~10-15 minutes, 25-35+ screenshots) because it tests the full UC-1
acquisition lifecycle end-to-end. When running `--journeys all`, budget extra time
and cost for this journey.

## Key Files

| File | Purpose |
|------|---------|
| `server/tests/e2e_judge_orchestrator.py` | CLI entry point, pipeline orchestration |
| `server/tests/e2e_vision_judge.py` | Bedrock converse with Sonnet vision |
| `server/tests/e2e_judge_cache.py` | SHA-256 file cache for judgments |
| `server/tests/e2e_judge_prompts.py` | Judge prompt templates per page type |
| `server/tests/e2e_judge_journeys.py` | Journey definitions (Python async) |
| `server/tests/e2e_screenshot_capture.py` | Playwright screenshot utility |

## Adding New Journeys

1. Open `server/tests/e2e_judge_journeys.py`
2. Add a new function with the `@journey` decorator:

```python
@journey("workflows", "Acquisition package workflows and status tracking")
async def journey_workflows(page, capture, base_url):
    screenshots = []
    await page.goto(f"{base_url}/packages", wait_until="networkidle")
    s = await capture.take(page, "workflows", "01_packages_list", "Package list view")
    screenshots.append(s)
    # ... more steps
    return screenshots
```

3. Add a page-specific prompt in `e2e_judge_prompts.py` (optional — falls back to general prompt)
4. Run: `python -m tests.e2e_judge_orchestrator --journeys workflows`
