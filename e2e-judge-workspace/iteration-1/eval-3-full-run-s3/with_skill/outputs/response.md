# E2E Judge: Full Visual Regression Test with S3 Upload

## Pre-flight Checks

Before running the pipeline, I would verify the following:

1. **AWS credentials are active** -- the `--upload-s3` flag pushes results to the S3 eval bucket (`eagle-eval-artifacts-695681773636-dev`), which requires valid AWS credentials with `s3:PutObject` permission in addition to `bedrock:InvokeModel`.

```bash
aws sts get-caller-identity --profile eagle
```

2. **Playwright and dependencies are installed** in the server virtualenv:

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server
pip install playwright boto3
playwright install chromium --with-deps
```

3. **Test credentials are available** -- confirm the env vars `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` are set, or plan to pass them as flags. The known test credentials from the codebase are `testuser@example.com` / `EagleTest2024!`.

4. **ALB is reachable** -- a quick health check against the deployed frontend ALB to confirm the app is up before spending time launching Playwright:

```bash
curl -s -o /dev/null -w "%{http_code}" http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com
```

Expected: `200` (or `302` if it redirects to login). If this times out, you are likely not inside the VPC -- run from the EC2 dev box or check VPN connectivity.

---

## Exact Command

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server && \
python -m tests.e2e_judge_orchestrator \
  --base-url http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com \
  --auth-email testuser@example.com \
  --auth-password "EagleTest2024!" \
  --journeys all \
  --upload-s3 \
  -v
```

---

## Flags and Arguments Explained

| Flag | Value | Why |
|------|-------|-----|
| `--base-url` | `http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com` | The deployed EAGLE frontend ALB URL (from `playwright.config.ts` and deployment expertise). This is the live dev environment. |
| `--auth-email` | `testuser@example.com` | Cognito test user for authenticating Playwright. Passed as a flag so the orchestrator can log in through the Cognito auth flow before capturing pages. |
| `--auth-password` | `EagleTest2024!` | Corresponding Cognito password. Alternatively, set `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` env vars. |
| `--journeys` | `all` | Runs every registered journey: `login`, `home`, `chat`, `admin`, `documents`, `responsive`. This gives full coverage across all pages. |
| `--upload-s3` | *(flag, no value)* | After the run completes, uploads the results JSON, markdown report, and all screenshots to the S3 eval bucket (`eagle-eval-artifacts-{account}-dev`). This is what makes the results visible in the dashboard. |
| `-v` | *(flag, no value)* | Verbose logging -- prints each journey step, screenshot path, judge verdict, and S3 upload progress to stdout. Essential for monitoring a full run with ~30-40 screenshots. |

### Flags I chose NOT to use

| Flag | Why omitted |
|------|-------------|
| `--headed` | Not needed -- headless is correct for a full regression run. Use `--headed` only when debugging a specific journey interactively. |
| `--purge-cache` | Not needed unless you specifically want to re-evaluate screenshots that haven't changed. Keeping the cache means unchanged pages are judged for free (cache hit by SHA-256). If you want a fully fresh evaluation, add `--purge-cache`. |
| `--output` | Not needed -- the default output directory (`data/e2e-judge/results/`) is the standard location. The S3 upload reads from there. |

---

## Expected Output

### Console output (verbose mode)

The run will print progress like:

```
[e2e-judge] Starting pipeline: 6 journeys, base_url=http://EagleC-Front-...
[e2e-judge] Authenticating as testuser@example.com...
[e2e-judge] Auth successful, cookies set.

[e2e-judge] === Journey: login (Login page, Cognito auth flow, redirect) ===
[e2e-judge]   Step 1/3: login_page → screenshot saved: data/e2e-judge/screenshots/{run-id}/login/01_login_page.png
[e2e-judge]   Judge: PASS (confidence=0.94, ui_quality=8) — "Login page renders correctly with NCI branding..."
[e2e-judge]   Step 2/3: cognito_redirect → screenshot saved: ...
[e2e-judge]   Judge: PASS (confidence=0.91, ui_quality=7) [CACHED]
...

[e2e-judge] === Journey: chat (Full chat: send message, streaming, response) ===
[e2e-judge]   Step 1/8: chat_empty → ...
...

[e2e-judge] === Journey: responsive (Key pages at mobile and tablet) ===
...

[e2e-judge] Pipeline complete: 35/38 PASS, 2 WARN, 1 FAIL
[e2e-judge] Report: data/e2e-judge/results/20260326-HHMMSS-report.md
[e2e-judge] Results: data/e2e-judge/results/20260326-HHMMSS.json

[e2e-judge] Uploading to S3: eagle-eval-artifacts-695681773636-dev
[e2e-judge]   Uploaded: results/20260326-HHMMSS.json
[e2e-judge]   Uploaded: results/20260326-HHMMSS-report.md
[e2e-judge]   Uploaded: results/latest.json
[e2e-judge]   Uploaded: screenshots/20260326-HHMMSS/ (38 files)
[e2e-judge] S3 upload complete.
```

### Local file outputs

| Artifact | Path |
|----------|------|
| Results JSON | `server/data/e2e-judge/results/{run-id}.json` (+ `latest.json` symlink) |
| Markdown report | `server/data/e2e-judge/results/{run-id}-report.md` |
| Screenshots | `server/data/e2e-judge/screenshots/{run-id}/{journey}/{step}.png` |
| Cache entries | `server/data/e2e-judge/cache/{sha256}.json` |

### S3 outputs (for the dashboard)

All the above files are uploaded to `s3://eagle-eval-artifacts-695681773636-dev/e2e-judge/...` with the same directory structure. The `latest.json` file is what the dashboard reads to display the most recent run.

### Approximate run characteristics

| Metric | Estimate |
|--------|----------|
| Total screenshots | ~30-40 (across 6 journeys) |
| Runtime | 3-5 minutes (depending on network/app response time) |
| Cost (Sonnet vision judge) | ~$0.16 for fresh evaluations; $0 for cache hits |
| Cost (Haiku for EAGLE app responses in chat journey) | ~$0.008 |

### Results JSON structure (per step)

Each screenshot step produces a structured judgment:

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

The top-level results JSON aggregates all steps with summary statistics (pass/fail/warn counts, average UI quality score, total cost, cache hit rate).

---

## If Something Goes Wrong

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Connection timeout on `--base-url` | Not inside VPC / ALB not reachable | Run from EC2 dev box or check VPN |
| `401` / auth failure | Wrong Cognito credentials or user not in pool | Verify `EAGLE_TEST_EMAIL` / `EAGLE_TEST_PASSWORD` |
| `botocore.exceptions.ClientError: bedrock:InvokeModel` | Missing Bedrock permissions | Ensure EC2 instance role or SSO profile (`eagle`) has Bedrock access |
| `S3 upload failed: AccessDenied` | Missing `s3:PutObject` on the eval bucket | Check IAM role has write access to `eagle-eval-artifacts-*` |
| All screenshots cached (no fresh evaluations) | Previous run had identical UI | Add `--purge-cache` to force fresh Sonnet evaluations |
