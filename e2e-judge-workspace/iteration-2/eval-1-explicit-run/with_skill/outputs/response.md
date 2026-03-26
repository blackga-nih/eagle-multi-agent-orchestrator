# E2E Judge Execution Plan: login, home, chat Journeys

## 1. Pre-Flight Checks

Before executing the pipeline, the following checks would be run to ensure the environment is ready:

### 1a. Verify environment variables are set

```bash
echo "EAGLE_TEST_EMAIL is ${EAGLE_TEST_EMAIL:+SET (${#EAGLE_TEST_EMAIL} chars)}" && \
echo "EAGLE_TEST_PASSWORD is ${EAGLE_TEST_PASSWORD:+SET (${#EAGLE_TEST_PASSWORD} chars)}"
```

**Why**: The orchestrator reads `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` from env vars (see `e2e_judge_orchestrator.py` lines 338-343 and `e2e_screenshot_capture.py` lines 48-49). If these are missing and the deployed app requires Cognito auth, `ScreenshotCapture._authenticate()` raises `RuntimeError("Auth required but no credentials...")` at line 84-87 of `e2e_screenshot_capture.py`.

### 1b. Verify Python dependencies are installed

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server && \
python -c "import playwright; import boto3; print('Dependencies OK')"
```

**Why**: The pipeline requires `playwright` (for Chromium-based screenshot capture) and `boto3` (for Bedrock converse calls to the Sonnet vision judge). These are listed as prerequisites in the SKILL.md.

### 1c. Verify Playwright Chromium is installed

```bash
npx playwright install chromium --with-deps 2>&1 | tail -5
```

**Why**: `ScreenshotCapture.start()` calls `self._pw.chromium.launch()`. If Chromium binaries are missing, Playwright throws a `BrowserType.launch` error. The `--with-deps` flag installs system-level dependencies (fonts, libraries) needed for headless rendering.

### 1d. Verify AWS credentials for Bedrock access

```bash
aws sts get-caller-identity --profile eagle 2>/dev/null || aws sts get-caller-identity
```

**Why**: `VisionJudge.__init__()` creates a `boto3.client("bedrock-runtime")` with region `us-east-1`. The judge calls `converse()` with the Sonnet model. AWS credentials must have `bedrock:InvokeModel` permission. On the EC2 dev box this comes from the instance role; locally it comes from the `eagle` SSO profile (account `695681773636`).

### 1e. Verify ALB is reachable

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com/
```

**Why**: The default `--base-url` points to the internal ALB. This is only reachable from within the VPC (EC2 dev box). If running locally outside the VPC, this will time out and you would need a different URL or VPN. A 200 or 302 (redirect to login) confirms the target is live.

### 1f. Check for existing cache (optional awareness)

```bash
ls C:/Users/blackga/Desktop/eagle/sm_eagle/data/e2e-judge/cache/ 2>/dev/null | wc -l
```

**Why**: The `JudgeCache` stores judgments as `{sha256}.json` files in `data/e2e-judge/cache/`. If prior runs exist and the UI hasn't changed, screenshots will produce the same SHA-256 hashes and get free cache hits (no Bedrock calls). This is informational only -- not blocking.

---

## 2. The Exact Command

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server && \
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys login,home,chat \
  -v
```

That is the single command. No other commands are needed.

---

## 3. Flag-by-Flag Explanation

| Flag | Value | Rationale |
|------|-------|-----------|
| `--base-url` | `http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com` | The deployed ALB URL. This is the hardcoded default in the CLI's argparse (line 329-333 of `e2e_judge_orchestrator.py`). Providing it explicitly makes the target visible in the command. |
| `--journeys` | `login,home,chat` | Restricts execution to the three requested journeys. Without this flag the default is `all`, which would also run `admin`, `documents`, and `responsive` -- adding ~15 more screenshots and unnecessary cost/time. The comma-separated format is parsed by `args.journeys.split(",")` at line 362. |
| `-v` | (flag, no value) | Enables `logging.DEBUG` level (line 357-359). This surfaces per-screenshot SHA-256 hashes, Bedrock converse calls, cache hit/miss decisions, and timing info. Useful for a first run to confirm the pipeline is working correctly. |
| `--auth-email` | **OMITTED** | Not passed because the orchestrator falls back to `os.environ.get("EAGLE_TEST_EMAIL")` at line 340. Since the user confirmed these env vars are already set, explicit flags are unnecessary and would risk the password appearing in shell history. |
| `--auth-password` | **OMITTED** | Same as above -- reads from `EAGLE_TEST_PASSWORD` env var (line 343). Never hardcode credentials on the command line. |
| `--headed` | **OMITTED** | Not passed, so `headless=True` (default). The browser runs invisibly. You would only add `--headed` for debugging a failing journey where you need to watch the browser navigate. |
| `--purge-cache` | **OMITTED** | Not passed, so existing cache entries are preserved. This is the right default: if the UI hasn't changed, cached judgments save Bedrock API calls. You would add `--purge-cache` only if you suspect stale cache entries (e.g., after a deploy that changed the UI). |
| `--upload-s3` | **OMITTED** | Not passed, so results stay local. S3 upload would push to `s3://eagle-eval-artifacts-695681773636-dev/e2e-judge/` and make results visible at `/admin/e2e-judge` on the deployed app. Add this flag when you want the team to see results. |
| `--output` | **OMITTED** | Not passed, so results go to the default: `{repo_root}/data/e2e-judge/results/` (line 67-68 of the orchestrator). This keeps results alongside screenshots in the standard `data/` directory. |

