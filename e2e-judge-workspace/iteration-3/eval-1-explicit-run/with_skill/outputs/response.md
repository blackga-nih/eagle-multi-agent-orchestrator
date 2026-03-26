# E2E Judge Run: Login, Home, and Chat Journeys

## 1. Exact Command to Run

```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys login,home,chat
```

Since `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` are already set in your environment, the orchestrator will pick them up automatically. No `--auth-email` or `--auth-password` flags needed.

---

## 2. Flag-by-Flag Explanation

| Flag | Value | Why |
|------|-------|-----|
| `--base-url` | `http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com` | The deployed EAGLE ALB URL inside the VPC. This is the default in the orchestrator's argparse definition, so technically optional, but explicit is better. |
| `--journeys` | `login,home,chat` | Comma-separated list restricting the run to only these three journeys instead of the default `all` (which would also run admin, documents, responsive, acquisition_package). |

**Flags NOT used (and why):**
- `--headed` -- omitted because we want headless Chromium (faster, no display needed on EC2).
- `--purge-cache` -- omitted to benefit from any existing cached judgments. Add this flag if you want a fully fresh evaluation.
- `--upload-s3` -- omitted because this is a local check. Add it if you want results viewable at `/admin/e2e-judge` on the deployed app.
- `--output` -- omitted to use the default `data/e2e-judge/results/` directory.
- `-v` -- omitted for cleaner output. Add for DEBUG-level logging if troubleshooting.

---

## 3. Journey Details: Step-by-Step Breakdown

### 3.1 Login Journey (3 screenshots)

The login journey validates that Cognito authentication works and redirects properly.

| Step | Screenshot Name | What Happens |
|------|----------------|--------------|
| 1 | `01_initial_load` | Navigates to `base_url` root. Waits for `networkidle` + 2s. Captures whatever page appears -- either the login form or the home page if already authenticated. |
| 2a | `02_login_form` | If the URL contains `/login`, captures the Cognito login form showing email and password fields. |
| 2b | `02_authenticated` | If already past login (cached session or dev mode), captures the redirected state instead. |
| 3 | `03_post_auth_home` | Navigates to `base_url/` to confirm the auth flow completed. Captures the home page post-authentication. |

**Note:** The actual Cognito login (filling `#login-email`, `#login-password`, clicking submit) happens inside `ScreenshotCapture._authenticate()` during pipeline setup -- before any journey runs. The login journey screenshots capture the *page states*, not the auth interaction itself. Auth is performed once and the storage state is reused across all journeys.

### 3.2 Home Journey (4 screenshots)

The home journey validates the landing page layout, feature cards, and basic navigation.

| Step | Screenshot Name | What Happens |
|------|----------------|--------------|
| 1 | `01_home_page` | Navigates to `base_url/` with `networkidle` + 2s wait. Captures the full home page with welcome message and feature cards. |
| 2 | `02_sidebar` | Locates the first `<nav>`, `[role='navigation']`, or `<aside>` element. If found, captures the page showing the sidebar with session list and navigation links. |
| 3 | `03_card_navigation` | Locates elements matching `[data-testid*='card']`, `.feature-card`, or `a[href*='/chat']`. Clicks the first one and waits 2s. Captures the resulting page to verify navigation works. |
| 4 | `04_return_home` | Navigates back to `base_url/` to verify return navigation. Captures the home page after the round-trip. |

### 3.3 Chat Journey (10-15+ screenshots)

The chat journey is the most complex of the three. It tests a full multi-turn conversation with the EAGLE agent, including streaming state captures.

