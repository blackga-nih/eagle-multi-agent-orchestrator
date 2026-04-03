# EAGLE QA Resolution Memo — EAGLE-70 through EAGLE-77

**Date:** 2026-04-03
**Author:** Gabriel Black
**Epic:** EAGLE-75 (EAGLE QA 1)
**Status:** All 7 tickets validated PASS

---

## Executive Summary

Seven QA issues (EAGLE-70 through EAGLE-77, excluding EAGLE-75 epic) were filed on 2026-03-24 after comparing EAGLE responses against the Research Optimizer reference implementation. All issues stemmed from three root causes: cascade enforcement gaps, KB search quality limitations, and missing guardrails on document generation. Over the past two weeks, six commits addressed these root causes. All 7 tickets now pass automated validation.

---

## Fix Summary

| Ticket | Issue | Root Cause | Fix Applied | Commit |
|--------|-------|------------|-------------|--------|
| EAGLE-70 | Agent uses web_search instead of KB search | Cascade not enforced | KB cascade enforcement + fetch depth tracking | `af83106` |
| EAGLE-71 | Missing NIH-specific policy layer in threshold answers | No NIH policy overlay prompt; research tool skipped 79% of cascades | Composite research tool with auto-fetch; PMR/FRC checklist enforcement | `7d3e8ac`, `98bc7ab` |
| EAGLE-72 | GAO B-302358 not found in KB | KB search overflow on large catalogs | Pre-filter large catalogs before AI ranking; cascade enforcement ensures KB-first | `c2a95e8`, `af83106` |
| EAGLE-73 | Missing bona fide needs document alongside severable services | AI ranking missed related concepts; agent fetched too few docs | Research tool auto-fetches top 4 KB results; fetch depth reminders | `7d3e8ac`, `af83106` |
| EAGLE-74 | Wrong FAR section (16.507 vs 16.505), missing 7th exception | KB uses HHS RFO numbering; agent cited RFO sections to users | RFO-to-FAR cross-reference in KB file + system prompt mapping | Uncommitted (this session) |
| EAGLE-76 | Web search before KB for SBIR protest question | Cascade violation | Cascade enforcement; checklist isolation keeps protest docs clean | `af83106`, `a522b2d` |
| EAGLE-77 | Template path not shown before document generation | Fast-path bypassed agent; no template lookup | Fast-path template search + agent-level guardrail | Uncommitted (this session) |

---

## Detailed Fix Descriptions

### EAGLE-70: KB Cascade Enforcement
**Problem:** Agent called `web_search` before `knowledge_search`, producing slower, less authoritative answers.

**Fix (commit `af83106`):** Added `_kb_tools_called` tracking to both subagent and service tool builders. The `web_search` tool now logs a `CASCADE VIOLATION` warning if no KB tool (`knowledge_search`, `search_far`) was called first. System prompt updated with mandatory "RESEARCH DEPTH" section requiring `knowledge_fetch` on at least 2 documents before responding. `_kb_depth` tracking (search count, fetch count, chars read) triggers `_fetch_reminder` injection when depth is insufficient.

**Validation:** Jira baseline question hits `query_compliance_matrix` + `research` tools. No cascade violations.

---

### EAGLE-71: NIH Policy Layer
**Problem:** Agent returned basic thresholds ($15K MPT, $350K SAT) but didn't offer NIH-specific policy overlay (purchase card supplements, HCA approval requirements, NIH procedural steps).

**Fix (commits `7d3e8ac`, `98bc7ab`, `a522b2d`):** Three changes combined:
1. **Composite research tool** (`7d3e8ac`): Replaced the multi-step cascade (knowledge_search → knowledge_fetch → query_compliance_matrix) that the agent skipped 79% of the time with a single deterministic server-side tool. Auto-fetches top 4 KB results including NIH policy documents.
2. **Checklist enforcement** (`98bc7ab`): Compliance matrix now returns HHS/NIH-specific document requirements (FRC + PMR) with S3 keys, ensuring the agent fetches NIH checklists alongside FAR requirements.
3. **Checklist isolation** (`a522b2d`): Checklists excluded from general `knowledge_search` results; fetched via dedicated `document_type="checklist"` search in the research tool. Prevents checklist noise from polluting general KB answers while ensuring they're always included when relevant.

