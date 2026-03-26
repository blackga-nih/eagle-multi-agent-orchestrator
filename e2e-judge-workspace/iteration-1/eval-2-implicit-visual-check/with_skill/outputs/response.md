# E2E Judge Response: Implicit Visual Check of Admin Dashboard and Chat Page

## Skill Recognition

The user's request -- "quick visual check of the admin dashboard and chat page to make sure nothing looks broken" against the "deployed URL" -- maps directly to the **e2e-judge** skill. The skill description explicitly covers: "visual QA", "UI validation", "check if the deployed EAGLE app looks correct", and "screenshot testing". Even though the user did not mention "e2e judge" by name, the intent is a visual regression check on specific pages of the deployed app, which is exactly what this pipeline does.

---

## Pre-Flight Checks

Before running the command, I would verify:

1. **Playwright is installed**: `playwright install chromium --with-deps` (the skill requires Playwright + Chromium)
2. **AWS credentials are active**: The vision judge calls Bedrock converse (Sonnet), so valid AWS credentials with `bedrock:InvokeModel` are required. On the EC2 dev box, the instance role provides this. Locally, I would confirm `aws sts get-caller-identity --profile eagle` succeeds.
3. **Network reachability**: The deployed ALB URL (`http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com`) must be reachable from the current machine. On the EC2 dev box inside the VPC this is guaranteed. From a local Windows machine, this public-facing ALB should also be accessible, but worth a quick `curl -sI` to confirm.
4. **Python dependencies**: `pip install playwright boto3` must be satisfied in the active environment.
5. **Test credentials available**: The orchestrator needs Cognito auth credentials. These are typically set via environment variables `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD`, or passed as CLI flags.

### Pre-flight commands:

```bash
# Verify AWS credentials
aws sts get-caller-identity --profile eagle

# Verify ALB is reachable
curl -sI http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com | head -5

# Verify Playwright chromium is installed
python -c "from playwright.sync_api import sync_playwright; print('OK')"
```

---

## Exact Command(s) to Run

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server/ && \
python -m tests.e2e_judge_orchestrator \
  --base-url http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com \
  --auth-email testuser@example.com \
  --auth-password "EagleTest2024!" \
  --journeys admin,chat \
  -v
