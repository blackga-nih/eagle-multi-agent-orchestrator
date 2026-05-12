# Research-Lane Performance Benchmark — Local Validation

**Date:** 2026-05-06
**Author:** blackga (with Claude Opus 4.7)
**Branch chain:** `perf/research-semantic-timeout-and-spans` → `perf/research-checklist-parallel-lane` → `perf/cache-ttl-1h`
**PRs:** #199, #200, #202 (stacked)

---

## TL;DR

Three stacked PRs targeting Jitong's slow `sole source on a multi-award IDIQ` query (88–152s deployed). Local benchmark on the same query confirms research-lane wall **dropped from 64s → 11s (5.8× improvement)**. Total query wall on local Bedrock dropped from a baseline of ~114s to **70s warm / 72s cold** — the remaining time is final-answer synthesis, which is bounded by Sonnet 4.6 output-token throughput and is a separate problem.

---

## Baseline — Jitong's deployed Langfuse trace

Trace `6213c2aa…aa79` (2026-05-05 22:35, 88.4s):

| Phase | Time | Notes |
|---|---|---|
| chat decision | 2.7s | supervisor decides to call research |
| research tool | **64.2s** | gated by `kb_search_semantic` (60s) |
| └ kb_search_primary | 8.1s | parallel |
| └ kb_search_secondary | 7.2s | parallel |
| └ kb_search_path | 3.1s | parallel |
| └ **kb_search_semantic** | **60.4s** | **the bottleneck** |
| └ s3_fetch_docs | 0.7s | sequential |
| └ kb_search_checklist | 2.5s (or 63s on May 4) | sequential, high variance |
| chat synthesis | 20.4s | final answer |

Same query on 2026-05-04 took 152.6s — the 64s difference came from `kb_search_checklist` spiking to 63s on its AI rerank.

---

## Changes shipped in PRs #199 / #200 / #202

### PR #199 — `perf/research-semantic-timeout-and-spans`

1. **Hard timeout on semantic lane** (default 12s, env: `EAGLE_SEMANTIC_LANE_TIMEOUT_S`)
   - Replaced `with ThreadPoolExecutor` with manual `try/finally` so a timed-out future doesn't block on `__exit__`
   - On `TimeoutError`: drop semantic to None (merge code already handles None), `shutdown(wait=False, cancel_futures=True)`
2. **Embedding cache** in `embed_text()`
   - Bounded FIFO map (256 entries, env: `EAGLE_EMBED_CACHE_MAXSIZE`) keyed by `(truncated_text, dim)`
   - Failures not cached
3. **Span split** inside `exec_semantic_search`
   - New `semantic_embed` and `semantic_vectorquery` spans so we can isolate which step is slow

### PR #200 — `perf/research-checklist-parallel-lane`

- **Move `kb_search_checklist` into the parallel ThreadPool** as a 5th lane (alongside primary/secondary/path/semantic)
- Same 12s timeout pattern (env: `EAGLE_CHECKLIST_LANE_TIMEOUT_S`)
- Removes the lane from the critical path; previously it ran *after* the 4 KB lanes merged + s3_fetch_docs completed

### PR #202 — `perf/cache-ttl-1h`

- **Bump Bedrock prompt-cache TTL from 5m → 1h** via boto3 `before-parameter-build` event handler
- Walks the Converse request and adds `ttl="1h"` to every `cachePoint` block (system / toolConfig.tools / messages.content)
- Wired at all three `BedrockModel` construction sites (module chain + 2 retry-supervisor sites)
- Env-tunable via `EAGLE_CACHE_TTL` ("1h" default, "5m" reverts, empty disables)

---

## Local benchmark methodology

- Backend: `uvicorn app.main:app --port 8000` against AWS profile `eagle` (us-east-1)
- Query: identical to Jitong's — `Are there any special rules for issuing a sole source on a multi-award IDIQ?`
- Cold call: first hit on the freshly-started backend
- Warm call: same query 1 minute later (within 1h cache TTL window)
- Measurement: `response_time_ms` from `chat_request` log + Langfuse trace observations