**Validation:** Jira baseline response (12,013 chars) mentions NIH-specific policies, uses 5 tools including `research`, `search_far`, `knowledge_search`, and `knowledge_fetch`.

---

### EAGLE-72: GAO B-302358 Retrieval
**Problem:** Agent couldn't find the GAO B-302358 IDIQ minimum obligation decision in the knowledge base.

**Fix (commits `c2a95e8`, `af83106`):**
1. **KB search overflow fix** (`c2a95e8`): Large metadata catalogs (>200 items) caused a 208K-token context overflow when passed to Bedrock AI ranking. Added deterministic pre-filtering (keyword/title matching) before AI ranking to keep the ranked set manageable.
2. **Cascade enforcement** (`af83106`): Ensures `knowledge_search` runs first, and `knowledge_fetch` is called on top results to read full GAO decision text.

**Validation:** Response (6,196 chars) correctly retrieves and cites B-302358, uses `knowledge_search` → `search_far` → `knowledge_fetch` → `web_search` → `web_fetch` cascade.

---

### EAGLE-73: Bona Fide Needs + Severable Services
**Problem:** Agent found `appropriations_law_severable_services.txt` but missed `appropriations_law_time_bona_fide_needs.txt`. AI ranking didn't connect "fiscal year appropriation" with "bona fide needs."

**Fix (commits `7d3e8ac`, `af83106`):**
1. **Research tool auto-fetch** (`7d3e8ac`): The composite research tool auto-fetches top 4 KB results (not just the top 1-2 the agent would select). This catches related documents that AI ranking surfaces but the agent would skip.
2. **Fetch depth enforcement** (`af83106`): `_fetch_reminder` injection ensures the agent reads at least 2 documents / 5K chars before responding, catching the second file.

**Validation:** Response (12,177 chars) covers both severable/non-severable rules AND bona fide needs under 31 U.S.C. 1502(a). Tools: `search_far` + `research`.

---

### EAGLE-74: FAR 16.505 Fair Opportunity Exceptions
**Problem:** Agent listed 6 exceptions instead of 7, cited wrong FAR section (16.507-6 instead of 16.505), and missed exception (F) Small Business Set-Asides.

**Root Cause:** The KB file `FAR_Part_16_IDIQ_Comprehensive_RFO_2025.txt` uses HHS Class Deviation 2026-01 (RFO) numbering where FAR 16.505 is renumbered as 16.507-6. Exception (F) appears as a separate paragraph (c) rather than in the numbered exception list. The agent faithfully cited what it read.

**Fix (this session, uncommitted):**
1. **KB file update**: Added an RFO-to-standard-FAR cross-reference table at the top of the FAR Part 16 KB document, explicitly mapping every 16.507-x section to its standard 16.505 equivalent. Includes a note: "There are seven (7) exceptions — (F) small business set-asides appears as paragraph (c) in this document."
2. **System prompt update**: Added FAR SECTION ACCURACY guidance with explicit RFO→FAR mappings (16.507-6 = 16.505(b)(2)(i), etc.) and instruction to never cite 16.507-x to users.

**Validation:** Re-run produces all 7 exceptions (A-G), cites 16.505 correctly, includes (F) small business set-asides, zero 16.507 references.

---

### EAGLE-76: SBIR Protest KB vs Web
**Problem:** Agent used web search instead of KB for SBIR protest/debriefing question, missing 9 protest-guidance documents in the knowledge base.

