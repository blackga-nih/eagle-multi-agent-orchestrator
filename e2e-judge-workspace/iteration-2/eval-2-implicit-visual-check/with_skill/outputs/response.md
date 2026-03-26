# E2E Judge -- Detailed Execution Plan for Implicit Visual Check

**User request**: "I just deployed a frontend change to the EAGLE app. Can you do a quick visual check of the admin dashboard and chat page to make sure nothing looks broken? Use the deployed URL."

---

## 1. How I Recognized This as an E2E Judge Task

The user never mentioned "e2e-judge" by name, but multiple signals in the request match the skill's trigger description. The SKILL.md file at `.claude/skills/e2e-judge/SKILL.md` explicitly states:

> Use this skill whenever someone asks to run E2E tests, **visual QA**, screenshot testing, **UI validation**, vision-based testing, or wants to **check if the deployed EAGLE app looks correct**. Also use when asked about "e2e judge", "screenshot judge", "visual regression", or "**UI quality check**".

The user's request hits three of these trigger phrases:

1. **"visual check"** -- maps directly to "visual QA" and "UI quality check" in the skill description.
2. **"make sure nothing looks broken"** -- maps to "check if the deployed EAGLE app looks correct."
3. **"Use the deployed URL"** -- signals this is against the real deployed environment, which is the primary use case for the e2e-judge pipeline (running against the ALB URL inside the VPC).

Additionally, the user named specific pages ("admin dashboard and chat page"), which correspond directly to registered journey names in the e2e-judge system (`admin` and `chat`). This is not a Playwright E2E test in the traditional assertion-based sense -- it is a vision-based screenshot evaluation pipeline, which is exactly what the e2e-judge skill provides.

If the user had said "run the Playwright tests" without mentioning visual/screenshot/quality, I would have leaned toward `npx playwright test` instead. The visual/quality language is the distinguishing factor.

---

## 2. Pre-Flight Checks I Would Run

Before executing the pipeline, I would run several pre-flight checks in parallel:

### Check A: Verify Python dependencies are installed

```bash
cd /c/Users/blackga/Desktop/eagle/sm_eagle/server && python -c "import playwright; import boto3; print('deps OK')"
```

**Why**: The skill requires `playwright` and `boto3`. If either is missing, the pipeline will fail immediately. Better to catch this before a long-running command.

### Check B: Verify Playwright browsers are installed

```bash
python -m playwright install --dry-run chromium 2>&1 | head -5
```

**Why**: The pipeline runs headless Chromium. If the browser binary is not installed, we need to run `playwright install chromium --with-deps` first.

### Check C: Verify AWS credentials are valid

```bash
aws sts get-caller-identity --profile eagle 2>&1
```

**Why**: The VisionJudge calls `bedrock-runtime:InvokeModel` via boto3. If credentials are expired (SSO session timeout), the judge phase will fail after screenshots are already captured, wasting time. The MEMORY.md confirms the `eagle` SSO profile is the daily-use profile with `NCIAWSPowerUserAccess`.

### Check D: Verify auth credentials are available

```bash
echo "EAGLE_TEST_EMAIL=${EAGLE_TEST_EMAIL:-(not set)}" && echo "EAGLE_TEST_PASSWORD=${EAGLE_TEST_PASSWORD:+(set)}"
```

**Why**: The pipeline authenticates against Cognito pool `us-east-1_ChGLHtmmp`. If env vars are not set, I would prompt the user for credentials rather than hardcoding them (the SKILL.md explicitly forbids hardcoding passwords).

### Check E: Verify the deployed URL is reachable

```bash
curl -s -o /dev/null -w "%{http_code}" "http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com" --max-time 10
```

**Why**: The ALB URL is internal to the VPC. If running from the EC2 dev box, this should return 200 or 302 (redirect to login). If it times out, the machine may not be inside the VPC, and we would need to troubleshoot connectivity before wasting time on the pipeline.

---

## 3. The Exact Bash Command(s) I Would Execute

```bash
cd /c/Users/blackga/Desktop/eagle/sm_eagle/server && \
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys admin,chat \
  -v
```

This is the single command I would run. If I needed to also push results to the S3 dashboard, I would append `--upload-s3`.

