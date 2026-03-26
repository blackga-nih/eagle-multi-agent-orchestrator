# E2E Judge: Full Visual Regression Run with S3 Upload

A complete walkthrough of running the EAGLE E2E Judge pipeline across all pages with results uploaded to S3 for the admin dashboard.

---

## 1. Pre-Flight Checks

Before executing the pipeline, the following checks must pass:

### Environment & Credentials

```bash
# 1a. Verify AWS credentials are active (SSO profile or instance role)
aws sts get-caller-identity --profile eagle

# 1b. Confirm Bedrock model access (Sonnet for judge, Haiku for EAGLE app)
aws bedrock get-foundation-model \
  --model-identifier us.anthropic.claude-sonnet-4-6-20250514-v1:0 \
  --region us-east-1

# 1c. Confirm auth env vars are set (never hardcode passwords)
echo "EAGLE_TEST_EMAIL is set: ${EAGLE_TEST_EMAIL:+yes}"
echo "EAGLE_TEST_PASSWORD is set: ${EAGLE_TEST_PASSWORD:+yes}"
```

### Dependencies

```bash
# 1d. Verify Python packages
cd server/
pip show playwright boto3 2>/dev/null | grep -E "^(Name|Version)"

# 1e. Verify Chromium is installed for Playwright
playwright install chromium --with-deps 2>&1 | tail -1
```

### Target Reachability

```bash
# 1f. Verify the deployed ALB is reachable from this machine
curl -s -o /dev/null -w "%{http_code}" \
  http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com

# Expected: 200 or 302 (redirect to login)
# If running from outside the VPC, this will fail — must use EC2 dev box or VPN.
```

### S3 Bucket Existence

```bash
# 1g. Confirm the eval artifacts bucket exists
aws s3 ls s3://eagle-eval-artifacts-695681773636-dev/e2e-judge/ --profile eagle
```

---

## 2. Exact Command to Execute

```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys all \
  --upload-s3 \
  -v
```

That is the single command. Auth credentials are pulled from the environment variables `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` (which must already be exported).

---

## 3. Flag-by-Flag Explanation

| Flag | Value | Why |
|------|-------|-----|
| `--base-url` | `http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com` | The deployed ALB URL for the EAGLE dev environment inside the VPC. This is the actual deployed app, not localhost. The default in the CLI argparse is this same URL (from `e2e_judge_orchestrator.py` line 330). |
| `--journeys` | `all` | Runs every registered journey in `JOURNEY_REGISTRY`: login, home, chat, admin, documents, responsive. When set to `all`, the orchestrator calls `list_journeys()` which returns all keys from the registry dict. This gives complete coverage of all EAGLE pages. |
| `--upload-s3` | *(flag, no value)* | After all screenshots are captured and judged, uploads results JSON + all PNG screenshots to the S3 eval artifacts bucket (`eagle-eval-artifacts-{account_id}-dev`). The upload function (`_upload_to_s3` at line 291) auto-detects the bucket name using the STS caller identity account ID. It uploads: (a) `e2e-judge/results/{run-id}.json`, (b) `e2e-judge/latest.json` (overwritten each run), and (c) all PNGs under `e2e-judge/screenshots/{run-id}/{journey}/{step}.png`. This is what feeds the admin dashboard at `/admin/e2e-judge`. |
| `-v` | *(flag, no value)* | Sets logging to `DEBUG` level. This surfaces cache hit/miss decisions, Bedrock converse call details, token counts per evaluation, and Playwright navigation events. Essential for diagnosing failures on the first run. |

### Flags NOT used (and why)

| Flag | Why omitted |
|------|-------------|
| `--auth-email` / `--auth-password` | Credentials come from `EAGLE_TEST_EMAIL` / `EAGLE_TEST_PASSWORD` env vars, which is the correct pattern. Never pass passwords as CLI arguments (they appear in shell history and `ps` output). |
| `--headed` | Not needed for a CI/automated run. Only useful when debugging a specific journey interactively on a machine with a display. |
| `--purge-cache` | Not needed for a standard run. The cache has a 7-day TTL. Only purge if you suspect stale results or have made visual changes you want to force-reevaluate. |
| `--output` | Defaults to `data/e2e-judge/results/` relative to repo root, which is the expected location. |

---

## 4. All Available Journeys

The journey registry in `server/tests/e2e_judge_journeys.py` contains 6 journeys:

### 4.1 `login` -- Login Page and Authentication Flow
- **Description**: Login page load and authentication flow
- **What it tests**: Initial page load (login or auto-redirect), Cognito login form rendering, post-auth redirect to home
- **Steps**:
  1. `01_initial_load` -- Navigate to root URL, capture whatever loads (login form or home redirect)
  2. `02_login_form` / `02_authenticated` -- Login form with email/password fields (or confirmation of dev-mode auto-auth)
  3. `03_post_auth_home` -- Home page after successful authentication
- **Approximate screenshots**: 3

### 4.2 `home` -- Home Page Feature Cards and Navigation
- **Description**: Home page feature cards and navigation elements
- **What it tests**: Welcome message, feature cards (Acquisition Intake, Document Generation, etc.), sidebar navigation, card click navigation
- **Steps**:
  1. `01_home_page` -- Full home page with welcome message and feature cards
  2. `02_sidebar` -- Sidebar navigation with session list and nav links
  3. `03_card_navigation` -- Page after clicking first feature card (verifies routing)
  4. `04_return_home` -- Home page after navigating back
- **Approximate screenshots**: 4-5 (step 2 is conditional on sidebar element existing; step 3 is conditional on feature cards existing)

### 4.3 `chat` -- Full Multi-Turn Chat Interaction
- **Description**: Full chat interaction: send message, agent streaming, response, tool cards
- **What it tests**: Chat page load, new chat creation, message composition, agent streaming (Haiku 4.5 responses), response rendering, tool use cards, multi-turn conversation flow
- **Steps**:
  1. `01_chat_page` -- Chat page with sidebar, input area, quick action buttons
  2. `02_new_chat` -- Fresh chat session after clicking "New Chat"
  3. `03_pre_send_1` -- **Pre-send capture**: user's first message typed in textarea, before clicking send
  4. `04_streaming_start` -- Agent streaming state (3s after send) -- typing indicator or partial response
  5. `05_a_interval_30s` through `05_d_interval_120s` -- **30-second interval captures** during streaming wait (up to 120s timeout, so 0-4 interval shots)
  6. `06_response_1_complete` -- Completed first agent response
  7. `07_response_1_scrolled` -- Full first response scrolled into view
  8. `08_tool_cards` -- Tool use cards if the agent invoked any tools (conditional)
  9. `09_pre_send_2` -- **Pre-send capture**: follow-up message typed, before clicking send
  10. `10_streaming_2_start` -- Second streaming state (3s after send)
  11. `11_a_interval_30s` through `11_d_interval_120s` -- **30-second interval captures** for second message response
  12. `12_response_2_complete` -- Completed second agent response
  13. `13_full_conversation` -- Full multi-turn conversation scrolled to bottom
- **Approximate screenshots**: 10-15+ (varies based on agent response time; faster responses = fewer interval shots)

### 4.4 `admin` -- Admin Dashboard and Sub-Pages
- **Description**: Admin dashboard and sub-pages (skills, templates, traces)
- **What it tests**: Admin dashboard with stats cards, plus 5 sub-pages for management features
- **Steps**:
  1. `01_dashboard` -- Main admin dashboard with stats cards and navigation
  2. `02_skills` -- `/admin/skills` -- Skills management page with agent/skill list
  3. `03_templates` -- `/admin/templates` -- Document templates management page
  4. `04_traces` -- `/admin/traces` -- Trace viewer with recent agent traces
  5. `05_tests` -- `/admin/tests` -- Test results page with run history
  6. `06_costs` -- `/admin/costs` -- Cost tracking dashboard
- **Approximate screenshots**: 6-7 (sub-pages that fail to load are skipped gracefully with error logging)

### 4.5 `documents` -- Document List and Templates
- **Description**: Document list, template view, and document detail
- **What it tests**: Documents listing page, individual document detail view (if documents exist), templates listing
- **Steps**:
  1. `01_documents_list` -- Documents listing page with document cards or table
  2. `02_document_detail` -- Single document detail view (conditional: only if documents exist)
  3. `03_templates` -- Document templates listing
- **Approximate screenshots**: 3-4 (step 2 is conditional on documents existing in the system)