| Step | Screenshot Name | What Happens |
|------|----------------|--------------|
| 1 | `01_chat_page` | Navigates to `base_url/chat/` with `networkidle` + 2s. Captures the chat page with sidebar, input area, and quick action buttons. |
| 2 | `02_new_chat` | Clicks the "New Chat" button (if present) to start a fresh session. Captures the empty chat state. |
| 3 | `03_pre_send_1` | Types `"Hello, I need help with a simple acquisition under $10,000"` into the textarea. Captures the input area with the message typed **before** clicking send. |
| 4 | `04_streaming_start` | Clicks the send button, waits 3s. Captures the initial streaming state -- typing indicator or partial response should be visible. |
| 5 | `05_a_interval_30s` ... `05_d_interval_120s` | While waiting for the agent to finish responding (up to 120s timeout), captures a screenshot every 30 seconds. The condition checked every 2s: is the textarea re-enabled? Each interval screenshot gets a suffix (`_a`, `_b`, etc.) and an elapsed time label. **0-4 interval screenshots depending on response time.** |
| 6 | `06_response_1_complete` | After the textarea becomes enabled (response done), waits 2s, captures the completed first response. |
| 7 | `07_response_1_scrolled` | Scrolls to the bottom of the page via `window.scrollTo(0, document.body.scrollHeight)`. Captures the full first response scrolled into view. |
| 8 | `08_tool_cards` | Checks for elements matching `[data-testid*='tool']`, `.tool-card`, or `.tool-use-card`. If any tool use cards are visible, captures them. **Conditional -- only if tool cards exist.** |
| 9 | `09_pre_send_2` | Scrolls to bottom, types `"What forms do I need to fill out for a micro-purchase?"` into the textarea. Captures **before** sending the follow-up. |
| 10 | `10_streaming_2_start` | Clicks send, waits 3s. Captures the streaming state for the follow-up message. |
| 11 | `11_a_interval_30s` ... `11_d_interval_120s` | Same 30s interval screenshots while waiting for the second response. **0-4 interval screenshots.** |
| 12 | `12_response_2_complete` | Captures the completed second agent response. |
| 13 | `13_full_conversation` | Scrolls to the bottom of the page. Captures the full multi-turn conversation (both exchanges visible). |

---

## 4. Screenshot Strategy

### 4.1 Pre-Send Captures

The chat journey captures the input field **before** clicking send (steps `03_pre_send_1` and `09_pre_send_2`). This is intentional: it creates a visual record of exactly what the user typed, providing a baseline for evaluating whether the agent's response is contextually appropriate.

### 4.2 30-Second Interval Captures During Streaming

The `wait_with_interval_screenshots()` function implements a polling + capture loop:

1. **Check condition every 2 seconds**: Calls `condition_fn()` (which checks `textarea.is_enabled()`) every 2 seconds.
2. **Screenshot every 30 seconds**: After each 30-second interval passes without the condition being met, captures a screenshot.
3. **Timeout at 120 seconds**: For the chat journey, the total timeout is 120 seconds per message. If the agent hasn't finished by then, the wait loop exits.
4. **Naming convention**: Interval screenshots are named `{step_prefix}_{suffix}_interval_{elapsed}s` -- e.g., `05_a_interval_30s.png`, `05_b_interval_60s.png`.
5. **Early exit**: If the condition is met between interval captures (checked every 2s), the function returns immediately without taking another screenshot.

This strategy captures the streaming UI in progress -- partial agent responses, typing indicators, tool-use cards appearing -- providing the vision judge with evidence that streaming works correctly.

### 4.3 Full-Page Screenshots

All screenshots are captured with `full_page=True` by default (see `ScreenshotCapture.take()`). This means the entire scrollable page is captured, not just the viewport. The viewport is set to 1440x900 pixels.

### 4.4 SHA-256 Hashing

Every screenshot is hashed immediately after capture using SHA-256. The hash is printed to stdout in truncated form (e.g., `[capture] chat/03_pre_send_1 (a1b2c3d4e5f6...)`). These hashes are the cache keys for the vision judge -- if the same page renders identically on a repeat run, the cached judgment is reused for free.

---

## 5. Output Files

After the run completes, you will find these files:

### 5.1 Results JSON

```
data/e2e-judge/results/{run-id}.json       # Timestamped run results
data/e2e-judge/results/latest.json          # Symlink/copy to most recent run
```

The JSON contains aggregate metrics (pass/fail/warning counts, avg quality score, cache stats, token usage, cost) and per-journey step-level details with verdicts, reasoning, and issues.

### 5.2 Markdown Report

```
data/e2e-judge/results/{run-id}-report.md
```

A human-readable summary table with per-step verdicts, scores, and a listing of issues for any failed steps. Shows target URL, judge model, timestamp, and cache hit rate.

