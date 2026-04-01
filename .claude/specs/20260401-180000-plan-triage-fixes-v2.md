# Plan: Triage Fixes — 2026-04-01 (Sessions 341ed1e2, 989fcab7, 0e7906b4)

## Task Description
Fix 3 issues identified across the last 3 user sessions on 2026-04-01 (17:28–17:53 UTC).
Cross-referenced 5 Langfuse traces across 3 sessions. CloudWatch unavailable (SSO expired).

## Objective
Resolve all P0 and P1 issues. P2 items backlogged with clear file pointers.

## Problem Statement
Bedrock cross-region inference (`us.anthropic.claude-sonnet-4-6`) has been unstable since 2026-03-30 — 100% TTFT failures yesterday (503s/ServiceUnavailableException), ~50% intermittent today. When Sonnet stalls, botocore's `max_attempts=4` adaptive retry burns 30-40s on internal 503 retries before our 45s TTFT timer can react, consuming the entire budget in silent retries. The circuit breaker then cascades to Haiku, which produces advice-only (no document generation), leaving the user with no work product. Prompt caching (`cache_tools="default"`) adds cache-miss overhead to the first request, further increasing TTFT variance. A secondary issue is that `web_search` (Nova Web Grounding) has a 300s timeout, causing individual searches to stall for 5+ minutes.

## Relevant Files
| File | Issue |
|---|---|
| `server/app/strands_agentic_service.py:490-493` | Prompt caching re-enabled for Sonnet — causes empty generations |
| `server/app/strands_agentic_service.py:5189` | 45s TTFT timeout fires on cachePoint parse failure |
| `server/app/strands_agentic_service.py:5508-5529` | Circuit breaker cascades to Haiku after TTFT timeout |
| `server/app/tools/web_search.py:47-53` | 300s read_timeout on Nova Web Grounding client |
| `eagle-plugin/agents/supervisor/agent.md` | 14K+ token supervisor prompt overwhelms Haiku when used as fallback |

---

## Implementation Phases

### Phase 1: P0 Fixes (Critical)

#### 1. Disable Bedrock prompt caching until Strands SDK supports cachePoint responses

- **Evidence**: Langfuse traces `cbb8608d` and `ea0084fe` both show Sonnet generations with 45s latency, 0 tokens in/out. Git history confirms: commit `6cec3c2` reverted caching because "Strands SDK can't parse cachePoint responses", then `f088656` re-enabled it without verifying SDK support.
- **Root cause**: When Bedrock returns content blocks containing `cachePoint` metadata, the Strands SDK hits a `KeyError('cachePoint')` during response parsing. The error is swallowed silently — no text chunks are yielded — and the 45s TTFT timeout fires, triggering the cascade.
- **File**: `server/app/strands_agentic_service.py:490-493`
- **Fix**: Remove the prompt caching kwargs for Sonnet models:
  ```python
  # Lines 490-493: DELETE these lines
  # if "sonnet" in _mid:
  #     _kwargs["cache_tools"] = "default"
  #     _kwargs["cache_config"] = CacheConfig(strategy="auto")
  ```
  This restores the safe state from commit `6cec3c2`. Re-enable only after upgrading `strands-agents` to a version that handles `cachePoint` in response content blocks.
- **Validation**: Deploy to dev, send 5 sequential microscope purchase prompts. All 5 should use Sonnet (no TTFT timeout, no cascade to Haiku). Check Langfuse traces for non-zero token counts on every Sonnet generation.

#### 2. Haiku fallback produces advice-only (no documents)

- **Feedback**: User sent identical $45K microscope prompt in sessions `989fcab7` (Haiku) and `341ed1e2` (Sonnet). Sonnet generated 4 documents (SON, MRR, IGCE, AP). Haiku generated advice text only — never called `create_document` or `manage_package`.
- **Evidence**: Langfuse trace `45f21b6672d2` shows 122K input tokens / 1.4K output tokens. Tool calls: `web_search` (x4), `web_fetch` (x2), `query_compliance_matrix` (x2), `knowledge_search` — but zero `create_document` calls. The supervisor prompt's "DEFAULT TO ACTION" directive was ignored.
- **Root cause**: Two contributing factors:
  1. The 14K+ token supervisor prompt (`eagle-plugin/agents/supervisor/agent.md`) overwhelms Haiku's reasoning when combined with tool schemas and conversation history (122K total input). Haiku shifts from action mode to reasoning/advice mode under token pressure.
  2. Conflicting prompt signals: "DO THE WORK" vs. "Do NOT generate any document with placeholder data. Gather real data first" — Haiku interprets ambiguity conservatively.
