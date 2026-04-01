# Plan: Triage Fixes — 2026-04-01 (Session c11ae897)

## Task Description
Fix 4 issues identified during session `c11ae897-65db-4001-88f9-fb6701ceb797` on 2026-03-31.
Cross-referenced 1 DynamoDB feedback item, 476 CloudWatch backend events (173 errors/warnings), and 8 Langfuse traces.

## Objective
Resolve all P0 and P1 issues. P2 items backlogged with clear file pointers.

## Problem Statement
The OTLP trace exporter is flooding CloudWatch with 401 Unauthorized errors (~every 5 seconds) because Langfuse API credentials on the deployed ECS container are invalid. This drowns backend logs with noise and makes observability appear broken. Separately, template_store has a broken import path that silently disables the PLUGIN# DynamoDB template fallback, and document creation (qasp, sb_review) is failing at the service layer — the user reported "still trying to read docx from s3 instead of markdown equivalent in dynamodb."

## Session Timeline

```
20:22:17  [LF] Trace: "I need to procure cloud hosting..." → intake questions (5s)
20:22:38  [LF] Trace: User provides details → acquisition summary (22s)
20:23:10  [LF] Trace: SOW + IGCE generation (341s, 30 observations)
20:29:20  [DDB] Feedback: "still trying to read docx from s3 instead of markdown equivalent in dynamodb"
20:29:58  [LF] Trace: Market Research + AP generation (299s, 30 observations)
20:35:39  [LF] Trace: SSP + Purchase Request (163s, 19 observations)
20:37:26  [CW] ERROR: OTLP export 401 Unauthorized (repeats every 5-10s throughout)
20:38:39  [CW] WARN: template_store plugin_store not importable (sb_review, qasp, source_selection_plan)
20:41:23  [CW] INFO: create_document_tool DONE sb_review → success=False
20:42:20  [CW] WARN: template_store plugin_store not importable (repeats for 3 templates)
20:43:27  [CW] INFO: create_document_tool ENTRY qasp (content_len=10644)
20:43:27  [CW] INFO: create_document_tool DONE qasp → success=False
20:43:27  [CW] INFO: create_document_tool TIMING qasp → 12ms success=True (contradictory!)
20:45:57  [CW] INFO: Set active package PKG-2026-0038
20:47:00  [CW] INFO: Greeting fast-path 62916ms (model=us.anthropic.claude-sonnet-4-6)
20:47:10  [CW] WARN: template_store plugin_store not importable (repeats again)
```

## Relevant Files
| File | Issue |
|---|---|
| `server/app/strands_agentic_service.py:130-145` | OTLP exporter continues after 401 auth failure |
| `server/app/template_store.py:361` | Bare `from plugin_store import ...` fails with ImportError in ECS |
| `server/app/document_service.py` | Document creation returns success=False — needs investigation |
| `server/app/strands_agentic_service.py:689-740` | Greeting fast-path taking 63s |

---

## Implementation Phases

### Phase 1: P0 Fixes (Critical)

#### 1. OTLP Exporter 401 Unauthorized — Disable exporter on auth failure
- **Feedback**: User reported "langfuse and cloudwatch are not working properly"
- **Evidence**: 20+ OTLP 401 errors in CloudWatch within 10 minutes; every span export fails
- **Root cause**: `_ensure_langfuse_exporter()` at line 125 adds the `SimpleSpanProcessor(exporter)` to the tracer provider, then the startup probe at line 141 detects the 401 — but the exporter is already registered. All subsequent spans attempt (and fail) to export, flooding logs.
- **File**: `server/app/strands_agentic_service.py:82-167`
- **Fix**: Restructure to probe FIRST, add exporter ONLY if auth succeeds. Move the httpx probe before `provider.add_span_processor()`. If 401, skip adding the processor entirely and log once.
- **Validation**: Deploy, check CW for absence of OTLP 401 errors; Langfuse traces appear when keys are valid.

```bash
ruff check server/app/strands_agentic_service.py
python -m pytest server/tests/ -v -k "langfuse or otlp"
```

#### 2. template_store.py — Fix broken plugin_store import
- **Feedback**: Indirectly corroborates "still trying to read docx from s3 instead of markdown equivalent in dynamodb" — PLUGIN# fallback never fires
- **Evidence**: WARNING repeated 9+ times across session: `plugin_store not importable; skipping PLUGIN# fallback`
- **Root cause**: Line 361 uses `from plugin_store import get_plugin_item` (bare module name). In the ECS container, the module lives at `app.plugin_store` and `plugin_store` alone is not on `sys.path`. Every other file in `server/app/` uses relative imports (`.plugin_store`) or absolute (`app.plugin_store`).
- **File**: `server/app/template_store.py:361`
- **Fix**: Change to `from .plugin_store import get_plugin_item` (relative import, consistent with rest of codebase).
- **Validation**:
```bash
ruff check server/app/template_store.py
python -c "from app.template_store import resolve_template; print('OK')"
```