---

## 4. Every Flag and Why

### `--base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com`

**What it does**: Sets the target URL for Playwright navigation.

**Why this value**: The user said "use the deployed URL." The SKILL.md and orchestrator source code both show this internal ALB URL as the default value (line 332-335 of `e2e_judge_orchestrator.py`). It is also the value in the `BASE_URL` env var default. This is the internal ECS Fargate frontend service, accessible from within the VPC (EC2 dev box or VPN).

**Why not localhost**: The user explicitly said "deployed," ruling out `http://localhost:3000`.

**Why not omit it**: Although it is the default, being explicit avoids surprises if someone has `BASE_URL` set to a different value in their shell environment.

### `--journeys admin,chat`

**What it does**: Restricts the pipeline to only two of the six registered journeys.

**Why these two**: The user said "admin dashboard and chat page." The journey registry (from `e2e_judge_journeys.py`) contains these registered journey names:

| User's words | Mapped journey name | Rationale |
|---|---|---|
| "admin dashboard" | `admin` | Exact match. The `@journey("admin", "Admin dashboard and sub-pages (skills, templates, traces)")` decorator at line 300 of `e2e_judge_journeys.py` names this journey `admin`, and its description starts with "Admin dashboard." |
| "chat page" | `chat` | Exact match. The `@journey("chat", "Full chat interaction: send message, agent streaming, response, tool cards")` decorator at line 181 names this journey `chat`. |

**Why not `all`**: The user asked for a "quick visual check" of two specific pages, not a full regression. Running all six journeys (`login`, `home`, `chat`, `admin`, `documents`, `responsive`) would take significantly longer and cost more. The `all` default would capture ~40 screenshots; limiting to `admin,chat` captures roughly 16-22 screenshots instead.

**Why not include `login`**: The login journey runs implicitly as part of the authentication setup in `ScreenshotCapture.start()`. The `login` journey as a standalone test captures screenshots of the login page form itself -- the user did not ask to verify the login page.

**Why not include `home`**: The user specifically named "admin dashboard and chat page." Adding `home` would go beyond the request.

### `-v` (verbose)

**What it does**: Sets logging level to `DEBUG` instead of `INFO`.

**Why**: The user deployed a frontend change and wants to "make sure nothing looks broken." Verbose logging provides more diagnostic detail if something fails -- connection timeouts, Playwright navigation errors, Bedrock API issues, cache hit/miss details. For a post-deploy verification, extra visibility is valuable.

### Flags I deliberately omitted

| Flag | Why omitted |
|---|---|
| `--headed` | Not needed. Headless mode is correct for automated checks. `--headed` opens a visible browser window, which is only useful for interactive debugging. |
| `--purge-cache` | Not used. After a frontend deploy, the screenshots will likely have pixel-level differences from cached versions (new code = new renders), so cache misses will happen naturally. Purging would also destroy valid cache entries for unchanged pages. However, if the user had said "I'm not sure the cache is stale," I would add this flag. |
| `--upload-s3` | Not requested. The user asked for a quick check, not a dashboard upload. If I were to include it, I would inform the user that results are viewable at `/admin/e2e-judge` on the deployed app (per SKILL.md instruction). |
| `--output` | Not specified. The default output path `data/e2e-judge/results/` is correct for this repo. |
| `--auth-email` / `--auth-password` | Not passed on the command line. These should come from `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` environment variables. The SKILL.md says "Never hardcode passwords in commands -- use env vars or prompt the user for credentials." |

---

## 5. Expected Output and Verdict Meanings

### Console output during execution

The pipeline prints structured progress to stdout. Expected output for `admin,chat` journeys:

```
============================================================
E2E Judge Pipeline -- Run 20260326-154500
Target: http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com
Journeys: admin, chat
============================================================

--- Journey: admin ---

--- Journey: chat ---

--- Judging 19 screenshots ---

  [+] admin/01_dashboard: pass (score=8, cached=false)
  [+] admin/02_skills: pass (score=7, cached=false)
  [+] admin/03_templates: pass (score=8, cached=false)
  [+] admin/04_traces: pass (score=7, cached=false)
  [+] admin/05_tests: pass (score=8, cached=false)
  [+] admin/06_costs: pass (score=7, cached=false)
  [+] chat/01_chat_page: pass (score=9, cached=false)
  [+] chat/02_new_chat: pass (score=8, cached=false)
  [+] chat/03_pre_send_1: pass (score=8, cached=false)
  [+] chat/04_streaming_start: pass (score=7, cached=false)
  [+] chat/05_a_interval_30s: pass (score=7, cached=false)
  [+] chat/06_response_1_complete: pass (score=8, cached=false)
  [+] chat/07_response_1_scrolled: pass (score=8, cached=false)
  [+] chat/09_pre_send_2: pass (score=8, cached=false)
  [+] chat/10_streaming_2_start: pass (score=7, cached=false)
  [+] chat/12_response_2_complete: pass (score=8, cached=false)
  [+] chat/13_full_conversation: pass (score=8, cached=false)

============================================================
Results: 17 passed, 0 failed, 0 warnings
Avg quality score: 7.8/10
Cache: 0/17 hits (0%)
Cost:   $0.0680 (22720 in / 1700 out tokens)
Report: C:\Users\blackga\Desktop\eagle\sm_eagle\data\e2e-judge\results\20260326-154500-report.md
JSON:   C:\Users\blackga\Desktop\eagle\sm_eagle\data\e2e-judge\results\20260326-154500.json
============================================================
```

### Output artifacts

The pipeline produces four types of output:

| Artifact | Path | Description |
|---|---|---|
| Results JSON | `data/e2e-judge/results/{run-id}.json` | Full structured results with per-step verdicts |
| Latest JSON | `data/e2e-judge/results/latest.json` | Symlink/copy of most recent run for quick access |
| Markdown report | `data/e2e-judge/results/{run-id}-report.md` | Human-readable table with per-journey breakdowns |
| Screenshots | `data/e2e-judge/screenshots/{run-id}/{journey}/{step}.png` | Raw PNG captures from Playwright |

### Verdict definitions

Each screenshot receives one of three verdicts from the Sonnet vision judge:

**`pass` (score 7-10)**: The page looks correct and functional. Minor cosmetic issues (slight spacing inconsistencies, minor alignment quirks) are acceptable. This is the expected verdict for a healthy deploy. The judge evaluates layout, content, functionality, branding, accessibility, and error states. A "pass" means none of these criteria have meaningful issues.

**`warning` (score 4-6)**: Something looks off but the page is still usable. Examples: a missing element that should be present (e.g., sidebar missing a section), odd spacing or alignment issues, elements that are present but styled unexpectedly, slow-loading content that has not appeared yet. Warnings indicate areas worth investigating but are not necessarily blockers.

**`fail` (score 1-3)**: The page is broken. Examples: blank white screen, visible JavaScript error overlay, 404 page, content showing "undefined" or raw JSON, completely wrong page for the expected context, stuck loading spinner, overlapping elements making the page unusable. A fail on any step means the deploy likely introduced a regression.

### Confidence score (0.0 to 1.0)

Each judgment includes a confidence value indicating how certain the vision judge is about its verdict. Values above 0.85 are high-confidence; values between 0.5-0.85 suggest ambiguity (e.g., the page is partially loaded and it is unclear if it will finish). Low confidence on a "pass" might warrant manual review.

### UI quality score (1-10)

A holistic quality rating separate from the pass/fail binary. Even a "pass" can have a score of 7 (functional but rough) vs. 10 (polished). Tracking this over time reveals gradual UI quality drift.

### Issues array

A list of specific problems found. For "pass" verdicts, this is typically empty. For "warning" and "fail" verdicts, each issue is a string describing a concrete problem (e.g., "Sidebar navigation links are not visible," "Loading spinner has been showing for the entire screenshot duration").

### How I would interpret results for this task

For the user's "make sure nothing looks broken" request:

- **All pass, avg score >= 7**: "Both pages look good. No visual regressions detected. Here is the report: [path]."
- **Any warnings**: "The admin dashboard and chat page are functional, but the judge flagged [N] warnings: [summary of issues]. These may be worth reviewing. Screenshots are at [path]."
- **Any fails**: "The deploy may have introduced a regression. [N] screenshots failed visual QA: [summary]. The failed screenshots show [specific issues]. See the full report at [path] and screenshot evidence at [path]."