### 5.3 Screenshots

```
data/e2e-judge/screenshots/{run-id}/
  login/
    01_initial_load.png
    02_login_form.png          # or 02_authenticated.png
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
    05_a_interval_30s.png      # if response takes >30s
    05_b_interval_60s.png      # if response takes >60s
    06_response_1_complete.png
    07_response_1_scrolled.png
    08_tool_cards.png           # conditional
    09_pre_send_2.png
    10_streaming_2_start.png
    11_a_interval_30s.png      # if response takes >30s
    12_response_2_complete.png
    13_full_conversation.png
```

### 5.4 Cache

```
data/e2e-judge/cache/{sha256}.json
```

One JSON file per unique screenshot hash, containing the `JudgmentResult` (verdict, confidence, reasoning, ui_quality_score, issues, model_id, timestamp). TTL is 7 days by default. On repeat runs, identical-looking pages produce cache hits.

---

## 6. Cost Estimate

### 6.1 Vision Judge Cost (Sonnet)

The judge uses `us.anthropic.claude-sonnet-4-6-20250514-v1:0` via Bedrock converse.

- **Per screenshot**: ~$0.004 (each 1440x900 screenshot encodes to ~1,600 image tokens, plus the prompt text and JSON response)
- **Sonnet pricing**: $3.00/MTok input, $15.00/MTok output

**Expected screenshot count for login + home + chat:**

| Journey | Base Screenshots | Interval Screenshots (worst case) | Total |
|---------|------------------|------------------------------------|-------|
| login | 3 | 0 | 3 |
| home | 4 | 0 | 4 |
| chat | 9 (base) + 1 (conditional tool cards) | 0-8 (up to 4 per message wait) | 10-18 |
| **Total** | **16-17** | **0-8** | **17-25** |

**Cost range:**
- Best case (fast responses, no intervals): 17 screenshots x $0.004 = **~$0.07**
- Typical case (some streaming waits): ~20 screenshots x $0.004 = **~$0.08**
- Worst case (slow responses, max intervals): 25 screenshots x $0.004 = **~$0.10**
- Cached repeat run: **$0.00**

### 6.2 EAGLE App Cost (Haiku 4.5)

The chat journey sends 2 messages to the actual EAGLE app, which uses Haiku 4.5 (`STRANDS_MODEL_ID`):
- ~$0.001/response x 2 responses = **~$0.002**

### 6.3 Total Estimated Cost

**First run: ~$0.07-$0.10 total** (judge + app combined).
**Repeat run with identical UI: $0.002** (only app cost; judge hits cache).

---

## 7. What to Expect in the Results

### 7.1 Console Output During Run

You will see live output like:

```
============================================================
E2E Judge Pipeline -- Run 20260326-143000
Target: http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com
Journeys: login, home, chat
============================================================

  [capture] Chromium launched (headless=True)
  [capture] Logging in as test-user@eagle.nci.nih.gov...
  [capture] Authenticated successfully
  [capture] Screenshots will be saved to: data/e2e-judge/screenshots/20260326-143000

--- Journey: login ---
  [capture] login/01_initial_load (a1b2c3d4e5f6...)
  [capture] login/02_login_form (f6e5d4c3b2a1...)
  [capture] login/03_post_auth_home (1234abcd5678...)

--- Journey: home ---
  [capture] home/01_home_page (abcd1234efgh...)
  ...

--- Journey: chat ---
  [capture] chat/01_chat_page (...)
  [capture] chat/03_pre_send_1 (...)
  ...

--- Judging 20 screenshots ---

  [+] login/01_initial_load: pass (score=8, cached=False)
  [+] login/02_login_form: pass (score=9, cached=False)
  [+] login/03_post_auth_home: pass (score=8, cached=False)
  [+] home/01_home_page: pass (score=8, cached=False)
  ...
  [!] chat/04_streaming_start: warning (score=5, cached=False)
  [+] chat/06_response_1_complete: pass (score=8, cached=False)
  ...

============================================================
Results: 18 passed, 0 failed, 2 warnings
Avg quality score: 7.8/10
Cache: 0/20 hits (0%)
Cost:   $0.0800 (32000 in / 4000 out tokens)
Report: data/e2e-judge/results/20260326-143000-report.md
JSON:   data/e2e-judge/results/20260326-143000.json
============================================================
```