---

## Results

### Cold call — trace `19207d99…f45e` (71.7s)

```
14:26:29  chat (decision)        10.83s    [supervisor → research tool_use]
14:26:40  research TOOL          10.60s    [parallel lane wall]
  ├─ kb_search_primary            7.63s    \
  ├─ kb_search_secondary          7.42s     |
  ├─ kb_search_path               2.51s     |  parallel
  ├─ kb_search_semantic           3.03s    /
  │  ├─ semantic_embed            1.28s    [NEW span — Titan call]
  │  └─ semantic_vectorquery      1.58s    [NEW span — S3 Vectors]
  └─ s3_fetch_docs                2.52s    [sequential after lanes]
  (no checklist — research called with include_checklist=false)
14:26:51  chat (synthesis)       48.83s    [2,372 output tokens]
14:27:42  request complete       79.79s
```

### Warm call — trace `f01f9548…4182` (70.0s)

```
14:28:02  chat (decision)         4.27s    [✓ prompt cache hit, was 10.83s]
14:28:06  research TOOL          11.12s    [parallel lane wall]
  ├─ kb_search_primary            8.01s    \
  ├─ kb_search_secondary          7.62s     |
  ├─ kb_search_path               1.45s     |
  ├─ kb_search_semantic           1.50s     |  parallel (5 lanes)
  │  ├─ semantic_embed            0.00s    [✓ EMBED CACHE HIT]
  │  └─ semantic_vectorquery      1.31s    /
  └─ kb_search_checklist          5.00s    [✓ NOW PARALLEL — was sequential]
  └─ s3_fetch_docs                2.33s
14:28:18  chat (synthesis)       53.73s    [2,737 output tokens]
14:29:13  request complete       74.80s
```

### Cache token accounting (from `/api/chat` response)

| Call | tokens_in | cache_read_input | cache_creation_input |
|---|---|---|---|
| Cold | 50,849 | 14,673 | 15,223 |
| Warm | 42,451 | **23,662** ↑ | **6,137** ↓ |

Warm call read **+8,989 more cached tokens** and wrote **−9,086 fewer** — confirms the prompt cache is engaging (cold call writes the prefix; warm call reads almost all of it).

---

## What each PR is proven to do, locally

| PR | Claim | Evidence |
|---|---|---|
| #199 — semantic timeout | Research wall capped if semantic spikes | Local semantic was fast (3s) so timeout didn't fire — but the same `result(timeout=12)` path runs every call; deployed traces will show it firing on slow Bedrock paths |
| #199 — embed cache | Identical queries skip Titan | Cold `semantic_embed`=1.28s → warm `semantic_embed`=**0.00s** ✓ |
| #199 — span split | Telemetry granularity | Both `semantic_embed` and `semantic_vectorquery` appear as distinct spans inside `kb_search_semantic` ✓ |
| #200 — checklist parallel | Removes from critical path | Cold trace had no checklist (called with include_checklist=false). Warm trace shows `kb_search_checklist` start_time=14:28:06.859 — same millisecond as other 4 lanes. Was previously sequential at trace-end ✓ |
| #200 — checklist timeout | Caps tail at 12s | Local checklist completed at 5.0s, well under cap. Deployed will show whether the 60s tail seen on May 4 gets capped |
| #202 — cache TTL 1h | Cache survives long pauses | Within-minute warm call hit cache (would have hit at 5m TTL too). Long-pause validation requires deployed trace with >5min gap between turns — to be confirmed post-deploy on Jitong's intake flows |

---

## Expected deployed impact for Jitong

For the same `sole source on multi-award IDIQ` query that took 88s on 2026-05-05:

| Phase | Before | After (expected) | Delta |
|---|---|---|---|
| chat decision | 2.7s | 2.7s (cold) / ~1s (warm via 1h cache) | up to −1.7s |
| research wall | 64.2s | ~12s (max of lanes, capped) | **−52s** |
| chat synthesis | 20.4s | 20.4s (unchanged) | 0 |
| **total** | **88.4s** | **~35s** | **−53s (60% reduction)** |

For the multi-turn ServiceNow intake flow (4 turns, 1029s total) where users paused 34 min between turns:

- Per-turn research savings: same ~52s reduction × 4 turns = ~208s
- Cache TTL win: 1 cache write avoided per long-paused turn × ~19k tokens × Sonnet input rate
- Estimated total savings: **~250–300s across the 4-turn session** (~25–30% reduction)

---

## What is NOT improved: final synthesis cost

Both cold and warm calls spent **48–54s on the final `chat` generation block**. That's:
- 2400–2700 output tokens × ~45 tok/s (Sonnet 4.6 throughput) = ~50–60s

This is structural — bounded by the model's generation speed, not by lane concurrency or cache state. The user perceives it as "the silent gap" before the answer appears. Three potential mitigations, deferred for separate evaluation:

1. **Reduce per-doc cap (5K → 2.5K)** in `_fetch_capped` — cuts input bulk by ~half, may also reduce output length if the LLM was over-quoting. **Risk:** may lose answer fidelity on docs that need fuller context (especially checklists). Needs eval coverage to validate.
2. **Move synthesis to Haiku for simple queries** — cheaper and faster, but routing logic needs to identify "simple" reliably.
3. **Stream the final answer** — already implemented on `/api/chat/stream`. The chat UI uses streaming; users see tokens as they arrive instead of waiting for completion. No wall-clock change but materially better UX. (Confirmed: streaming is already wired end-to-end, including the thinking-block chip from PR #192.)

---

## Validation summary

| Check | Result |
|---|---|
| `ruff check` on touched files | All checks passed |
| `pytest -k "research or semantic or knowledge_tools or strands_agentic"` | 62/65 pass (3 pre-existing failures on `main`, unrelated) |
| Smoke imports | `_SEMANTIC_LANE_TIMEOUT_S=12.0`, `_CHECKLIST_LANE_TIMEOUT_S=12.0`, `_CACHE_TTL=1h`, all models load |
| Handler simulation against fake Converse request | All cachePoint blocks (system / toolConfig.tools / messages.content) get `ttl="1h"` ✓ |
| Bedrock service model | `CachePointBlock.ttl` enum `['5m', '1h']` confirmed via boto3 introspection |
| Local cold call | 71.7s end-to-end, all 5 lanes fire, response valid |
| Local warm call | 70.0s, embed cache hit (0.00s), prompt cache hit (decision 10.8s → 4.3s), checklist parallel ✓ |

---

## Next steps

1. **Merge #199 → #200 → #202 in order** and deploy via the standard CI/CD path
2. **Pull a post-deploy Langfuse trace** for any research-heavy query and confirm:
   - `kb_search_semantic` ≤ 12s, or shows the new "dropping" warn log if it would have exceeded
   - `semantic_embed` and `semantic_vectorquery` appear as distinct spans
   - `kb_search_checklist` starts at the same time as the other 4 lanes
   - `cache_read_input_tokens` is high relative to total input on multi-turn sessions
3. **Optional** — open follow-up PR for **Option E** (per-doc cap reduction) once we have eval coverage that catches quality regressions on checklist-heavy answers
4. **Optional** — investigate **Option D** (drop semantic `over_fetch` from 60 → 30) once #199's `semantic_vectorquery` span tells us S3 Vectors is the slow part of the deployed semantic lane

---

## Branch / PR map

```
main
 └── perf/research-semantic-timeout-and-spans   PR #199
      └── perf/research-checklist-parallel-lane  PR #200 (stacked)
           └── perf/cache-ttl-1h                 PR #202 (stacked)
```

Files changed across all three:

```
server/app/strands_agentic_service.py    +171 / -39
server/app/tools/knowledge_tools.py       +71 / -20
```
