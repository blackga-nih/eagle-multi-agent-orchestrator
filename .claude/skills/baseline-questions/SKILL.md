---
name: baseline-questions
description: >
  Run the EAGLE baseline evaluation suite — sends all baseline acquisition
  questions (read dynamically from Excel) to the running EAGLE server, captures
  responses with full metadata, writes results to the Use Case List Excel
  workbook, judges and scores against the previous version, and generates an
  HTML comparison report. Use when someone says "run baseline", "baseline
  questions", "baseline eval", "run the baseline questions", "re-run baseline",
  "test against baseline", "score baseline", or references comparing EAGLE
  versions on the standard question set.
model: opus
---

# Baseline Questions — EAGLE Version Evaluation

Run all baseline federal acquisition questions (read dynamically from Excel column D)
against the live EAGLE server, capture responses with metadata, write to Excel, judge
against the previous version, and produce a scored HTML comparison report.

## Arguments

**Required**: `VERSION_LABEL` — the version tag (e.g., `v5`, `v6`, `v7`)

**Optional**:
- `--server=URL` — server base URL (default: `http://localhost:8000`)
- `--xlsx=PATH` — Excel workbook path (default: `Use Case List.xlsx` in repo root)
- `--run-only` — run questions and save responses, skip judging
- `--judge-only` — skip running, judge the most recent responses column
- `--tenant=ID` — tenant for API calls (default: `dev-tenant`)

Parse `$ARGUMENTS` to extract VERSION_LABEL (first word matching `v\d+`) and flags.

---

## Phase 1: Preflight Checks

### 1a. Verify Server is Running

```bash
curl -s http://localhost:8000/api/health | python -c "import sys,json; d=json.load(sys.stdin); print(f'Server OK: {d[\"service\"]} {d[\"version\"]}')" 2>/dev/null || echo "SERVER NOT REACHABLE"
```

If the server is not reachable, STOP and tell the user to start it:
```
uvicorn app.main:app --reload --port 8000
```

### 1b. Verify Excel Exists

Check that the Use Case List workbook exists at the expected path. The workbook
must have a sheet named "Baseline questions" with questions in column D (rows 2-7).

### 1c. Detect Next Available Columns

Read the Excel header row to find the next empty column for responses and the
6 scoring columns after it. The pattern is:

```
Col N:   "EAGLE {version} Response ({date})"
Col N+1: "EAGLE {version} Accuracy (0-5)"
Col N+2: "EAGLE {version} Completeness (0-5)"
Col N+3: "EAGLE {version} Sources (0-5)"
Col N+4: "EAGLE {version} Actionability (0-5)"
Col N+5: "EAGLE {version} Total (0-20)"
Col N+6: "{version} vs RO + {prev_version} Comparative Judgment"
```

Scan row 1 to find the first empty column. Also identify the previous version's
response column and score columns for comparison during judging. **Always read
column E (RO Response) — this is the reference standard for all judging.**

---

## Phase 2: Run Baseline Questions

Run the baseline script. It sends 6 questions sequentially (each needs full model
attention) with a fresh session per question.

```bash
cd server && python ../.claude/skills/baseline-questions/scripts/run_baseline.py \
  --version {VERSION_LABEL} \
  --server {SERVER_URL} \
  --xlsx "{XLSX_PATH}" \
  --tenant {TENANT_ID}
```

The script:
1. Reads questions from Excel column D, rows 2-7
2. Sends each to `POST /api/chat` with headers:
   - `X-User-Id: baseline-eval`
   - `X-Tenant-Id: {tenant}`
   - `X-User-Email: baseline@eval.test`
   - `X-User-Tier: advanced`
3. Captures: response text, tools_called, usage tokens, elapsed time, session_id
4. Saves raw JSON to `scripts/baseline_{version}_results.json`
5. Writes responses to the next available Excel column with green header
6. Prints a per-question summary table

**Timeout**: 5 minutes per question. Complex questions (Q5 SBIR protest) can take
2-3 minutes with deep KB research.

