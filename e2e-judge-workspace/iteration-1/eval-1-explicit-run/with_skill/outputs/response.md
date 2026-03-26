# E2E Judge Run Plan — login, home, chat journeys

## 1. Pre-flight Checks

Before executing the main command, I would run these checks:

### a. Verify Playwright and dependencies are installed

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server
pip install playwright boto3 2>/dev/null | tail -1
playwright install chromium --with-deps 2>/dev/null | tail -1
```

**Why**: The SKILL.md lists `playwright` and `boto3` as prerequisites. Playwright also needs the Chromium browser binary installed. Without these, the orchestrator will fail immediately.

### b. Verify AWS credentials for Bedrock access

```bash
aws sts get-caller-identity --profile eagle 2>/dev/null || aws sts get-caller-identity
```

**Why**: The vision judge calls Bedrock converse (Sonnet) to evaluate screenshots. Without valid `bedrock:InvokeModel` permissions, screenshot capture will succeed but judgment will fail. On the EC2 dev box, the instance role should suffice. Locally, the `eagle` SSO profile is needed.

### c. Verify the ALB is reachable

```bash
curl -s -o /dev/null -w "%{http_code}" http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com/
```

**Why**: The ALB is inside the VPC. If running from a local machine outside the VPC, this will time out. The EC2 dev box inside the VPC should be able to reach it. A 200 or 302 response confirms reachability.

### d. Verify the orchestrator module exists

```bash
ls C:/Users/blackga/Desktop/eagle/sm_eagle/server/tests/e2e_judge_orchestrator.py
```

**Why**: Confirms the entry point is present before attempting the run.

---

## 2. Exact Bash Command to Run

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server && \
python -m tests.e2e_judge_orchestrator \
  --base-url http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com \
  --auth-email testuser@example.com \
  --auth-password "EagleTest2024!" \
  --journeys login,home,chat \
  -v
```

---

## 3. Flags and Arguments Explained

| Flag | Value | Why |
|------|-------|-----|
| `--base-url` | `http://EagleC-Front-...elb.amazonaws.com` | Targets the deployed ALB rather than the default `localhost:3000`. This is the deployed EAGLE app instance. |
| `--auth-email` | `testuser@example.com` | Cognito test user email. Playwright uses this to authenticate through the Cognito login flow before accessing protected pages. |
| `--auth-password` | `"EagleTest2024!"` | Cognito test user password. Quoted because it contains `!` which bash interprets as a history expansion character in interactive mode. |
| `--journeys` | `login,home,chat` | Limits the run to only the three requested journeys instead of the default `all` (which would also run admin, documents, responsive). This saves time and Bedrock cost. |
| `-v` | *(flag)* | Verbose logging. Provides step-by-step output showing screenshot capture, Bedrock calls, cache hits/misses, and individual verdicts. Essential for monitoring a run. |

### Flags NOT used and why

| Flag | Why omitted |
|------|-------------|
| `--headed` | Not needed; headless is correct for a standard run. Use `--headed` only when debugging a failure interactively. |
| `--purge-cache` | Not needed unless we suspect stale cached judgments. First run will have no cache anyway. |
| `--upload-s3` | Not requested. Would push results to the S3 eval bucket for the dashboard. Can add if needed later. |
| `--output` | Not specified; defaults to `data/e2e-judge/results/` which is the standard location. |

---

## 4. Expected Output

### Console output (with `-v` flag)

The user should see output similar to:

```
[INFO] E2E Judge starting — run ID: 20260326-xxxxxx
[INFO] Target: http://EagleC-Front-XYyWWR29wzVZ-745394335.us-east-1.elb.amazonaws.com
[INFO] Journeys: login, home, chat
[INFO] Launching Playwright (headless chromium)...

=== Journey: login ===
  [1/3] Navigating to login page...
  [SCREENSHOT] login/01_login_page.png (captured)
  [JUDGE] login/01_login_page — PASS (confidence: 0.94, quality: 8/10)
  [2/3] Submitting credentials...
  [SCREENSHOT] login/02_auth_redirect.png (captured)
  [JUDGE] login/02_auth_redirect — PASS (confidence: 0.90, quality: 7/10)
  [3/3] Post-login landing...
  [SCREENSHOT] login/03_post_login.png (captured)
  [JUDGE] login/03_post_login — PASS (confidence: 0.93, quality: 8/10)
  Journey login: 3/3 PASS

=== Journey: home ===
  [1/4] Home page initial load...
  [SCREENSHOT] home/01_home_page.png (captured)
  [JUDGE] home/01_home_page — PASS (confidence: 0.91, quality: 8/10)
  ... (4-5 steps total)
  Journey home: 4/4 PASS

=== Journey: chat ===
  [1/7] Chat page load...
  [SCREENSHOT] chat/01_chat_page.png (captured)
  [JUDGE] chat/01_chat_page — PASS (confidence: 0.92, quality: 8/10)
  [2/7] Sending test message...
  [3/7] Streaming response...
  ... (7-8 steps total)
  Journey chat: 7/7 PASS

=== Summary ===
  Total steps:  14-16
  Passed:       14-16
  Failed:       0
  Cache hits:   0 (first run)
  Cost estimate: ~$0.06 (14-16 screenshots x $0.004)
  Results:      data/e2e-judge/results/20260326-xxxxxx.json
  Report:       data/e2e-judge/results/20260326-xxxxxx-report.md
```

### File outputs

The run produces these artifacts under `server/data/e2e-judge/`:

| Path | Content |
|------|---------|
| `results/{run-id}.json` | Structured JSON with all step verdicts, scores, timing |
| `results/latest.json` | Symlink/copy of the latest run results |
| `results/{run-id}-report.md` | Human-readable markdown summary report |
| `screenshots/{run-id}/login/01_login_page.png` | Screenshot of login page |
| `screenshots/{run-id}/login/02_auth_redirect.png` | Screenshot of auth redirect |
| `screenshots/{run-id}/login/03_post_login.png` | Screenshot of post-login |
| `screenshots/{run-id}/home/*.png` | 4-5 home page screenshots |
| `screenshots/{run-id}/chat/*.png` | 7-8 chat interaction screenshots |
| `cache/{sha256}.json` | Cached judgments keyed by screenshot hash |

### Expected step counts per journey

| Journey | Approximate screenshots | What gets tested |
|---------|------------------------|------------------|
| `login` | 3 | Login page render, Cognito auth flow, post-login redirect |
| `home` | 4-5 | Home page render, feature cards, sidebar navigation |
| `chat` | 7-8 | Chat page load, message input, send, streaming indicator, response render, tool cards |
| **Total** | **14-16** | |

### Estimated cost

- Vision judge (Sonnet): ~14-16 screenshots x $0.004 = ~$0.06
- EAGLE app (Haiku 4.5): ~1-2 chat interactions x $0.001 = ~$0.002
- **Total**: ~$0.06 for a first run with no cache
- Repeat runs with identical UI: $0 (cache hits)

### Possible failure modes

| Symptom | Likely cause |
|---------|-------------|
| Connection timeout on `--base-url` | Running outside VPC; ALB is not internet-facing |
| `NoCredentialsError` from boto3 | Missing AWS credentials for Bedrock |
| `AccessDeniedException` from Bedrock | IAM role lacks `bedrock:InvokeModel` permission |
| Login step fails with screenshot showing error | Wrong credentials or Cognito user pool misconfiguration |
| Chat journey timeout | Backend not responding; check ECS task health |