---

## 4. Expected Output

### 4a. Console Output (stdout)

The pipeline prints a structured flow. Here is what you would see for these three journeys:

```
============================================================
E2E Judge Pipeline -- Run 20260326-143052
Target: http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com
Journeys: login, home, chat
============================================================

  [capture] Chromium launched (headless=True)
  [capture] Logging in as testuser@example.com...
  [capture] Authenticated successfully
  [capture] Screenshots will be saved to: C:/Users/blackga/Desktop/eagle/sm_eagle/data/e2e-judge/screenshots/20260326-143052

--- Journey: login ---
  [capture] login/01_initial_load (a3f2c8d91b4e...)
  [capture] login/02_login_form (7e1a5f3b2c0d...)
  [capture] login/03_post_auth_home (b8d4e2f1a6c3...)

--- Journey: home ---
  [capture] home/01_home_page (c1d9e7f3a5b2...)
  [capture] home/02_sidebar (d2e8f6a4b1c0...)
  [capture] home/03_card_navigation (e3f7a5b9c2d1...)
  [capture] home/04_return_home (f4a6b8c0d3e2...)

--- Journey: chat ---
  [capture] chat/01_chat_page (1a2b3c4d5e6f...)
  [capture] chat/02_new_chat (2b3c4d5e6f7a...)
  [capture] chat/03_pre_send_1 (3c4d5e6f7a8b...)
  [capture] chat/04_streaming_start (4d5e6f7a8b9c...)
  [capture] chat/05_a_interval_30s (5e6f7a8b9c0d...)
  [capture] chat/06_response_1_complete (6f7a8b9c0d1e...)
  [capture] chat/07_response_1_scrolled (7a8b9c0d1e2f...)
  [capture] chat/09_pre_send_2 (8b9c0d1e2f3a...)
  [capture] chat/10_streaming_2_start (9c0d1e2f3a4b...)
  [capture] chat/11_a_interval_30s (0d1e2f3a4b5c...)
  [capture] chat/12_response_2_complete (1e2f3a4b5c6d...)
  [capture] chat/13_full_conversation (2f3a4b5c6d7e...)
  [capture] Done. 17 screenshots captured.

--- Judging 17 screenshots ---

  [+] login/01_initial_load: pass (score=8, cached=False)
  [+] login/02_login_form: pass (score=8, cached=False)
  [+] login/03_post_auth_home: pass (score=9, cached=False)
  [+] home/01_home_page: pass (score=9, cached=False)
  [+] home/02_sidebar: pass (score=8, cached=False)
  [+] home/03_card_navigation: pass (score=7, cached=False)
  [+] home/04_return_home: pass (score=9, cached=False)
  [+] chat/01_chat_page: pass (score=9, cached=False)
  [+] chat/02_new_chat: pass (score=8, cached=False)
  [+] chat/03_pre_send_1: pass (score=8, cached=False)
  [+] chat/04_streaming_start: pass (score=7, cached=False)
  [+] chat/05_a_interval_30s: pass (score=7, cached=False)
  [+] chat/06_response_1_complete: pass (score=9, cached=False)
  [+] chat/07_response_1_scrolled: pass (score=8, cached=False)
  [+] chat/09_pre_send_2: pass (score=8, cached=False)
  [+] chat/10_streaming_2_start: pass (score=7, cached=False)
  [+] chat/12_response_2_complete: pass (score=9, cached=False)

============================================================
Results: 17 passed, 0 failed, 0 warnings
Avg quality score: 8.1/10
Cache: 0/17 hits (0%)
Cost:   $0.0680 (17200 in / 850 out tokens)
Report: C:/Users/blackga/Desktop/eagle/sm_eagle/data/e2e-judge/results/20260326-143052-report.md
JSON:   C:/Users/blackga/Desktop/eagle/sm_eagle/data/e2e-judge/results/20260326-143052.json
============================================================
```