---

## 6. Cost Estimate and Cache Behavior

### Cost breakdown for this specific run

**Admin journey** produces approximately 6-7 screenshots:
- `01_dashboard` -- Admin main dashboard
- `02_skills` -- `/admin/skills` sub-page
- `03_templates` -- `/admin/templates` sub-page
- `04_traces` -- `/admin/traces` sub-page
- `05_tests` -- `/admin/tests` sub-page
- `06_costs` -- `/admin/costs` sub-page

**Chat journey** produces approximately 10-15+ screenshots:
- `01_chat_page` -- Initial chat page load
- `02_new_chat` -- After clicking New Chat
- `03_pre_send_1` -- First message typed, pre-send
- `04_streaming_start` -- 3 seconds after sending first message
- `05_a_interval_30s` through `05_d_interval_120s` -- 0-4 interval screenshots during streaming (depends on response time)
- `06_response_1_complete` -- First response done
- `07_response_1_scrolled` -- Scrolled to see full response
- `08_tool_cards` -- (conditional) If tool-use cards are visible
- `09_pre_send_2` -- Follow-up message typed, pre-send
- `10_streaming_2_start` -- 3 seconds after sending follow-up
- `11_a_interval_30s` through `11_d_interval_120s` -- 0-4 interval screenshots
- `12_response_2_complete` -- Second response done
- `13_full_conversation` -- Full conversation scrolled to bottom

**Total estimated screenshots**: 16-22

**Vision judge cost** (Sonnet via Bedrock converse):
- Each screenshot evaluation: ~1600 input tokens (image) + ~200 prompt tokens + ~150 output tokens
- Per-screenshot cost: ~$0.004 (input: 1800 tokens * $3/MTok = $0.0054, output: 150 tokens * $15/MTok = $0.0023) -- approximately $0.004 rounded
- **20 screenshots total: ~$0.08**

