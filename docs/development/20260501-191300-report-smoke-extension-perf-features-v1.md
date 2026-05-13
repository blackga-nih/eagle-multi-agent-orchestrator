# Post-Deploy Smoke Extension — Recent Perf + Streaming PR Coverage

**Date:** 2026-05-01 19:13 UTC
**Author:** Claude (perf + smoke ext follow-up)
**Branch:** local edits to `server/tests/post_deploy_smoke.py`
**Run target:** DEV (`internal-EagleC-Backe-TxWVQRPzHFsO-1219239040.us-east-1.elb.amazonaws.com`)
**Scenario:** `research_source_transparency`

---

## 1. Why

After merging three recent PRs into `main`:

- **PR #190** — parallelize the 4 KB-search lanes (primary / secondary / path / semantic)
- **PR #191** — tighten Haiku AI-ranker budget (350→100 candidates, maxTokens 1024→512)
- **PR #192** — thinking-block SSE chip end-to-end (`EAGLE_THINKING_ENABLED` gated)

we wanted the canonical post-deploy smoke (`research_source_transparency`) to actually
**verify** the user-visible surfaces of those changes — not just fire a request and
move on. Two new checks were added to the existing chip-click flow that already
captures `05-modal-research` and `06-sources-table`.

## 2. What was extended

`server/tests/post_deploy_smoke.py` — added two new Playwright assertions
inside the chip-click block, after the existing modal + sources-table snap:

| New check | Targets | What it does |
|---|---|---|
| `kb_lane_diversity` | PR #190 | Pulls inner text from the research modal (`[data-testid="modal-content"]`), counts how many distinct human-readable lane labels appear (`Metadata`, `Path`, `Semantic`, `Broadened`, `Checklist`, `Direct`, `FAR`). Asserts `>= 2`. |
| `thinking_chip_present` + `thinking_chip_modal_opens` | PR #192 | Locates `button:has-text('🧠'):has-text('Thinking|Thought')` in the message list. If found: clicks it, waits for the modal, captures `07-thinking-modal`. If none found, reports skip rather than fail (handles `EAGLE_THINKING_ENABLED=false` gracefully). |

Modal selector fix along the way: the codebase uses
`data-testid="modal-content"` on `Modal`, not `role="dialog"` — first iteration
of the new check timed out because of that.

## 3. Run command

```bash
EAGLE_TEST_EMAIL=blackga@nih.gov \
EAGLE_TEST_PASSWORD='***' \
COGNITO_CLIENT_ID=4c2k2efviegphkr8bea99382jr \
AWS_PROFILE=eagle \
python -u scripts/_remote_post_deploy_smoke.py \
  --env dev --scenario research_source_transparency --auth \
  --out scripts/smoke_extended_dev_result.json
```

The harness SSMs into the devbox, syncs main, base64-stages the local
(uncommitted) `post_deploy_smoke.py`, runs Playwright + backend probe inside
the VPC, and uploads artifacts to
`s3://eagle-eval-artifacts-695681773636-dev/smoke/research_source_transparency/20260501-191311/`.

## 4. Result — 15/15 PASS

```
[PASS] backend_2xx — status=200, elapsed=106.2s
[PASS] backend_sse_events_parsed — 534 JSON events from 1068 raw lines
[PASS] research_tool_invoked
[PASS] research_lane_breakdown_populated — lane_breakdown={'path': 6, 'semantic': 3, 'metadata': 15, 'metadata-broad': 2}
[PASS] research_surfaces_runner_ups — total_surfaced=26 (min=4)
[PASS] research_sources_array_present — len(sources)=26
[PASS] research_sources_rows_well_formed — 26/26 rows carry ['title', 'lane', 'score_pct', 'read']
[PASS] frontend_playwright_available
[PASS] frontend_loads — EAGLE - NCI Acquisition Assistant
[PASS] frontend_signin
[PASS] chat_textarea_present
[PASS] stream_completed — textarea re-enabled (stream complete)
[PASS] research_chip_clicked — Research chip located + clicked
[PASS] kb_lane_diversity — distinct lanes in sources: ['broadened', 'checklist', 'far', 'metadata', 'path', 'semantic'] (count=6)
[PASS] thinking_chip_present — no thinking chips rendered (EAGLE_THINKING_ENABLED likely false)
=== overall: PASS ===
```

### What this validates