**Notes on the console output**:
- The `[+]`, `[X]`, `[!]` icons map to pass, fail, and warning verdicts (line 149 of orchestrator).
- The `cached=False` on a first run means every screenshot triggered a Bedrock converse call. On a second identical run, you would see `cached=True` and `$0.0000` cost.
- The exact number of chat screenshots depends on how long streaming takes. If both responses complete within 30 seconds each, there will be zero interval screenshots (the `wait_with_interval_screenshots` function returns early). If a response takes 45 seconds, you get one interval screenshot. If it takes 75 seconds, you get two.

### 4b. Files Produced

All files land under the repo root at `C:/Users/blackga/Desktop/eagle/sm_eagle/`:

#### Results JSON

| File | Path |
|------|------|
| Run-specific | `data/e2e-judge/results/{run-id}.json` |
| Latest symlink | `data/e2e-judge/results/latest.json` |

The JSON contains the full results structure: run metadata, per-journey breakdowns, per-step verdicts with scores and reasoning, and aggregate cache/cost stats.

#### Markdown Report

| File | Path |
|------|------|
| Run report | `data/e2e-judge/results/{run-id}-report.md` |

A human-readable report with a summary table (total screenshots, pass/fail/warning counts, average quality score, cache hit rate, token usage, cost) and per-journey step tables showing step name, verdict, score, and reasoning.

#### Screenshots (PNG files)

```
data/e2e-judge/screenshots/{run-id}/
  login/
    01_initial_load.png
    02_login_form.png           (or 02_authenticated.png if no login page)
    03_post_auth_home.png
  home/
    01_home_page.png
    02_sidebar.png
    03_card_navigation.png
    04_return_home.png
  chat/
    01_chat_page.png
    02_new_chat.png
    03_pre_send_1.png           ** pre-send capture **
    04_streaming_start.png
    05_a_interval_30s.png       ** 30s interval shot (if streaming > 30s) **
    05_b_interval_60s.png       ** 60s interval shot (if streaming > 60s) **
    06_response_1_complete.png
    07_response_1_scrolled.png
    08_tool_cards.png            (only if tool use cards visible)
    09_pre_send_2.png           ** pre-send capture **
    10_streaming_2_start.png
    11_a_interval_30s.png       ** 30s interval shot (if streaming > 30s) **
    12_response_2_complete.png
    13_full_conversation.png
```

All screenshots are full-page PNGs at 1440x900 viewport (the default in `ScreenshotCapture.__init__`, `full_page=True` in `take()`).

#### Cache Files

```
data/e2e-judge/cache/
  {sha256_of_screenshot_1}.json
  {sha256_of_screenshot_2}.json
  ...
```

Each is a JSON file containing the `JudgmentResult` dataclass fields (verdict, confidence, reasoning, ui_quality_score, issues, timestamp, model_id, cached, step_name, journey). These persist for 7 days (default `E2E_JUDGE_CACHE_TTL_DAYS`).

---

## 5. Cost Estimate

### Vision Judge Cost (Sonnet via Bedrock)

The vision judge uses `us.anthropic.claude-sonnet-4-6-20250514-v1:0` via Bedrock converse.

**Bedrock Sonnet pricing** (us-east-1, per the `VisionJudge.stats` property at lines 182-183):
- Input: $3.00 / million tokens
- Output: $15.00 / million tokens

**Per-screenshot breakdown**:
- Each screenshot at 1440x900 consumes approximately 1,600 image tokens (as noted in the code comment at line 185).
- The text prompt adds approximately 150-300 tokens depending on the journey-specific prompt.
- Total input per screenshot: ~1,800-1,900 tokens.
- Output per screenshot: ~50-80 tokens (just the JSON judgment object).
- **Cost per screenshot**: ~$0.004 (matches SKILL.md estimate).

**For login + home + chat (3 journeys)**:

| Journey | Expected Screenshots (no cache) | Notes |
|---------|---------------------------------|-------|
| login | 3 | Always exactly 3 steps |
| home | 4 | 4 steps (sidebar may or may not appear; feature card click may or may not match) |
| chat | 10-15 | Variable: depends on streaming duration (30s interval shots) and tool card visibility |
| **Total** | **17-22** | |

**Estimated cost range**:
- Low (17 screenshots, all cached from prior run): **$0.00**
- Typical first run (17 screenshots, no cache): **~$0.07**
- High (22 screenshots, slow streaming, no cache): **~$0.09**

### EAGLE App Cost (Haiku 4.5 for chat responses)

The chat journey sends two real messages to the deployed EAGLE app, which uses Haiku 4.5 (set via `STRANDS_MODEL_ID`):
- 2 messages x ~$0.001/response = **~$0.002**

### Total Estimated Cost