**EAGLE app cost** (Haiku 4.5 via Strands for the chat journey's two messages):
- Two chat turns at ~$0.001/response: ~$0.002
- This is the cost of the EAGLE app itself responding to the test messages

**Total estimated cost: ~$0.08-$0.10 for a fresh (uncached) run of admin + chat journeys.**

### Cache behavior

The cache is keyed by **SHA-256 hash of the raw PNG screenshot bytes**. This has important implications:

**First run after deploy (this scenario)**: Since the user just deployed a frontend change, most screenshots will produce pixel-level differences from any previously cached versions. This means:
- Admin pages that were visually unchanged by the deploy: cache hits (free)
- Admin pages with visual changes from the deploy: cache misses (Sonnet call)
- Chat pages: almost certainly cache misses, because chat content includes timestamps and dynamic data that differ between runs

In practice, a post-deploy run will likely see **0-30% cache hit rate** depending on how many pages were visually affected by the change.

**Repeat run (same deploy, no changes)**: If the pipeline is run again without any changes, the cache hit rate will be high for admin pages (static content) but lower for chat pages (dynamic timestamps and conversation content change the pixels). Expected cache hit rate: **50-80%**.

**Cache TTL**: 7 days by default (configurable via `E2E_JUDGE_CACHE_TTL_DAYS` env var). After 7 days, all entries expire and are treated as cache misses.

**Cache storage**: File-based at `data/e2e-judge/cache/{sha256}.json`. Each file contains the full `JudgmentResult` as JSON.

---

## 7. Screenshot Strategy Details

The e2e-judge pipeline uses two distinct screenshot timing strategies, both visible in the `chat` journey code:

### Strategy A: Pre-Send Captures (before each message)

**What**: A screenshot is taken with the user's message typed into the textarea but **before** the send button is clicked.

**Where in code**: Lines 212-213 (`03_pre_send_1`) and lines 261-262 (`09_pre_send_2`) of `e2e_judge_journeys.py`.

**Why**: This captures the input state, proving that:
1. The textarea is functional and accepts input
2. The message text is visible and properly rendered
3. The send button is present and presumably clickable
4. The chat UI layout is correct with a composed-but-unsent message

**What the judge evaluates**: The chat-specific prompt (`e2e_judge_prompts.py`, lines 65-79) tells Sonnet to look for "Text input area (textarea) at the bottom for user messages" and "Send button." The pre-send screenshot validates these elements are present and properly styled with actual content in the textarea.

**Screenshots produced**:
- `03_pre_send_1`: First message ("Hello, I need help with a simple acquisition under $10,000") typed in textarea
- `09_pre_send_2`: Follow-up message ("What forms do I need to fill out for a micro-purchase?") typed in textarea

### Strategy B: 30-Second Interval Screenshots During Streaming

**What**: While waiting for the EAGLE agent's response to complete, a screenshot is captured every 30 seconds.

**Where in code**: The `wait_with_interval_screenshots()` function (lines 34-107 of `e2e_judge_journeys.py`) is called at lines 229-238 (first message) and 272-280 (follow-up message).

**How it works in detail**:

1. After the send button is clicked, the function enters a polling loop.
2. Every 2 seconds (`check_interval = 2000`), it checks if `condition_fn()` returns True. The condition function is `response_complete()` (line 226-227), which checks `await textarea.is_enabled()` -- the textarea becomes enabled again when the agent finishes streaming.
3. Every 30 seconds (`interval_ms = 30_000`), if the condition has not been met, it captures a screenshot.
4. The total timeout is 120 seconds (`timeout_ms = 120_000`), giving a maximum of 4 interval screenshots per message (at 30s, 60s, 90s, 120s).
5. Screenshots are named with alphabetic suffixes: `05_a_interval_30s`, `05_b_interval_60s`, `05_c_interval_90s`, `05_d_interval_120s`.

**Why 30 seconds**: EAGLE agent responses can take 30-120+ seconds depending on the complexity of the query and whether specialist subagents are invoked. The 30-second interval captures the streaming progress without excessive screenshot overhead. It catches:
- The typing indicator / streaming cursor animation
- Partial response text appearing progressively
- Tool-use cards appearing during agent processing
- Any error states that appear mid-stream (connection drops, timeout errors)

**Why this matters for visual QA**: Streaming state is where many frontend bugs manifest -- layout shifts as content grows, flickering during partial renders, broken markdown rendering mid-stream, disappearing scroll position. Capturing at intervals rather than only before/after gives the judge visibility into these transient states.

**Screenshot naming convention**:

```
{step_prefix}_{suffix}_interval_{elapsed_seconds}s
```

Examples:
- `05_a_interval_30s` -- First message, 30 seconds into streaming
- `05_b_interval_60s` -- First message, 60 seconds into streaming
- `11_a_interval_30s` -- Follow-up message, 30 seconds into streaming

### Additional screenshot timing in the chat journey

Beyond pre-send and interval screenshots, the chat journey also captures:

| Step | Timing | Purpose |
|---|---|---|
| `01_chat_page` | After initial navigation + 2s wait | Baseline chat page layout |
| `02_new_chat` | After clicking New Chat button | Fresh session state |
| `04_streaming_start` | 3 seconds after first send | Early streaming state (typing indicator) |
| `06_response_1_complete` | After textarea re-enabled + 2s | Completed first response |
| `07_response_1_scrolled` | After scrolling to bottom | Full response visible (catches overflow issues) |
| `08_tool_cards` | Conditional, if tool cards detected | Tool-use card rendering |
| `10_streaming_2_start` | 3 seconds after follow-up send | Early streaming state for second turn |
| `12_response_2_complete` | After textarea re-enabled + 2s | Completed second response |
| `13_full_conversation` | After scrolling to bottom | Full multi-turn conversation view |

### Admin journey screenshot strategy

The admin journey is simpler -- no streaming or dynamic content. It takes one screenshot per page after a `networkidle` wait + 2 second buffer:

1. Navigate to URL
2. `wait_until="networkidle"` -- Playwright waits until no network requests for 500ms
3. `wait_for_timeout(2000)` -- Additional 2-second buffer for client-side rendering / animations
4. `capture.take()` -- Screenshot

This produces 6-7 screenshots total: the main dashboard plus each sub-page (skills, templates, traces, tests, costs).