**Expected tool patterns** (for sanity checking):
- Q1 (Thresholds): `query_compliance_matrix` — simple lookup
- Q2 (GAO B-302358): `knowledge_search` + possibly `knowledge_fetch`, `web_search`, `legal_counsel`
- Q3 (Severable): `knowledge_search` + `knowledge_fetch`
- Q4 (Fair Opportunity): `search_far` + `knowledge_fetch`
- Q5 (SBIR Protest): `knowledge_search` + `search_far` + `knowledge_fetch` — most complex
- Q6 (Design): No tools — design discussion, not regulatory

If a question gets no tools at all (except Q6), that is a yellow flag — the cascade
enforcement may not be working.

If `--run-only` was passed, stop here. Otherwise proceed to Phase 3.

---

## Phase 3: Judge and Score

This phase requires human-quality judgment. Read the new EAGLE responses, the
**RO (Research Optimizer) reference responses from column E**, and the previous
version's responses, then score each on 4 dimensions.

### 3a. Read All Versions

Read the raw JSON results file for the new version — it includes both the EAGLE
response and the RO reference response for each question. Also read the previous
version's responses from the Excel (the column immediately before the scoring
columns for the prior version).

**Column E (RO Response) is the gold-standard reference.** These are the responses
from the Research Optimizer — the predecessor system. Every EAGLE response should be
compared against the RO response to assess whether EAGLE matches or exceeds it in
accuracy, completeness, sources, and actionability.

### 3b. Score Each Question

For each question (Q1-Q6), evaluate the new EAGLE response on 4 dimensions (0-5 each),
**comparing against the RO reference response in column E**:

| Dimension | What to assess |
|-----------|---------------|
| **Accuracy** | Are the facts, citations, dollar amounts, FAR references correct? Compare against the RO response — does EAGLE match the RO's factual claims? Deduct for wrong FAR section numbers, incorrect thresholds, fabricated case citations |
| **Completeness** | Does it cover all aspects of the question? Compare against the RO response — does EAGLE cover the same topics? Are there missing exceptions, missing procedural steps, or incomplete analysis that the RO covered? |
| **Sources** | Does it cite primary sources (KB files, FAR sections, case law)? Compare against the RO's citations — does EAGLE cite the same or better sources? Are citations specific (file paths, section numbers) vs vague? Did it fetch full documents or answer from summaries? |
| **Actionability** | Can a CO act on this response? Does it include practical next steps, decision tables, checklists, or worked examples? Compare against the RO — is EAGLE's output as actionable? |

### 3c. Write Comparative Judgment

For each question, write a comparative judgment that includes:

1. **Winner declaration** — first line: `EAGLE {v} > RO (improved)` or `EAGLE {v} = RO (comparable)` or `EAGLE {v} < RO (regression)`
2. **RO comparison** — what did the RO response cover that EAGLE did/didn't? What did EAGLE add beyond the RO?
3. **Key improvements or regressions vs prior EAGLE version** — what specifically changed from vN-1
4. **Tools comparison** — `v{N-1}=tools_list | v{N}=tools_list`
5. **Cascade effect** — did the KB cascade enforcement produce different behavior?
6. **Source gap status** — which sources from the RO response are missing in EAGLE? Which are now covered?
7. **Verdict** — one-line summary

### 3d. Write Scores to Excel

Write the scoring script or use openpyxl inline to write:
- 4 dimension scores (cols N+1 through N+4)
- Total score (col N+5, sum of 4 dimensions)
- Comparative judgment text (col N+6)

Use green header fill (`#2E7D32`) for the new version columns. Set column widths:
- Score columns: 12-14
- Judgment column: 100

### 3e. Print Summary Report

Print a table comparing scores:

```
Q#    Acc  Comp  Src  Act  Total  Prev Total  Delta  Verdict
Q1      5     5    4    5  19/20      18/20      +1  v5 = v4 (no change)
...
AVG                      19.5/20    18.5/20    +1.0

v{N} wins: X/6 | Ties: Y/6 | v{N-1} wins: Z/6
```

Then print the KB CASCADE ENFORCEMENT IMPACT section showing:
- Which questions changed tool usage patterns
- Which source gaps were closed/partially closed/still open
- Whether `knowledge_fetch` is being called after search (the primary metric)

---

## The 6 Baseline Questions