| Scenario | Judge Cost | App Cost | Total |
|----------|-----------|----------|-------|
| First run (no cache) | $0.07-$0.09 | $0.002 | **~$0.07-$0.09** |
| Repeat run (full cache) | $0.00 | $0.002 | **~$0.002** |
| Partial cache (UI changed on some pages) | $0.02-$0.05 | $0.002 | **~$0.02-$0.05** |

---

## 6. Screenshot-Related Details

### 6a. Pre-Send Captures

The chat journey takes explicit "pre-send" screenshots -- capturing the state of the UI with the user's message typed into the textarea but **before** clicking the send button. This happens at two points:

1. **Step `03_pre_send_1`** (line 213 of `e2e_judge_journeys.py`):
   - The textarea is filled with `"Hello, I need help with a simple acquisition under $10,000"`.
   - A screenshot is taken showing the message in the input area.
   - Purpose: Verifies the textarea is visible, properly styled, and shows the typed text. The judge evaluates that the input area looks correct and the text is readable.

2. **Step `09_pre_send_2`** (line 261):
   - The textarea is filled with `"What forms do I need to fill out for a micro-purchase?"`.
   - Screenshot taken before clicking send.
   - Purpose: Same as above, but also validates that the previous conversation is visible above the input area.

The pre-send pattern is important because it captures a moment that would be lost otherwise -- the judge can verify that the input field works correctly and that the message composition UX is intact.

### 6b. 30-Second Interval Shots During Streaming

The `wait_with_interval_screenshots()` function (lines 34-107 of `e2e_judge_journeys.py`) implements a polling-with-capture pattern during agent response streaming:

**How it works**:
1. A `condition_fn` is provided -- for chat, this is `response_complete()` which checks `await textarea.is_enabled()` (lines 226-227). When the agent finishes streaming, the textarea re-enables.
2. The function enters a loop with `timeout_ms=120_000` (2 minutes max wait) and `interval_ms=30_000` (30-second snapshot intervals).
3. Within each 30-second interval, it checks the condition every 2 seconds (`check_interval = 2000` at line 81). If the condition becomes true during any 2-second check, it returns immediately **without** taking an interval screenshot.
4. If 30 seconds pass without the condition being met, it takes a screenshot named `{step_prefix}_{suffix}_interval_{elapsed_sec}s` where suffix cycles through `a`, `b`, `c`, etc.

**Concrete example for the first message**:
- `step_prefix="05"`, starting after the `04_streaming_start` screenshot.
- If the response completes in 15 seconds: **zero** interval screenshots taken. The function returns an empty list.
- If the response takes 45 seconds: **one** interval screenshot at ~30s elapsed, named `05_a_interval_30s`.
- If the response takes 95 seconds: **three** interval screenshots at ~30s, ~60s, ~90s, named `05_a_interval_30s`, `05_b_interval_60s`, `05_c_interval_90s`.
- If the response takes >120 seconds: the loop exits at the timeout boundary, with up to 3 interval screenshots captured.

The same pattern repeats for the second message with `step_prefix="11"`.

**What the judge evaluates in interval screenshots**:
- The chat-specific judge prompt (from `e2e_judge_prompts.py`) mentions "If streaming: typing indicator (bouncing dots) or streaming cursor" as an expected element.
- Interval screenshots capture the mid-stream state: partial agent text, streaming cursor, tool-use cards appearing in real time.
- This validates that streaming rendering works correctly and doesn't produce visual artifacts, blank areas, or error states mid-flight.

### 6c. Screenshot Hashing and Cache Interaction

Every screenshot is hashed with SHA-256 immediately on capture (`compute_sha256(screenshot_bytes)` at line 155 of `e2e_screenshot_capture.py`). The hash is printed to the console as a 12-character prefix (e.g., `a3f2c8d91b4e...`).

During the judging phase, the same bytes are read from disk, rehashed, and checked against the file-based cache in `data/e2e-judge/cache/`. This means:
- **Static pages** (login form, home page, sidebar) will cache well across runs -- same pixels produce the same hash.
- **Dynamic pages** (chat responses, streaming states) will almost never cache -- the response content changes each run, producing different pixels and different hashes.
- **Interval screenshots** are inherently uncacheable -- they capture a moment in time during streaming that will never reproduce exactly.

### 6d. Viewport and Full-Page Behavior

- Default viewport: **1440x900** pixels (set in `ScreenshotCapture.__init__` lines 39-40).
- All screenshots use `full_page=True` (line 150 of the `take()` method), which means Playwright captures the entire scrollable content, not just the viewport. A long chat conversation could produce a screenshot much taller than 900px.
- The chat journey explicitly scrolls to bottom (`page.evaluate("window.scrollTo(0, document.body.scrollHeight)")`) before certain captures (steps 07 and 13) to ensure the latest content is in view for both the screenshot and any viewport-only checks.
