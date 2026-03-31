---
name: mvp1-eval
description: Run the EAGLE evaluation ladder — Python unit/integration tests, Strands/Bedrock eval suite (test_strands_eval.py), and Playwright frontend checks (structural, live SSE/tool UI, optional e2e-judge visual QA). Uses repo-keyed config; aligns traces with Langfuse when credentials exist.
model: sonnet
---

# EAGLE MVP1 Eval Skill

Curated ladder for the acquisition workflow stack: **Tier 1** fast unit tests, **Tier 2** live Strands/Bedrock integration, **Tier 3** full Strands eval driver, **Tier 4** frontend in three bands (structural, live streaming/tool UI, visual QA).

## Validation loop (run every time)

1. **Load config** — `.claude/skills/mvp1-eval/config.json` for this repo basename; no hardcoded Langfuse project IDs in prose (use `langfuse_project_id` from config or `LANGFUSE_PROJECT_ID` from `env_file`).
2. **Pre-flight (AWS)** — **Mandatory** before **Tier 2+**, **Tier 4-live**, and **Tier 4b** (any run that hits Bedrock, live backend/SSE, or e2e-judge). **Skip** AWS checks for **Tier 1 only** (or Tier 1 + **4a** structural) so local pytest can run without credentials. If the planned run includes Tier 2+, 4-live, or 4b and `aws sts get-caller-identity` fails, abort with a clear message (`aws sso login --profile ...`); do not start those tiers.
3. **Execute tiers** in order; **after each tier** record pass/fail counts, duration, and failing test names.
4. **Gate** — default: stop before Tier 3 unless `--full` or `--tier 3`; stop before Tier 4b visual unless `--full` or `--visual` (or `--tier 4b`).
5. **Correlate** — for any tier that hit Bedrock, bracket timestamps and pull Langfuse traces (Phase 4).
6. **Score** — apply [Scoring and report thresholds](#scoring-and-report-thresholds) below; flag regressions.
7. **Notify** — only if `TEAMS_WEBHOOK_URL` or `ERROR_WEBHOOK_URL` is set in `env_file` (see [Notifications](#notifications)); never embed or default a webhook URL in code or copy-paste snippets.

## Canonical sources

| Kind | Path | Notes |
|------|------|--------|
| **Strands eval suite (source of truth for inventory)** | `server/tests/test_strands_eval.py` | Numbered scenarios, CLI (`--tests`, `--model`, …); docstring at top describes phases. **Do not assume a fixed test count** — the file grows; cross-check `server/tests/eval_aws_publisher.py` `_TEST_NAMES` for CloudWatch name mapping (keep in sync when adding tests). |
| **Demo scripts** | `EAGLE-DEMO-SCRIPT-UPDATED.md` (primary), `EAGLE-DEMO-SCRIPT.md` (legacy) | Multi-turn UC content for demos and eval scenarios; paths also listed in config `demo_script_paths`. |
| **e2e-judge** | `server/tests/e2e_judge_orchestrator.py`, `server/tests/e2e_judge_journeys.py` | Vision judge over Playwright screenshots; journey list in config `tier4b_journeys`. |
| **Playwright eval config** | `client/tests/eval-playwright.config.ts` | Chromium, screenshots for eval runs. |
| **Skill config** | `.claude/skills/mvp1-eval/config.json` | Per-repo paths, tiers, Langfuse host/project id, demo paths, optional report scripts. |

### Other useful references (short)

- **Tier 1** files: `test_compliance_matrix.py`, `test_chat_kb_flow.py`, `test_canonical_package_document_flow.py`, `test_document_pipeline.py`.
- **Tier 2** files: `test_strands_multi_agent.py`, `test_strands_poc.py`, `test_strands_service_integration.py`.
- **Backend orchestration**: `server/app/strands_agentic_service.py`; **compliance**: `server/app/compliance_matrix.py`.

### Langfuse UI

Build links as `{langfuse_host}/project/{langfuse_project_id}/traces/...` using values from **config** and/or `server/.env`. Do not use stale project slugs from old docs.

---

## Step 0: Load repo config

```bash
REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
echo "Repo: $REPO_NAME"
```

Read `.claude/skills/mvp1-eval/config.json` → entry for `$REPO_NAME`, else `_template` fields as hints and fallbacks.

| Variable | Config key | Notes |
|----------|------------|--------|
| `AWS_PROFILE` | `aws_profile` | Default `eagle` |
| `S3_BUCKET` | `s3_bucket` | From config |
| `SERVER_DIR` | `server_dir` | Usually `server` |
| `CLIENT_DIR` | `client_dir` | Usually `client` |
| `ENV_FILE` | `env_file` | Usually `server/.env` |
| `LANGFUSE_HOST` | `langfuse_host` | Plus `LANGFUSE_PROJECT_ID` in env for API URLs |
| `LANGFUSE_PROJECT_ID` | `langfuse_project_id` | Prefer config; env overrides for local |
| `TIER1_TESTS` | `tier1_tests[]` | pytest paths under `SERVER_DIR` |
| `TIER2_TESTS` | `tier2_tests[]` | |
| `TIER3_TEST` | `tier3_test` | `tests/test_strands_eval.py` |
| `TIER4A_TESTS` | `tier4a_tests[]` | Structural Playwright specs (filenames) |
| `TIER4_LIVE_TESTS` | `tier4_live_tests[]` | Live backend/SSE/tool specs |
| `TIER4A_PROJECT` | `tier4a_project` | e.g. `chromium` |
| `TIER4B_JOURNEYS` | `tier4b_journeys[]` | e2e-judge |
| `E2E_JUDGE` | `e2e_judge_orchestrator` | Module path under server |
| `DEMO_SCRIPTS` | `demo_script_paths[]` | Repo-relative markdown |
| `REPORT_SCRIPTS` | `report_generator_scripts[]` | Optional helpers (e.g. `server/tests/generate_eval_report.py`, `server/tests/generate_mt_report.py`; repo may also list legacy paths) |

If the repo key is missing, warn and use sensible defaults; do not abort.

---

## Pre-flight

1. **AWS** — **not required** for **Tier 1** alone (or Tier 1 + **4a** structural Playwright). **Required** before **Tier 2+**, **Tier 4-live**, and **Tier 4b** (Bedrock, live SSE/backend, e2e-judge). When any of those tiers are in scope, run:

```bash
aws sts get-caller-identity --profile "$AWS_PROFILE" 2>&1
```

On failure, print a clear abort message (`aws sso login --profile ...`) and **do not** start Tier 2+, Tier 3, Tier 4-live, or Tier 4b. **Tier 1** may still run first without AWS if you are gating that way.

2. **Server tests**: `cd "$SERVER_DIR"`.

---

## Tier 1 — Unit tests (no Bedrock)

```bash
python -m pytest "${TIER1_TESTS[@]}" -v --tb=short
```

Expect a large fast suite (compliance, KB flow, package routing, document pipeline). Report pass/total and time.

---

## Tier 2 — Integration (Bedrock / Strands)

```bash
AWS_PROFILE="$AWS_PROFILE" python -m pytest "${TIER2_TESTS[@]}" -v --tb=short -x
```

Roughly six tests across the three files (supervisor routing, UC-02 POC, SDK adapter). ~minutes with valid credentials.

---

## Tier 3 — Full Strands eval (`test_strands_eval.py`)

**Inventory is not fixed** — the authoritative list is the suite file itself (async tests + numbering), with `_TEST_NAMES` in `eval_aws_publisher.py` for telemetry naming.

```bash
AWS_PROFILE="$AWS_PROFILE" python -m pytest "$TIER3_TEST" -v --tb=short -x
```

**Collection note:** `test_strands_eval.py` parses CLI args at import time. If pytest collection fails, run the module as a script per that file’s `if __name__ == "__main__"` / README-style invocation, or use the documented flags in the file header.

**When to run:** `--full`, `--tier 3`, or after Tier 1+2 pass and the user explicitly wants the long run (often ~tens of minutes; cost on Bedrock).

### Strands-native evaluation guidance (for new harnesses)

When extending evals alongside the Strands Agents SDK, prefer SDK-aligned patterns over one-off asserts:

- **ActorSimulator** — deterministic user turns and edge prompts (multi-turn, tool-forcing, abstention).
- **TrajectoryEvaluator** — end-to-end session scoring over full agent traces (not only final text).
- **Tool selection / parameter evaluators** — assert correct tool choice and structured args vs rubric (e.g. compliance matrix before routing, correct S3 keys).
- **StrandsEvalsTelemetry** — emit structured run summaries so CloudWatch / Langfuse / dashboards stay consistent with `publish_eval_metrics` / trace validators in-repo.

Reuse existing helpers where possible: `eval_helpers.py` (`LangfuseTraceValidator`, `ToolChainValidator`, etc.) and patterns in `test_strands_eval.py`.

---

## Tier 4 — Frontend

Resolve `BASE_URL` first: env override → probe `http://localhost:3000` → deployed default from `client/playwright.config.ts` if needed. Export as `RESOLVED_BASE_URL`.

### 4a — Structural / mock-friendly Playwright

Low dependency on a live agent: layout, navigation, admin shells, many chat **shell** checks. Uses `tier4a_tests` + `eval-playwright.config.ts`.

```bash
cd "$CLIENT_DIR" && BASE_URL="$RESOLVED_BASE_URL" npx playwright test \
  "${TIER4A_TESTS[@]}" \
  --project="$TIER4A_PROJECT" \
  --config=tests/eval-playwright.config.ts \
  --reporter=list
```

Treat connection failures to `localhost:8000` as **skipped / environment** when the intent is structural-only; do not count as product regressions without a running API.

### 4-live — Live SSE, streaming, tool cards

Requires **reachable frontend + backend** (and typically Bedrock or full stack). Uses `tier4_live_tests` from config (SSE pipeline, `validate-chat-v2*`, tool panels, streaming persistence/render, activity counts, session/thread isolation, etc.).

Same `playwright` invocation pattern as 4a, substituting the live spec list. Run when validating releases or after backend deploys; skip in CI that lacks the stack.

### 4b — Visual QA (e2e-judge)

Optional; Bedrock vision cost. **Only** with `--full`, `--visual`, or `--tier 4b`.

```bash
# If EAGLE_TEST_EMAIL / EAGLE_TEST_PASSWORD are in server/.env, add:
#   --auth-email ... --auth-password ...
cd "$SERVER_DIR" && python -m tests.e2e_judge_orchestrator \
  --base-url "$RESOLVED_BASE_URL" \
  --journeys "$(IFS=,; echo "${TIER4B_JOURNEYS[*]}")"
```

Read `data/e2e-judge/results/latest.json` for pass/fail, `avg_quality_score`, `cache_stats`, cost.

---

## Scoring and report thresholds

Use these dimensions in written reports (adjust numbers with team agreement):

| Dimension | What to measure | Suggested threshold / notes |
|-----------|-------------------|-----------------------------|
| **Conversation / session** | Turn coherence, handoffs, session resume, Langfuse session linkage | **Pass** = Tier 3 session/history tests green + no orphan traces for the run window |
| **Tool-call** | Correct tool, argument shape, success vs error observations | **Pass** = ToolChainValidator / eval rubrics in Tier 3; flag **recovered** errors separately from hard fails |
| **Frontend** | 4a structural pass rate; 4-live pass when stack available | **4a** target 100% with reachable app; **4-live** allow skips only for documented missing env |
| **Confidence / quality** | e2e-judge `avg_quality_score` (1–10), content-quality tests in Tier 3 | **Warn** if avg < 7; **fail** if < 5 or any journey `failed` on release gates |
| **Overall release bar** | Tiers run for the gate | **Ship candidate**: Tier 1 + 2 + 4a all pass; Tier 3 per release policy; 4-live pass on staging; 4b per policy |

Always report wall-clock per tier and aggregate **failed test names** with one-line errors.

---

## Arguments (conventions)

| Flag | Behavior |
|------|----------|
| `--full` | All tiers including Tier 3 and 4b |
| `--tier N` | `1`, `2`, `3`, `4a`, `4live`, `4b` |
| `--visual` | Include 4b |
| `--base-url URL` | Frontend target |
| `--mvp N` | Filter when tests expose MVP markers (most Strands evals are mixed; prefer `--tests` in `test_strands_eval.py` for precision) |
| `--reauth` | `aws sso login` before AWS tiers |
| *(default)* | Tier 1 + 2 + 4a |

---

## Reporting checklist

After each tier: passes, failures, skips, duration. Accumulate:

- `tier1_*`, `tier2_*`, `tier3_*`, `tier3_run`
- `tier4a_*`, `tier4live_*`, `tier4live_run`
- `tier4b_*`, `tier4b_run`, `tier4b_avg_score`, judge cost from cache stats
- `failed_tests[]`, `elapsed_seconds`

### Langfuse (after Bedrock tiers)

Load `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `LANGFUSE_PROJECT_ID` from `ENV_FILE`. Query traces in **UTC** between run start/end. Token usage: sum **GENERATION** observations, not trace-level `usage`. Subagent: `metadata.attributes["eagle.subagent"]`. Trace link: `{LANGFUSE_HOST}/project/{LANGFUSE_PROJECT_ID}/traces/{id}`.

If Langfuse is unset, state that explicitly and skip trace sections.

### Report table template

Use **dynamic** totals for Tier 3 and Tier 4 rows (never hardcode “42 tests”). Example:

```markdown
| Tier | Passed | Failed | Skipped | Time |
|------|--------|--------|---------|------|
| 1 | … | … | … | … |
| 2 | … | … | … | … |
| 3 | … | … | … | … |
| 4a | … | … | … | … |
| 4-live | … | … | … | … |
| 4b | … | … | … | … |
```

---

## Notifications

**Do not** use a baked-in or “default” webhook URL. Post Teams/Adaptive Cards **only** when `TEAMS_WEBHOOK_URL` or `ERROR_WEBHOOK_URL` is present in `ENV_FILE` (or the process environment). If neither is set, skip notification and mention that notifications were disabled. Never log full secrets.

---

## Adding a new repo

Copy the `_template` object in `config.json`, rename the key to the repo basename, set `aws_account`, `s3_bucket`, and `langfuse_project_id`. Align `tier4_live_tests` and `demo_script_paths` with what exists in that clone.