### 4.6 `responsive` -- Key Pages at Mobile and Tablet Viewports
- **Description**: Key pages at mobile (375px) and tablet (768px) viewports
- **What it tests**: Responsive layout at two breakpoints across 3 key pages. Checks content reflow, no horizontal overflow, hamburger menu on mobile, readable text, tappable buttons.
- **Steps**:
  1. `mobile_home` -- Home page at 375x812 (iPhone-class)
  2. `mobile_chat` -- Chat page at 375x812
  3. `mobile_admin` -- Admin dashboard at 375x812
  4. `tablet_home` -- Home page at 768x1024 (iPad-class)
  5. `tablet_chat` -- Chat page at 768x1024
  6. `tablet_admin` -- Admin dashboard at 768x1024
- **Approximate screenshots**: 6 (viewport is reset to 1440x900 after this journey completes)

### Total Screenshot Count Summary

| Journey | Min | Max | Notes |
|---------|-----|-----|-------|
| login | 3 | 3 | Fixed steps |
| home | 3 | 5 | Conditional on sidebar + feature cards |
| chat | 10 | 15+ | Variable: streaming interval shots depend on agent response time |
| admin | 1 | 7 | Sub-pages may fail gracefully |
| documents | 2 | 4 | Conditional on existing documents |
| responsive | 6 | 6 | Fixed: 2 viewports x 3 pages |
| **TOTAL** | **~25** | **~40+** | Typical run: ~32-38 screenshots |

---

## 5. Expected Output

### 5.1 Console Output

```
============================================================
E2E Judge Pipeline -- Run 20260326-143000
Target: http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com
Journeys: login, home, chat, admin, documents, responsive
============================================================

  [capture] Chromium launched (headless=True)
  [capture] Logging in as testuser@example.com...
  [capture] Authenticated successfully
  [capture] Screenshots will be saved to: /home/ec2-user/sm_eagle/data/e2e-judge/screenshots/20260326-143000

--- Journey: login ---
  [capture] login/01_initial_load (a3f8b2c1d4e5...)
  [capture] login/02_login_form (7e9f1a2b3c4d...)
  [capture] login/03_post_auth_home (1b2c3d4e5f6a...)

--- Journey: home ---
  [capture] home/01_home_page (d4e5f6a7b8c9...)
  [capture] home/02_sidebar (2c3d4e5f6a7b...)
  [capture] home/03_card_navigation (8c9d0e1f2a3b...)
  [capture] home/04_return_home (f6a7b8c9d0e1...)

--- Journey: chat ---
  [capture] chat/01_chat_page (5f6a7b8c9d0e...)
  [capture] chat/02_new_chat (0e1f2a3b4c5d...)
  [capture] chat/03_pre_send_1 (3b4c5d6e7f8a...)
  [capture] chat/04_streaming_start (6e7f8a9b0c1d...)
  [capture] chat/05_a_interval_30s (9b0c1d2e3f4a...)
  [capture] chat/06_response_1_complete (c1d2e3f4a5b6...)
  [capture] chat/07_response_1_scrolled (4a5b6c7d8e9f...)
  [capture] chat/09_pre_send_2 (7d8e9f0a1b2c...)
  [capture] chat/10_streaming_2_start (0a1b2c3d4e5f...)
  [capture] chat/11_a_interval_30s (2c3d4e5f6a7b...)
  [capture] chat/12_response_2_complete (5f6a7b8c9d0e...)
  [capture] chat/13_full_conversation (8c9d0e1f2a3b...)

--- Journey: admin ---
  [capture] admin/01_dashboard (b0c1d2e3f4a5...)
  [capture] admin/02_skills (e3f4a5b6c7d8...)
  [capture] admin/03_templates (1a2b3c4d5e6f...)
  [capture] admin/04_traces (4d5e6f7a8b9c...)
  [capture] admin/05_tests (7a8b9c0d1e2f...)
  [capture] admin/06_costs (0d1e2f3a4b5c...)

--- Journey: documents ---
  [capture] documents/01_documents_list (3a4b5c6d7e8f...)
  [capture] documents/02_document_detail (6d7e8f9a0b1c...)
  [capture] documents/03_templates (9a0b1c2d3e4f...)

--- Journey: responsive ---
  [capture] responsive/mobile_home (c2d3e4f5a6b7...)
  [capture] responsive/mobile_chat (5e6f7a8b9c0d...)
  [capture] responsive/mobile_admin (8b9c0d1e2f3a...)
  [capture] responsive/tablet_home (1e2f3a4b5c6d...)
  [capture] responsive/tablet_chat (4b5c6d7e8f9a...)
  [capture] responsive/tablet_admin (7e8f9a0b1c2d...)
  [capture] Done. 35 screenshots captured.

--- Judging 35 screenshots ---

  [+] login/01_initial_load: pass (score=8, cached=False)
  [+] login/02_login_form: pass (score=9, cached=False)
  [+] login/03_post_auth_home: pass (score=8, cached=False)
  [+] home/01_home_page: pass (score=9, cached=False)
  ... (one line per screenshot) ...
  [+] responsive/tablet_admin: pass (score=7, cached=False)

============================================================
Results: 33 passed, 0 failed, 2 warnings
Avg quality score: 7.8/10
Cache: 0/35 hits (0%)
Cost:   $0.1540 (51,200 in / 8,750 out tokens)
Report: /home/ec2-user/sm_eagle/data/e2e-judge/results/20260326-143000-report.md
JSON:   /home/ec2-user/sm_eagle/data/e2e-judge/results/20260326-143000.json
============================================================

  [s3] Uploaded to s3://eagle-eval-artifacts-695681773636-dev/e2e-judge/
```