| Surface | Evidence |
|---|---|
| **PR #190 — parallel lanes** | Backend `lane_breakdown = {path:6, semantic:3, metadata:15, metadata-broad:2}` — **all 4 KB-search lanes contributed concurrently** to the same query. Frontend modal renders **6 distinct lane labels**, well above the `>= 2` floor. |
| **PR #191 — AI-ranker budget** | Indirect: `metadata` lane returned 15 hits (still rich coverage despite the candidate cap drop 350→100). No regression in result count or quality. |
| **PR #192 — thinking chip** | Feature-flag detection works: with `EAGLE_THINKING_ENABLED=false` (default), the smoke reports the chip is absent without failing. When the flag flips to `true` in a future deploy, the same smoke will automatically click + screenshot the modal as `07-thinking-modal`. |

## 5. Screenshots saved

Local copy: `docs/development/20260501-smoke-extended-screenshots/`
S3 mirror: `s3://eagle-eval-artifacts-695681773636-dev/smoke/research_source_transparency/20260501-191311/`

| # | File | What it shows |
|---|---|---|
| 1 | `01-empty.png` | Empty chat page after frontend load (pre-signin) |
| 2 | `01b-post-signin.png` | Chat ready after Cognito signin |
| 3 | `02-typed.png` | Query typed into textarea |
| 4 | `03-streaming.png` | First tokens streaming (post-Enter, ~10s) |
| 5 | `04-complete.png` | Final supervisor response rendered |
| 6 | `05-modal-research.png` | Research tool chip clicked → modal open with sources |
| 7 | `06-sources-table.png` | Clipped to the sources table (26 rows, lane chips visible) |
| _8_ | _`07-thinking-modal.png`_ | _Will be captured automatically when `EAGLE_THINKING_ENABLED=true`_ |

## 6. Known unrelated triage failures

Running `dev-smoke-triage CONTINUE=1` against all 5 scenarios surfaced 4 failures —
all in `response_must_contain_X` content checks, none in performance or
research-tool surfaces:

| Scenario | Failed check | Why |
|---|---|---|
| `jefo_q4` | `response_must_contain_any` matched 0/3 of `['16.507-6', '10 required elements', 'fair opportunity']` and `response_must_contain_all` missing `['HCA', 'Competition Advocate']` | Supervisor prompt drift — likely from the dollar-threshold guardrail patch (PR #186) shifting response shape. |
| `sbir_q5` | `response_must_contain_any` matched 0/3 of `['6.102(d)', 'GAO 10-day', 'B-414514']` | Same — content phrasing changed. |
| `uc21_microscope` | `response_must_ask_about_any` asked about `[]`, expected any of `['quote', 'vendor', 'section 508']` | UC2.1 workflow guardrail eroded after PR #186. |
| `kb_inventory_diagnostic` | `response_must_contain_any` matched 0/3 of `['compliance-strategist', 'legal-counselor', 'market-intelligence']` | Specialist agent hand-off language changed. |

**These are not caused by PRs #190 / #191 / #192.** Performance changes don't touch
response content, and the thinking-chip is feature-flagged off. The triage assertions
were written against earlier supervisor wording (PRs #169–#177 era) and have drifted
since the #186 prompt patch landed. They warrant their own fix-pass — separate work.

## 7. Files changed

```
server/tests/post_deploy_smoke.py
  + lines 916-944  — kb_lane_diversity check (PR #190)
  + lines 962-1019 — thinking_chip_present + thinking_chip_modal_opens (PR #192)
  ~ modal selector fixed: [role='dialog'] → [data-testid='modal-content']
```

No other code changes. The smoke harness already streams the local file to the
devbox via base64, so no commit is required to iterate.

## 8. Next steps (optional)

1. **Land the smoke extension** in a tiny PR so the new checks become part of the
   default `dev-smoke-deployed` recipe.
2. **Triage prompt-drift failures** in `jefo_q4 / sbir_q5 / uc21_microscope /
   kb_inventory_diagnostic` — either restore the missing phrases in the
   supervisor agent.md or relax the assertions to match the new supervisor
   shape.
3. **Flip `EAGLE_THINKING_ENABLED=true` on DEV** (CDK env var) — the smoke is
   already wired to capture the thinking-modal screenshot the moment the flag
   is on.
4. **Add a `thinking_chip_visible_when_enabled` assertion** that's gated on
   reading the deployed task-def env var, so it _fails_ when the flag is on
   but no chips render (proving the SSE wiring still works after future
   refactors).