**Fix (commits `af83106`, `a522b2d`):**
1. **Cascade enforcement** (`af83106`): Forces KB search before web search. Agent now searches `knowledge_search` first for protest-guidance files.
2. **Checklist isolation** (`a522b2d`): General KB results no longer polluted by checklist entries, so protest-guidance documents rank higher in search results.

**Validation:** Response (10,596 chars) uses `knowledge_search` + `knowledge_fetch`, cites protest guidance documents, covers GAO bid protest procedures and stay provisions.

---

### EAGLE-77: Template Path Before Document Generation
**Problem:** When asked to generate a SOW, agent went straight to `create_document` without identifying which KB template it was using or showing the S3 path.

**Root Cause:** The "fast document path" (`_maybe_fast_path_document_generation`) bypassed the Strands agent entirely, calling `exec_create_document` directly with no KB template lookup. System prompt and tool docstring instructions were irrelevant because the agent was never invoked.

**Fix (this session, uncommitted):**
1. **Fast-path template search**: Added `knowledge_search(document_type='template')` call to the fast path before generating. Template name and S3 path are included in the response: `**Template:** Using template: {name} ({s3_key})`.
2. **Agent-level guardrail**: Added shared `_template_search_done` flag between KB service tools and `create_document_tool`. If the agent path is used and `create_document` is called without a prior template search, it returns a `TEMPLATE SEARCH REQUIRED` block.
3. **Both code paths updated**: Streaming (`sdk_query_streaming`) and non-streaming (`sdk_query`) response builders both include template info.

**Validation:** Response now shows: `Using template: Statement of Work (SOW) Template - Eagle v2 (eagle-knowledge-base/approved/supervisor-core/essential-templates/statement-of-work-template-eagle-v2.docx)`.

---

## Validation Results

All 7 tickets tested with targeted Jira baseline questions on 2026-04-03:

| Ticket | Category | Verdict | Response | Tools Used |
|--------|----------|---------|----------|------------|
| EAGLE-70 | Cascade / KB Search | PASS | 4,332 chars | query_compliance_matrix, research |
| EAGLE-71 | NIH Policy Layer | PASS | 12,013 chars | query_compliance_matrix, research, search_far, knowledge_search, knowledge_fetch |
| EAGLE-72 | GAO KB Retrieval | PASS | 6,196 chars | knowledge_search, search_far, knowledge_fetch, web_search, web_fetch |
| EAGLE-73 | Bona Fide Needs | PASS | 12,177 chars | search_far, research |
| EAGLE-74 | FAR 16.505 Exceptions | PASS | 4,406 chars* | search_far, knowledge_fetch |
| EAGLE-76 | SBIR KB vs Web | PASS | 10,596 chars | knowledge_search, knowledge_fetch |
| EAGLE-77 | Template Path | PASS | 255 chars | create_document (+ knowledge_search via fast-path) |

*EAGLE-74 re-verified after fix — original run was FAIL.

---

## Commits (Chronological)

| Date | Commit | Description |
|------|--------|-------------|
| 2026-03-27 | `af83106` | KB cascade enforcement + compliance matrix deep research |
| 2026-03-28 | `98bc7ab` | Enforce checklist lookup before document recommendations |
| 2026-03-29 | `7d3e8ac` | Add composite research tool — dynamic KB + checklist in one call |
| 2026-03-31 | `c2a95e8` | Fix KB search overflow, safeguard wipe script |
| 2026-04-02 | `a522b2d` | Isolate checklist fetching in research tool |
| 2026-04-03 | *pending* | EAGLE-74 RFO-to-FAR mapping + EAGLE-77 template search guardrail |

---

## Remaining Work

- [ ] Commit and push EAGLE-74 + EAGLE-77 fixes
- [ ] Update Jira tickets with validation screenshots
- [ ] Close EAGLE-75 epic after all children are resolved
- [ ] Add automated eval tests for EAGLE-70 through EAGLE-77 to `test_strands_eval.py`
