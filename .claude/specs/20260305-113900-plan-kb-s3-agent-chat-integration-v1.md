# Plan: Full S3 Knowledge Base Integration for Agents + Chat (Beginner-Safe)

**Created**: 2026-03-05T11:39:00Z  
**Status**: Ready for Implementation  
**Type**: End-to-End Integration + Hardening  
**Estimated Effort**: 1-2 days (focused), 3 days (with full test hardening)

---

## 1. What This Plan Solves

### 1.1 Current Problem

Your app is in a **partial state**:

1. S3 and document generation are real and wired.
2. Knowledge retrieval handlers (`knowledge_search`, `knowledge_fetch`) exist and use DynamoDB + S3.
3. But the **active Strands runtime** does not expose those knowledge tools to the supervisor agent.
4. Result: chat cannot reliably retrieve from your S3 knowledge base, even though backend code exists.

### 1.2 End State (Definition of Done)

After this plan is completed:

- [ ] `/api/tools` shows `knowledge_search` and `knowledge_fetch`
- [ ] chat can call `knowledge_search` and `knowledge_fetch` in real conversations
- [ ] answers include source references (`title`, `s3_key`)
- [ ] health endpoint reports KB dependency status (DynamoDB + S3)
- [ ] tests cover success and failure paths
- [ ] static/mock FAR behavior is explicitly labeled or replaced

If all six are true, KB integration is no longer “mock/partial”.

---

## 2. Ground Rules (Read First)

### 2.1 Do This First

1. Create a branch:

```bash
git checkout -b feat/kb-s3-chat-integration
```

2. Confirm backend runs before making changes:

```bash
cd server
uvicorn app.main:app --reload --port 8000
```

3. In a second terminal, confirm tools endpoint responds:

```bash
curl -s http://127.0.0.1:8000/api/tools | jq '.'
```

### 2.2 Do Not Do

- Do not remove existing document generation behavior.
- Do not rename tool names (`knowledge_search`, `knowledge_fetch`) unless you update all references.
- Do not ship without test coverage for at least one end-to-end retrieval flow.

---

## 3. File-by-File Implementation Plan

## Phase A — Wire KB Tools into Active Strands Runtime

### Why

Right now, Strands builds service tools from `_SERVICE_TOOL_DEFS`, and KB tools are missing there.

### A1. Update `server/app/strands_agentic_service.py`

#### File

`server/app/strands_agentic_service.py`

#### Step

In `_SERVICE_TOOL_DEFS`, add these entries:

```python
"knowledge_search": (
    "Search the acquisition knowledge base metadata in DynamoDB. "
    "Pass JSON with optional fields: topic, document_type, agent, authority_level, keywords, limit."
),
"knowledge_fetch": (
    "Fetch full knowledge document content from S3. "
    "Pass JSON with s3_key (or document_id)."
),
```

Place them near `search_far` and `create_document` so tool grouping is obvious.

### A2. Keep tool schema list and runtime tool list aligned

Still in `server/app/strands_agentic_service.py`:

1. In `EAGLE_TOOLS`, add schema blocks for:
   - `knowledge_search`
   - `knowledge_fetch`
2. Use input schema compatible with `server/app/tools/knowledge_tools.py`.

Minimum schema contract:

- `knowledge_search`: object with optional `topic`, `document_type`, `agent`, `authority_level`, `keywords`, `limit`
- `knowledge_fetch`: object with `s3_key` and/or `document_id`

### A3. Verify registration

Run:

```bash
curl -s http://127.0.0.1:8000/api/tools | jq '.tools[].name'
```

Expected includes:

- `"knowledge_search"`
- `"knowledge_fetch"`

---

## Phase B — Enforce Retrieval Behavior in Agent Responses

### Why

Tools can be exposed but still underused by the model. We force predictable behavior via prompt rules.

### B1. Update supervisor prompt guidance

#### File

`server/app/strands_agentic_service.py`

#### Step