### 7.2 Per-Step Judgment Structure

Each screenshot judgment follows this structure in the results JSON:

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

Verdicts:
- **pass** (score 7-10): Page looks correct and functional. Minor cosmetic issues acceptable.
- **warning** (score 4-6): Something looks off but the page is usable. Missing elements, odd spacing.
- **fail** (score 1-3): Page is broken, blank, shows errors, or clearly wrong for expected context.

### 7.3 What the Vision Judge Evaluates

The Sonnet judge evaluates each screenshot against 6 criteria using journey-specific prompts:

1. **LAYOUT** -- proper structure, no overlapping elements, correct spacing, no overflows.
2. **CONTENT** -- real text (not "undefined", raw JSON, or stack traces).
3. **FUNCTIONALITY** -- buttons, inputs, dropdowns are visible and properly styled.
4. **BRANDING** -- EAGLE/NCI blue theme, consistent colors, proper header/sidebar.
5. **ACCESSIBILITY** -- sufficient contrast, readable font sizes, visual hierarchy.
6. **ERRORS** -- no blank screens, 404s, JS error overlays, or stuck spinners.

The `login`, `home`, and `chat` journeys each have dedicated prompt templates in `e2e_judge_prompts.py` that tell the judge what specific elements to expect (e.g., the chat prompt expects a textarea, send button, sidebar, EAGLE label on agent messages, streaming indicators).

### 7.4 Typical Outcomes

- **Login journey**: Usually 3 passes. A warning might appear if the login page takes a while to load or the redirect is slow.
- **Home journey**: Usually 3-4 passes. Warnings if feature cards are missing or sidebar fails to render.
- **Chat journey**: This is where most interesting results appear. Streaming screenshots (steps 4, 10, and interval shots) sometimes get "warning" verdicts because the page is in a transient state (typing indicator visible, partial response). The completed response screenshots (steps 6, 7, 12, 13) should be passes. A "fail" here would indicate a genuine UI problem (blank response, error overlay, broken layout).

### 7.5 Run Duration

- **Login + Home**: ~30 seconds total (page loads + screenshots).
- **Chat**: 1-5 minutes depending on agent response times (2 messages, each with up to 120s timeout, but usually completes in 15-60s per message).
- **Judging phase**: ~2-3 seconds per screenshot (Bedrock API call) for non-cached shots. With 17-25 screenshots, expect ~40-75 seconds for judging.
- **Total estimated duration**: **2-7 minutes**.

---

## 8. Troubleshooting

If the run fails, here are common issues:

| Symptom | Cause | Fix |
|---------|-------|-----|
| `RuntimeError: Auth required but no credentials` | Env vars not set | Verify `echo $EAGLE_TEST_EMAIL` and `echo $EAGLE_TEST_PASSWORD` return values |
| `RuntimeError: Login timed out` | Wrong credentials or Cognito issue | Check credentials against the `us-east-1_ChGLHtmmp` user pool |
| `playwright._impl._errors.Error: Executable doesn't exist` | Chromium not installed | Run `playwright install chromium --with-deps` |
| `botocore.exceptions.ClientError` on Bedrock | Missing IAM permissions | Ensure `bedrock:InvokeModel` access for `us.anthropic.claude-sonnet-4-6-20250514-v1:0` |
| `TimeoutError` during chat | Agent not responding | Check that the EAGLE backend is healthy at the ALB URL |

---

## 9. Optional Enhancements

If you want to modify the run:

```bash
# Fresh evaluation (ignore cache)
python -m tests.e2e_judge_orchestrator --journeys login,home,chat --purge-cache

# Upload results to S3 for the admin dashboard
python -m tests.e2e_judge_orchestrator --journeys login,home,chat --upload-s3

# Debug mode with visible browser + verbose logs
python -m tests.e2e_judge_orchestrator --journeys login,home,chat --headed -v

# Custom output directory
python -m tests.e2e_judge_orchestrator --journeys login,home,chat --output ./my-results/
```

After an `--upload-s3` run, results are viewable at `/admin/e2e-judge` on the deployed app.