### 5.2 Local File Structure

```
data/e2e-judge/
  results/
    20260326-143000.json          <-- Full structured results (per-journey, per-step)
    20260326-143000-report.md     <-- Human-readable markdown report
    latest.json                   <-- Symlink/copy to most recent run
  screenshots/
    20260326-143000/
      login/
        01_initial_load.png
        02_login_form.png
        03_post_auth_home.png
      home/
        01_home_page.png
        02_sidebar.png
        03_card_navigation.png
        04_return_home.png
      chat/
        01_chat_page.png
        02_new_chat.png
        03_pre_send_1.png
        04_streaming_start.png
        05_a_interval_30s.png       <-- (if response took >30s)
        06_response_1_complete.png
        07_response_1_scrolled.png
        09_pre_send_2.png
        10_streaming_2_start.png
        11_a_interval_30s.png       <-- (if response took >30s)
        12_response_2_complete.png
        13_full_conversation.png
      admin/
        01_dashboard.png
        02_skills.png
        03_templates.png
        04_traces.png
        05_tests.png
        06_costs.png
      documents/
        01_documents_list.png
        02_document_detail.png
        03_templates.png
      responsive/
        mobile_home.png
        mobile_chat.png
        mobile_admin.png
        tablet_home.png
        tablet_chat.png
        tablet_admin.png
  cache/
    a3f8b2c1d4e5...full-sha256.json   <-- One file per unique screenshot hash
    7e9f1a2b3c4d...full-sha256.json
    ... (one per unique screenshot)
```

### 5.3 S3 Paths (after `--upload-s3`)

Bucket: `s3://eagle-eval-artifacts-695681773636-dev/`

```
e2e-judge/
  latest.json                                              <-- Always points to most recent run
  results/
    20260326-143000.json                                   <-- This run's structured results
  screenshots/
    20260326-143000/
      login/01_initial_load.png
      login/02_login_form.png
      login/03_post_auth_home.png
      home/01_home_page.png
      home/02_sidebar.png
      home/03_card_navigation.png
      home/04_return_home.png
      chat/01_chat_page.png
      chat/02_new_chat.png
      chat/03_pre_send_1.png
      chat/04_streaming_start.png
      chat/05_a_interval_30s.png
      chat/06_response_1_complete.png
      chat/07_response_1_scrolled.png
      chat/09_pre_send_2.png
      chat/10_streaming_2_start.png
      chat/12_response_2_complete.png
      chat/13_full_conversation.png
      admin/01_dashboard.png
      admin/02_skills.png
      admin/03_templates.png
      admin/04_traces.png
      admin/05_tests.png
      admin/06_costs.png
      documents/01_documents_list.png
      documents/02_document_detail.png
      documents/03_templates.png
      responsive/mobile_home.png
      responsive/mobile_chat.png
      responsive/mobile_admin.png
      responsive/tablet_home.png
      responsive/tablet_chat.png
      responsive/tablet_admin.png
```

The S3 upload logic in `_upload_to_s3()` (orchestrator lines 291-316) auto-detects the account ID via `boto3.client("sts").get_caller_identity()["Account"]` and constructs the bucket name as `eagle-eval-artifacts-{account}-dev`. It uploads both the results JSON and `latest.json` to the `e2e-judge/results/` prefix, then walks the local screenshots directory and uploads every `.png` file under `e2e-judge/screenshots/`.

---

## 6. Cost Estimate