### Phase 2: P1 Fixes (High)

#### 3. Document creation success=False — Contradictory logging
- **Feedback**: "still trying to read docx from s3 instead of markdown equivalent in dynamodb"
- **Evidence**: At 20:43:27, create_document_tool logs both `TIMING: success=True` and `DONE: success=False` for the same qasp call. Same pattern for sb_review at 20:41:23.
- **Root cause**: Needs investigation. The TIMING log likely reflects the S3 upload timing (which succeeded), while DONE reflects the overall DocumentResult (which failed, possibly because DynamoDB write or template resolution failed). The template_store ImportError (Issue #2) could cause the template fallback to fail, which might cascade into document creation failure if no template is found in layers 1-3.
- **File**: `server/app/document_service.py:120-200`, `server/app/strands_agentic_service.py` (create_document_tool wrapper)
- **Fix**: After fixing Issue #2, re-test document creation. If still failing, add the DocumentResult error message to the DONE log line so root cause is visible. Investigate whether the "success=False" is due to a docx-vs-markdown format mismatch (user feedback suggests this).
- **Validation**:
```bash
python -m pytest server/tests/ -v -k "document"
```

#### 4. Greeting fast-path — 63 second response time
- **Evidence**: `Greeting fast-path responded in 62916ms (model=us.anthropic.claude-sonnet-4-6)`
- **Root cause**: The greeting fast-path at line 689-740 uses a direct Bedrock `converse()` call. 63s for a simple greeting suggests either: (a) Bedrock throttling/cold start, (b) the greeting prompt accumulated too much context, or (c) network latency in ECS. This was a one-off observation — need to check if it's persistent.
- **File**: `server/app/strands_agentic_service.py:689-740`
- **Fix**: Add a timeout to the Bedrock `converse()` call (e.g., 15s). If it exceeds timeout, fall through to the full agent path. Also check if this is a recurring pattern by querying CW for other greeting fast-path timings.
- **Validation**:
```bash
# Query CW for greeting fast-path timings in last 7 days
# Look for pattern of >30s responses
```

### Phase 3: P2 Improvements (Backlog)

#### 5. Dead clicks on diagnostic output (frontend)
- **Evidence**: Telemetry shows 8 `analytics.dead_click` events at 19:18-19:19 on `/chat` page — user clicking on health diagnostic table elements (Langfuse status, CW status rows)
- **File**: `client/components/chat-simple/simple-chat-interface.tsx`
- **Fix**: If diagnostic tables are rendered in chat, ensure table rows are not visually misleading as interactive elements (avoid hover states on non-clickable elements).

#### 6. Favicon feedback
- **Feedback**: "change favicon to the EAGLE logo from 'E'" (session 6c880600, 2026-04-01)
- **File**: `client/public/` or `client/app/layout.tsx`
- **Fix**: Replace favicon with EAGLE logo

#### 7. Header centering feedback
- **Feedback**: "this header text should be centered underneath the eagle and EAGLE. - Enhanced Acquisition Guidance and Learning Engine" (session 8202e347, 2026-04-01)
- **File**: Login or landing page component
- **Fix**: Center subtitle text under logo

---

## Acceptance Criteria
- [ ] OTLP exporter is NOT added when startup probe returns 401
- [ ] Zero OTLP 401 errors in CW logs after deploy (when keys are invalid, no exporter = no errors)
- [ ] `template_store.resolve_template` successfully imports `plugin_store` and queries PLUGIN# layer
- [ ] Document creation (qasp, sb_review) returns success=True
- [ ] Greeting fast-path has a timeout guard
- [ ] All validation commands pass

## Validation Commands
```bash
ruff check server/app/
npx tsc --noEmit
python -m pytest server/tests/ -v
```

## Notes
- Generated by /triage skill on 2026-04-01
- Session: `c11ae897-65db-4001-88f9-fb6701ceb797`
- Tenant: `dev-tenant` | User: `dev-user` | Package: `PKG-2026-0038`
- Environment: dev
- Sources: 1 feedback, 476 CW backend events (173 errors), 8 LF traces, 9050 telemetry events
- **CloudWatch MCP server** had SSO token expired — used AWS CLI directly
- **DynamoDB boto3** also had expired SSO token — used AWS CLI `dynamodb query` as workaround
- **Langfuse API** worked fine via direct HTTP (httpx) — traces retrieved successfully
