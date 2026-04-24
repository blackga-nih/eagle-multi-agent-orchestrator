# New EAGLE Jira Items — 2026-04-24

> Prepared from Teams thread feedback by Jitong Li (NIH/NCI) on 2026-04-23 — two related issues surfaced against the supervisor's `research` tool: high-variance KB-search latency and inconsistent citation rendering.

---

## New Stories

### [EAGLE-254](https://tracker.nci.nih.gov/browse/EAGLE-254): research tool — high-variance latency + inconsistent source citations
- **Type**: Bug
- **Epic**: Observability & Answer Quality
- **Summary**: Fix 11x latency variance in `research` tool and missing/inconsistent `Sources` block across LLM answers
- **Status**: To Do
- **Assignee**: `assignee:gregory.black`
- **Expert Domain**: `backend`, `cloudwatch`, `eval`
- **PR**: _pending_
- **Commits**: _pending_
- **Plan**: `.claude/specs/20260424-100000-plan-research-tool-obs-and-citations-v1.md`

**Description**

While testing FAR / appropriations-law questions against the deployed EAGLE on 2026-04-23, Jitong Li observed two distinct but related issues — both routing through the supervisor's `research` tool.

**1. Latency variance (observability gap).** The `research` tool is the single dominant span in every supervisor turn (`AGENT → event_loop → chat(tool_use) → research(TOOL) → event_loop → chat(end_turn)` = 6 observations total). Across three consecutive KB-backed questions in one session, the `research` span varied by 11x with no visible cause:

| Question | research span | total turn | Langfuse trace |
|---|---:|---:|---|
| "Micro-purchase / SAT thresholds" | 16.6s | 58.5s | `ba096fd0d1e89013e55d70269146044d` |
| "GAO cases on IDIQ minimum guarantees" | 11.4s | 42.2s | `12d395bd5ad01bd113f23d1b5967db03` |
| **"How severability effects fiscal-year funding"** | **128.3s** | **163.1s** | `cba35d9005b699c5474bf885d4ddafef` |

The research tool is emitted as a single opaque `TOOL` span. We have **zero** sub-span visibility into what happens inside — can't distinguish Bedrock Knowledge Base `Retrieve` latency from S3 doc hydration from post-processing. Payload size rules out "more data" (Q3 = 116KB output, Q2 = 167KB output — the slow one returned less).

**2. Citation rendering inconsistency (prompt/LLM bug).** The `research` tool's output *already contains* fully-qualified `s3_key` paths for every KB result (e.g. `eagle-knowledge-base/approved/compliance-strategist/SOPs/HHS_GPC_Streamlined_Guide_2025.txt`, 23 documents per call). The data is there. The LLM just renders it differently every time:

| Question | What the user sees at bottom of answer |
|---|---|
| Q1 micro-purchase | `**Source:** HHS PMR Threshold Matrix; HHS GPC Streamlined Guide 2025` — title only, no filename, no path |
| Q2 GAO IDIQ | `**Sources:** `GAO_B-321640_*.txt` — eagle-knowledge-base/approved/legal-counselor/appropriations-law/` — filename + directory ✅ |
| Q3 severability | **No Sources block at all** — only inline "GAO B-321640 (SBA, 2011)" prose reference |

Gregory Black's on-thread take — *"might just be a quick fix by simplifying the schema across the various tool uses"* — aligns with this. The research tool emits `document_id` + `s3_key` (duplicates). If other specialist tools use different field names the LLM can't pattern-match a single citation style, which is why it improvises inconsistently.

**Evidence**

- Session ID (Q3): `336cc3e5-294c-4a7c-8c7e-95c57c286de0`
- User ID: `24a8d478-20a1-7087-e1a3-56a38d733592` (Jitong Li)
- Langfuse project: `cmmsqvi2406aead071t0zhl7f`

**Acceptance Criteria**
- [ ] `research` tool emits child Langfuse spans `kb_retrieve`, `s3_fetch`, `post_process` so any future slow call is diagnosable without re-running.
- [ ] Supervisor system prompt enforces a `## Sources` footer after any `research` tool invocation. Each cited doc rendered as `` `<filename>` — <s3_key directory>``.
- [ ] KB-result schema normalized across all specialist tools that return documents (drop duplicate `document_id`; standardize on `s3_key` + `title` + `filename`).
- [ ] Regression tests in eval suite — run the three Jitong queries (micro-purchase, GAO IDIQ minimums, severability) and assert each answer contains a `## Sources` block with filename + directory per cited doc.
- [ ] Soft latency SLO: log `WARN` when a single `research` span exceeds 60s; alert threshold to be set after 1 week of child-span data.

**Priority**: P2 · **Effort**: M

---

## Summary

### Open — Priority Order

| Priority | Key | Summary | Effort |
|----------|-----|---------|--------|
| P2 | [EAGLE-254](https://tracker.nci.nih.gov/browse/EAGLE-254) | research tool — high-variance latency + inconsistent source citations | M |

**S** = small (< 1 day), **M** = medium (1-2 days), **L** = large (3-5 days)