In `build_supervisor_prompt(...)`, append a short “KB Retrieval Rules” block:

```text
KB Retrieval Rules:
1) For policy/regulation/procedure/template questions, call knowledge_search first.
2) If search returns results, call knowledge_fetch on top 1-3 relevant docs.
3) In final answer, include a "Sources" section with title + s3_key.
4) If no results, explicitly say no KB match and ask a refinement question.
```

Keep it short and imperative.

### B2. Keep citations simple and machine-checkable

In generated answers, enforce this shape:

```text
Sources:
- <title> (s3_key: <value>)
- <title> (s3_key: <value>)
```

This format makes tests easy.

---

## Phase C — Add KB Health and Diagnostics

### Why

You need an explicit “is KB connected right now?” answer without guessing from chat behavior.

### C1. Add KB status in health response

#### File

`server/app/streaming_routes.py` (health route), or `server/app/main.py` if you centralize there.

#### Step

Add fields under `services`:

- `knowledge_metadata_table`: true/false
- `knowledge_document_bucket`: true/false

### C2. Implement checks

Use lightweight checks only:

- DynamoDB: `describe_table` or `Table.load()` for `METADATA_TABLE`
- S3: `head_bucket` for `DOCUMENT_BUCKET` (or `S3_BUCKET` per your final architecture)

Return non-fatal errors in payload, not crashes.

Example shape:

```json
"knowledge_base": {
  "metadata_table": {"ok": true, "table": "eagle-document-metadata-dev"},
  "document_bucket": {"ok": true, "bucket": "eagle-documents-..."}
}
```

---

## Phase D — Make Mock/Static Knowledge Explicit

### Why

Currently `search_far` is static data. That can mislead users into thinking it is live retrieval.

### D1. Add explicit source label

#### File

`server/app/agentic_service.py`

#### Step

Keep `search_far` as-is for now, but ensure response clearly includes:

- `source: "static_reference_dataset"`
- `note: "Not live acquisition.gov lookup"`

### D2. Prompt rule to prefer KB over static FAR

In supervisor prompt, add:

```text
Prefer knowledge_search/knowledge_fetch over search_far when KB can answer.
Use search_far only as fallback reference.
```

---

## Phase E — Telemetry for Confidence + Debugging

### Why

You need proof that KB is being used after deployment.

### E1. Add counters

#### File

`server/app/main.py` (telemetry summary area) and/or tool handlers.

Track at minimum:

- `knowledge_search_calls`
- `knowledge_fetch_calls`
- `knowledge_zero_results`
- `knowledge_errors`

### E2. Log structured events in tool handlers

#### File

`server/app/tools/knowledge_tools.py`

Add consistent logs:

- on search start (filters + limit)
- on search result count
- on fetch key
- on fetch size/truncation
- on exception path

---

## Phase F — Tests (Required Before Merge)

## F1. Unit Tests for KB Tools

#### New file

`server/tests/test_knowledge_tools.py`

Test cases:

1. `exec_knowledge_search` returns filtered results
2. `exec_knowledge_search` handles DynamoDB error
3. `exec_knowledge_fetch` returns content for valid key
4. `exec_knowledge_fetch` handles missing key
5. `exec_knowledge_fetch` truncates >50KB content

Use mocking for boto3 clients/resources.

## F2. Integration Test for Tool Exposure

#### New or existing test file

`server/tests/test_tools_endpoint.py`

Assert `/api/tools` includes both KB tools.

## F3. Streaming/Chat Behavior Test

#### New or existing test file

`server/tests/test_chat_kb_flow.py`

Goal:

- simulate a KB-style prompt
- verify at least one KB tool was called (via response/tool trace)
- verify final text includes `Sources:` and `s3_key`

---

## 4. Copy/Paste Implementation Checklist

Run top-to-bottom. Do not skip.