- **File**: `server/app/strands_agentic_service.py` (cascade logic at line 5527) + `eagle-plugin/agents/supervisor/agent.md`
- **Fix**: This is resolved by Fix #1 (removing caching eliminates the TTFT timeout that causes the Haiku cascade). As a defense-in-depth measure, also add context pruning when cascading to Haiku:
  ```python
  # In the cascade loop (around line 5527), before creating the fallback agent:
  # If falling back to a haiku model, summarize conversation history
  # to keep input tokens under 80K
  if "haiku" in _next_model_id and strands_history:
      strands_history = _prune_history_for_fallback(strands_history, max_tokens=80_000)
  ```
- **Validation**: After Fix #1, confirm Haiku cascade no longer triggers on the microscope prompt. If manually forcing a Haiku fallback (by setting `EAGLE_BEDROCK_MODEL_ID=claude-haiku...`), verify it still generates documents with the pruned context.

### Phase 2: P1 Fixes (High)

#### 3. web_search 300s timeout causes 5-minute stalls

- **Evidence**: Langfuse traces show `web_search` calls taking 305s (session `341ed1e2`) and 309s (session `989fcab7`). These single calls dominated total session latency.
- **Root cause**: `server/app/tools/web_search.py:52` sets `read_timeout=300` on the Bedrock runtime client for Nova Web Grounding. When the grounding service takes close to the timeout, the call stalls for ~5 minutes. With `max_attempts=2`, a worst case is 600s.
- **File**: `server/app/tools/web_search.py:47-53`
- **Fix**: Reduce the timeout to 60s and add a per-query timeout wrapper:
  ```python
  _bedrock_runtime = boto3.client(
      "bedrock-runtime",
      region_name=AWS_REGION,
      config=Config(read_timeout=60, retries={"max_attempts": 1}),
  )
  ```
  60s is generous for web grounding (typical is 10-30s per AWS docs). Reduce retries to 1 (no retry) — the agent can decide to retry with a simpler query if the first fails.
- **Validation**: Trigger a web_search with a complex query. Confirm it either completes in <60s or fails fast with a timeout error (not 300s stall). Check that normal queries (10-30s) still succeed.

### Phase 3: P2 Improvements (Backlog)

#### 4. Reduce supervisor prompt token count

- **File**: `eagle-plugin/agents/supervisor/agent.md`
- **Issue**: ~14K tokens of supervisor prompt contributes to 122K input bloat on Haiku fallback. Verbose workflow examples, repeated compliance warnings, and edge case documentation inflate the prompt.
- **Suggestion**: Move detailed workflow examples to skill reference docs. Consolidate FAR 13.2/13.5/Part 15 into a decision tree. Target <8K tokens for the core supervisor prompt.

#### 5. Add Strands SDK cachePoint support tracking

- **Issue**: Prompt caching has been toggled 6 times across commits (`6aa9b45` → `64b4d76` → `6eab6c4` → `b5ece2a` → `6cec3c2` → `9ad20ad` → `f088656`). No tracking of when the Strands SDK actually supports it.
- **Suggestion**: Add a comment with the SDK issue number and a test that validates cachePoint handling before re-enabling.

---

## Acceptance Criteria
- [ ] Sonnet supervisor generates non-zero tokens on first call (no TTFT timeout)
- [ ] 5 consecutive microscope purchase prompts produce document packages (not advice-only)
- [ ] `web_search` timeout reduced to 60s — no 300s stalls
- [ ] No regressions in existing circuit breaker tests
- [ ] Langfuse traces show correct model attribution (Sonnet, not Haiku fallback)

## Validation Commands
```bash
ruff check server/app/
python -m pytest server/tests/ -v -k "circuit_breaker or web_search"
```

## Notes
- Generated by /triage skill on 2026-04-01
- Sessions: `341ed1e2`, `989fcab7`, `0e7906b4` (user `24a8d478`)
- Sources: 5 Langfuse traces, 0 CW events (SSO expired), 0 DynamoDB feedback
- Git history: 6cec3c2, 9ad20ad, f088656 (caching toggle chain)
- Langfuse URLs:
  - https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f/traces/7290ea56765127566a6558381b368b6d
  - https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f/traces/45f21b6672d2120be1db2838a8cd800e
  - https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f/traces/cbb8608da84b9f59c80bc049a3adf443