These are fixed — they test a range of complexity from simple threshold lookups
to multi-layered procedural analysis:

| Q# | Row | Category | Question Summary |
|----|-----|----------|-----------------|
| Q1 | 2 | Threshold | MPT and SAT under FAC 2025-06 |
| Q2 | 3 | Case Law | GAO B-302358 IDIQ minimum obligation |
| Q3 | 4 | Appropriations | Severable vs non-severable funding rules |
| Q4 | 5 | IDIQ | Fair opportunity exceptions under FAR 16.505 |
| Q5 | 6 | Protest | SBIR elimination + debriefing + protest procedural analysis |
| Q6 | 7 | Design | Acquisition workflow UX sequencing discussion |

Q1 tests the compliance matrix tool. Q2-Q5 test KB research depth (the primary
target of cascade enforcement). Q6 tests general reasoning with no tools.

---

## Scoring Rubric Reference

### 5/5 — Exceptional
- All facts correct with specific citations
- Complete coverage of all aspects
- Primary sources cited with file paths or section numbers
- Actionable tables, checklists, or worked examples

### 4/5 — Strong
- Facts correct, minor citation gaps
- Covers main aspects, may miss edge cases
- Sources cited but not all primary
- Useful but could be more specific

### 3/5 — Adequate
- Core facts correct, some vagueness
- Covers the main question but misses subtopics
- Generic source references
- General guidance without specific steps

### 2/5 — Weak
- Some factual errors or confusion
- Incomplete — misses major aspects
- Few or no source citations
- Vague, hard to act on

### 1/5 — Poor
- Significant factual errors
- Answered wrong question or mostly irrelevant
- No sources
- Not actionable

### 0/5 — Failure
- Completely wrong or no response
- Answered a different question entirely

---

## Phase 4: Generate HTML Report

**ALWAYS generate the HTML report after scoring.** Run the report generator:

```bash
cd server && python ../.claude/skills/baseline-questions/scripts/generate_report.py \
  --version {VERSION_LABEL} \
  --scores scripts/baseline_{version}_scores.json
```

The report includes:
- Summary bar (total score, wins/ties/losses, docs cited)
- Per-question score strip
- KB coverage comparison (shared/EAGLE-only/RO-only documents)
- Per-question cards with: tools, doc pills, score grid, verdict, side-by-side responses
- System prompt comparison (EAGLE vs RO supervisor)

Output: `scripts/baseline_{version}_report.html`

---

## Output Files

| File | Location | Contents |
|------|----------|---------|
| Raw JSON | `scripts/baseline_{version}_results.json` | Full response data per question |
| Scores JSON | `scripts/baseline_{version}_scores.json` | Per-question scores and verdicts |
| HTML Report | `scripts/baseline_{version}_report.html` | Visual comparison report |
| Excel responses | `Use Case List.xlsx` col N | Response text |
| Excel scores | `Use Case List.xlsx` cols N+1 to N+6 | Scores + judgment |

---

## Interpreting Results

**Comparing against the RO (Research Optimizer) reference in column E:**
- The RO response is the gold standard from the predecessor system
- Every EAGLE response should **match or exceed** the RO in accuracy and completeness
- If an EAGLE response misses facts, citations, or procedural steps that the RO covered,
  note these as "source gaps" in the comparative judgment
- If EAGLE adds content beyond the RO (e.g., decision tables, additional FAR citations,
  worked examples), note these as improvements

**What to look for in the cascade enforcement:**
- Q3 and Q4 are the primary canaries — in v4 these were answered from summaries.
  After cascade enforcement, they should show `knowledge_fetch` in the tools list.
- Q5 already triggered deep research in v4 — it should maintain or improve.
- Q2 is variable — sometimes triggers web_search, sometimes legal_counsel subagent.

**Score deltas to expect:**
- +1 to +3 per question when cascade enforcement works (sources + actionability improve)
- 0 delta on Q1 (threshold lookup, no cascade needed) and Q6 (design, no tools)
- Regression on any question is a red flag — investigate immediately

**When to re-run:**
- After any change to `strands_agentic_service.py` tool builders or system prompt
- After knowledge base content changes
- After model upgrades (new Claude version on Bedrock)
- Before and after major releases