```

---

## Flags and Arguments Explained

| Flag | Value | Why |
|------|-------|-----|
| `--base-url` | `http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com` | The deployed ALB URL for the EAGLE frontend. The user said "deployed URL" and this is the known production/dev ALB from the project configuration (referenced in `playwright.config.ts`, deployment expertise docs, and the skill's own example). |
| `--auth-email` | `testuser@example.com` | Cognito test user email for authentication. Required to access protected pages (admin dashboard, chat). |
| `--auth-password` | `"EagleTest2024!"` | Cognito test user password. Paired with `--auth-email` for the login flow. |
| `--journeys` | `admin,chat` | **Only the two journeys the user asked about.** The user specifically requested the "admin dashboard and chat page" -- no need to run `login`, `home`, `documents`, or `responsive`. The `admin` journey covers the admin dashboard and sub-pages (skills, templates, traces, costs -- approximately 6-7 screenshots). The `chat` journey covers the full chat flow (send message, streaming response, tool cards -- approximately 7-8 screenshots). |
| `-v` | *(flag)* | Verbose logging so we can see real-time progress of each screenshot capture and judge evaluation. Useful for a quick check where the user wants to know status as it runs. |

### Flags intentionally NOT used

| Flag | Why omitted |
|------|-------------|
| `--headed` | Not needed -- headless is fine for automated QA (and more reliable on EC2/CI). |
| `--purge-cache` | Not needed unless we suspect stale cache. If the frontend just changed, the screenshots will have different pixel content and therefore different SHA-256 hashes, which automatically bypasses the cache. |
| `--upload-s3` | User did not ask for S3 persistence or dashboard integration. Keep it local. |
| `--output` | Default output directory (`data/e2e-judge/results/`) is fine for a quick check. |

---

## Expected Output

### Console output (verbose mode)

The user should see streaming output similar to:

```
2026-03-26T10:30:00 INFO  [e2e-judge] Starting E2E judge pipeline
2026-03-26T10:30:00 INFO  [e2e-judge] Target: http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com
2026-03-26T10:30:00 INFO  [e2e-judge] Journeys: admin, chat
2026-03-26T10:30:01 INFO  [e2e-judge] Authenticating via Cognito...
2026-03-26T10:30:03 INFO  [e2e-judge] Authentication successful
2026-03-26T10:30:03 INFO  [e2e-judge] === Journey: admin ===
2026-03-26T10:30:05 INFO  [e2e-judge] Screenshot: admin/01_dashboard_overview.png
2026-03-26T10:30:07 INFO  [e2e-judge] Judge: PASS (confidence: 0.91, quality: 8/10)
2026-03-26T10:30:09 INFO  [e2e-judge] Screenshot: admin/02_skills_page.png
2026-03-26T10:30:11 INFO  [e2e-judge] Judge: PASS (confidence: 0.88, quality: 7/10)
... (4-5 more admin screenshots) ...
2026-03-26T10:30:25 INFO  [e2e-judge] === Journey: chat ===
2026-03-26T10:30:27 INFO  [e2e-judge] Screenshot: chat/01_chat_page_load.png
2026-03-26T10:30:29 INFO  [e2e-judge] Judge: PASS (confidence: 0.93, quality: 8/10)
... (6-7 more chat screenshots) ...
2026-03-26T10:31:00 INFO  [e2e-judge] Pipeline complete: 13/13 passed, 0 failed
```

### File artifacts produced

| Artifact | Location |
|----------|----------|
| Results JSON | `server/data/e2e-judge/results/{run-id}.json` and `latest.json` |
| Markdown report | `server/data/e2e-judge/results/{run-id}-report.md` |
| Screenshots | `server/data/e2e-judge/screenshots/{run-id}/admin/*.png` and `server/data/e2e-judge/screenshots/{run-id}/chat/*.png` |
| Cache entries | `server/data/e2e-judge/cache/{sha256}.json` (one per unique screenshot) |

### Results JSON structure (per step)

Each screenshot step produces a structured judgment:

```json
{
  "verdict": "pass",
  "confidence": 0.92,
  "reasoning": "Admin dashboard loads correctly with navigation sidebar, stats cards, and data tables rendered properly",
  "ui_quality_score": 8,
  "issues": [],
  "cached": false
}
```

### What a successful run looks like

- **All 13-15 screenshots** across admin (~6-7) and chat (~7-8) journeys receive **"pass"** verdicts
- **No `issues` arrays** with entries -- empty `[]` means no visual defects detected
- **`ui_quality_score`** values of 7+ across all steps (scores below 5 would indicate significant layout or rendering problems)
- The markdown report provides a human-readable summary with embedded screenshot references

### What a failure looks like

If the frontend deployment broke something, you would see:

```
2026-03-26T10:30:29 WARN  [e2e-judge] Judge: FAIL (confidence: 0.87, quality: 3/10)
  Issues: ["Main content area is blank", "Sidebar navigation links not rendered"]
```

The final summary would report `12/13 passed, 1 failed` and the markdown report would highlight the failing step with the Sonnet judge's reasoning.

---

## Approximate Cost and Duration

- **Duration**: ~60-90 seconds (Playwright navigation + Bedrock Sonnet calls for ~13 screenshots)
- **Cost**: ~$0.05-0.06 (13 screenshots x ~$0.004/screenshot for Sonnet vision evaluation)
- **Cached re-run**: If nothing changed visually, a repeat run costs $0 and completes in ~20 seconds (screenshots still captured, but SHA-256 matches trigger cache hits)

---

## Summary

The e2e-judge skill is the right tool for this request. By scoping `--journeys` to just `admin,chat`, we target exactly the two pages the user cares about without burning time/cost on login, home, documents, or responsive journeys. The pipeline will capture ~13 screenshots, send each to Sonnet for structured pass/fail evaluation, and produce a report confirming whether the frontend deployment introduced any visual regressions.