### Step 1: Runtime wiring
- [ ] Add `knowledge_search` to `_SERVICE_TOOL_DEFS`
- [ ] Add `knowledge_fetch` to `_SERVICE_TOOL_DEFS`
- [ ] Add both to `EAGLE_TOOLS` schema list
- [ ] Restart backend and verify `/api/tools`

### Step 2: Prompt behavior
- [ ] Add KB retrieval rules to supervisor prompt
- [ ] Add output “Sources” contract in prompt
- [ ] Verify chat output format manually

### Step 3: Health/diagnostics
- [ ] Add KB section to health response
- [ ] Implement DDB + S3 checks
- [ ] Confirm health route still returns 200

### Step 4: Mock clarity
- [ ] Label `search_far` as static
- [ ] Add prompt rule: KB preferred over static FAR

### Step 5: Tests
- [ ] Add `test_knowledge_tools.py`
- [ ] Add tools endpoint test for KB tools
- [ ] Add chat KB flow test
- [ ] Run tests and ensure pass

### Step 6: Final verification
- [ ] Ask chat a KB question
- [ ] Confirm KB tool calls in logs
- [ ] Confirm response includes `Sources` with `s3_key`

---

## 5. Verification Commands

Run exactly in this order.

```bash
# 1) Lint
cd server
ruff check app tests

# 2) Unit tests
pytest -q tests/test_knowledge_tools.py

# 3) Broader backend tests
pytest -q tests/test_tools_endpoint.py tests/test_chat_kb_flow.py

# 4) Manual tools check
curl -s http://127.0.0.1:8000/api/tools | jq '.tools[].name'

# 5) Health check
curl -s http://127.0.0.1:8000/api/health | jq '.'
```

Manual chat smoke prompt:

```text
What FAR guidance applies to sole-source justifications over SAT? Use the knowledge base and cite sources.
```

Pass criteria:

- answer contains `Sources:`
- includes at least one `s3_key`
- no fallback-only behavior unless no KB results exist

---

## 6. Rollback Plan (If Something Breaks)

If deployment causes bad behavior:

1. Revert only Strands tool exposure changes first.
2. Keep KB handlers intact (safe to leave).
3. Keep tests (they document intended behavior).

Fast rollback command example:

```bash
git revert <commit_sha_that_added_kb_tool_registration>
```

Then redeploy backend.

---

## 7. Common Failure Modes + Fixes

### Failure: `/api/tools` does not list KB tools

Cause: updated handler map but not Strands `EAGLE_TOOLS` / `_SERVICE_TOOL_DEFS`.

Fix: sync both lists in `strands_agentic_service.py`.

### Failure: tool exists but never called

Cause: prompt not instructive enough.

Fix: strengthen supervisor KB retrieval rules.

### Failure: KB search always empty

Cause: bad metadata table, wrong env var, or poor filters.

Fix:

1. Check `METADATA_TABLE` env var
2. run a raw scan on table
3. verify items have `s3_key`, `primary_topic`, `keywords`

### Failure: fetch errors for existing docs

Cause: wrong bucket (`DOCUMENT_BUCKET` vs `S3_BUCKET`) or key mismatch.

Fix:

1. align env vars
2. verify stored `s3_key` prefixes
3. test `head_object` with same key

---

## 8. Suggested Commit Plan

1. `feat(strands): expose knowledge_search and knowledge_fetch in service tool registry`
2. `feat(agent): add kb retrieval + citation behavior rules to supervisor prompt`
3. `feat(api): add knowledge base dependency checks to health endpoint`
4. `chore(far): label search_far as static fallback source`
5. `test(kb): add unit + integration tests for knowledge retrieval flow`

---

## 9. Final QA Sign-Off Template

Use this before merge:

- [ ] Runtime: KB tools visible in `/api/tools`
- [ ] Functionality: chat calls KB tools on retrieval queries
- [ ] Output: responses include `Sources` and `s3_key`
- [ ] Reliability: health endpoint reports KB status
- [ ] Transparency: static FAR path clearly labeled
- [ ] Safety: tests passing in CI/local

If every item is checked, implementation is complete.