### Vision Judge Costs (Sonnet -- the main cost)

| Item | Value |
|------|-------|
| Model | `us.anthropic.claude-sonnet-4-6-20250514-v1:0` |
| Input pricing | $3.00 / million tokens |
| Output pricing | $15.00 / million tokens |
| Tokens per screenshot | ~1,600 input tokens (image) + ~200 prompt tokens |
| Output tokens per judgment | ~150-250 tokens (structured JSON) |

For a typical full run of ~35 screenshots (all cache misses):

| Component | Calculation | Cost |
|-----------|-------------|------|
| Input tokens | 35 screenshots x ~1,800 tokens = ~63,000 tokens | ~$0.189 |
| Output tokens | 35 judgments x ~200 tokens = ~7,000 tokens | ~$0.105 |
| **Judge subtotal** | | **~$0.16** (as stated in skill docs) |

### EAGLE App Costs (Haiku 4.5 -- responses during chat journey)

| Item | Value |
|------|-------|
| Model | Haiku 4.5 (via `STRANDS_MODEL_ID`) |
| Pricing | ~$0.001 per response |
| Chat messages sent | 2 (first message + follow-up) |
| **App subtotal** | | **~$0.002** |

### Total First Run

| Scenario | Estimated Cost |
|----------|---------------|
| First run (0% cache hit) | **~$0.16** |
| Repeat run, no UI changes (100% cache hit) | **$0.00** |
| Repeat run after minor changes (~50% cache hit) | **~$0.08** |
| Repeat run with `--purge-cache` (forced 0% cache) | **~$0.16** |

### S3 Storage Costs

| Item | Value |
|------|-------|
| Screenshot size (avg) | ~200-500 KB per PNG |
| Total storage per run | ~10-15 MB |
| S3 Standard storage | $0.023/GB/month |
| Monthly cost for 30 daily runs | ~$0.01/month (negligible) |

**Bottom line**: A full run costs approximately **$0.16** on the first execution. Subsequent runs with identical UI are free due to SHA-256 caching.

---

## 7. Where to View Results After S3 Upload

### Dashboard URL

**Results are viewable at the deployed EAGLE admin dashboard:**

```
https://<deployed-eagle-url>/admin/e2e-judge
```

For the current dev environment, this is:

```
http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com/admin/e2e-judge
```

The skill documentation explicitly states (line 60-61 of SKILL.md):

> When `--upload-s3` is used, always tell the user results are viewable at `/admin/e2e-judge` on the deployed app.

The dashboard reads from `e2e-judge/latest.json` in the S3 eval bucket to display the most recent run, and can show historical runs from `e2e-judge/results/{run-id}.json`. The admin sub-page at `/admin/tests` also shows test run history which may include e2e-judge runs.

### Alternative Ways to View Results

| Method | How |
|--------|-----|
| Admin dashboard (primary) | `/admin/e2e-judge` on the deployed app |
| Local markdown report | Open `data/e2e-judge/results/{run-id}-report.md` |
| Local JSON | Parse `data/e2e-judge/results/{run-id}.json` |
| S3 direct access | `aws s3 cp s3://eagle-eval-artifacts-695681773636-dev/e2e-judge/latest.json -` |
| Local screenshots | Browse `data/e2e-judge/screenshots/{run-id}/` directory |

---

## 8. Screenshot Strategy Details

The E2E Judge pipeline uses a deliberate, multi-layered screenshot strategy designed to catch issues at different phases of user interaction.

### 8.1 Standard Page Captures

For non-interactive pages (login, home, admin, documents, responsive), the strategy is straightforward:

1. **Navigate** to the target URL with `wait_until="networkidle"` (waits for all network requests to settle)
2. **Wait** an additional 2 seconds (`page.wait_for_timeout(2000)`) for client-side rendering, animations, and lazy-loaded content
3. **Capture** a full-page screenshot (`full_page=True` by default in `ScreenshotCapture.take()`) as raw PNG bytes
4. **Hash** the PNG bytes with SHA-256 for cache keying
5. **Store** the screenshot to `data/e2e-judge/screenshots/{run-id}/{journey}/{step}.png`

### 8.2 Pre-Send Captures (Chat Journey)

The chat journey captures screenshots **before** each message is sent. This is intentional:

- **Step `03_pre_send_1`**: After `textarea.fill("Hello, I need help with...")`, a screenshot is taken showing the composed message in the input field *before clicking send*. This validates:
  - The textarea is visible and accepts input
  - The message text renders correctly in the input field
  - The send button is visible and appears clickable
  - The overall chat UI layout is correct with content in the input

- **Step `09_pre_send_2`**: Same pattern for the follow-up message. This additionally validates that the input area resets and is reusable after the first response completes.

This pre-send pattern catches input rendering issues that would be invisible in post-send screenshots (e.g., textarea overflow, broken placeholder text, disabled send button).

### 8.3 30-Second Streaming Interval Captures (Chat Journey)

The most sophisticated part of the screenshot strategy handles the unpredictable agent response time. The `wait_with_interval_screenshots()` function (defined at line 34 of `e2e_judge_journeys.py`) implements a polling loop:

**How it works:**

1. After sending a message, the initial streaming state is captured at t+3s (`04_streaming_start`)
2. The function then enters a loop with these parameters:
   - `timeout_ms=120_000` (2 minute total timeout)
   - `interval_ms=30_000` (30 second screenshot interval)
   - `condition_fn=response_complete` (checks if the textarea is re-enabled, meaning the agent finished)
3. Every 2 seconds within each 30-second interval, it checks `condition_fn()`. If the agent response completes mid-interval, it exits immediately **without** taking an unnecessary interval screenshot
4. If the agent is still streaming when the 30-second interval elapses, it captures a screenshot named `{step_prefix}_{letter}_interval_{elapsed}s` (e.g., `05_a_interval_30s`, `05_b_interval_60s`)
5. The letter suffix uses `a-z` (then numeric indices beyond 26 -- though hitting that would mean a 13+ minute response)

**Why 30-second intervals:**

- Agent responses from the Strands SDK supervisor + subagent chain typically take 15-60 seconds
- 30 seconds balances capturing meaningful streaming progress against excessive screenshot volume
- Each interval shot validates: partial response rendering, streaming indicator visibility, no stuck loading states, correct message bubble formatting during streaming

**Screenshot naming for interval captures:**

```
05_a_interval_30s.png    -- First message, 30s elapsed, still streaming
05_b_interval_60s.png    -- First message, 60s elapsed, still streaming
05_c_interval_90s.png    -- First message, 90s elapsed, still streaming (rare)
11_a_interval_30s.png    -- Second message, 30s elapsed, still streaming
11_b_interval_60s.png    -- Second message, 60s elapsed, still streaming
```

**Condition function**: The `response_complete` async function checks `await textarea.is_enabled()`. During streaming, the EAGLE frontend disables the textarea to prevent additional input. When the agent response finishes, the textarea is re-enabled, signaling completion.

### 8.4 Responsive Viewport Captures

The responsive journey modifies the viewport before captures:

1. Sets viewport to **375x812** (iPhone-class mobile) via `page.set_viewport_size()`
2. Captures home, chat, and admin at mobile size
3. Sets viewport to **768x1024** (iPad-class tablet)
4. Captures the same 3 pages at tablet size
5. **Resets viewport to 1440x900** after completion (to avoid affecting subsequent journeys if run order changes)

### 8.5 Cache Interaction with Screenshots

Every screenshot is hashed with SHA-256 before the vision judge is invoked. This means:

- **Identical pixels = identical hash = cache hit**: If the UI hasn't changed since the last run, the judge evaluation is free (read from `data/e2e-judge/cache/{sha256}.json`)
- **Any pixel change = new hash = cache miss**: Even a 1-pixel difference (different timestamp, new notification badge, changed data) triggers a fresh Sonnet evaluation
- **Cache TTL is 7 days** (configurable via `E2E_JUDGE_CACHE_TTL_DAYS`): After 7 days, even identical screenshots are re-evaluated to guard against prompt/model changes affecting judgment quality
- **Screenshots are always saved** regardless of cache status: The PNG files are written to disk before cache lookup, so you always have the visual evidence even for cached judgments

### 8.6 Full-Page vs Viewport Screenshots

The `ScreenshotCapture.take()` method defaults to `full_page=True`, meaning Playwright captures the entire scrollable page, not just the visible viewport. This is important for:

- Long admin dashboards with data tables
- Chat conversations with extended message history
- Document lists that scroll beyond the fold

The only exception is the responsive journey, where viewport-constrained screenshots are more relevant (since the test is specifically about how content renders within the constrained viewport). However, even responsive captures use `full_page=True` to check for overflow content that shouldn't be there.
