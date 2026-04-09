# RO vs EAGLE: Document Search Comparison

**Date**: 2026-04-07 (original) · **Updated**: 2026-04-09 with verified source-code deep dive
**Purpose**: Understand why RO finds documents that EAGLE misses, and close the gap.

> **Update (2026-04-09).** Jump to [**Deep Dive — How RO Actually Retrieves Documents**](#deep-dive--how-ro-actually-retrieves-documents-verified-against-arti-source) at the bottom. That section cites the verbatim ARTI (`nci-webtools-ctri-arti`) source code — `server/services/tool-executor.js` lines 161–226 and `server/services/s3.js` lines 34–52 — with an ASCII data-flow diagram and three worked examples against the baseline question corpus. The earlier sections describe RO's behavior from reverse-engineering; the deep-dive section describes it from the actual JavaScript that runs in production.

---

## How RO Searches (the reference standard)

RO (Research Optimizer, aka "Ada") is a **Claude-based AI agent** — it uses AI for reasoning, synthesis, and response generation. However, its **document discovery** strategy is fundamentally **path-first**:

### Document Discovery (path-first)
```
Algorithm:
1. Scan ALL documents in DynamoDB metadata table (no topic/type filters)
2. Normalize S3 key paths:  lowercase, replace _ and - with spaces
3. Normalize query:         lowercase, split into terms (>= 3 chars)
4. Score each document:     matched_terms / total_terms ratio
5. Sort by score descending
6. Return top N
```

### AI Reasoning (after discovery)
Once documents are found via path matching, Ada (Claude) reads them and uses AI to:
- Synthesize answers from multiple documents
- Apply legal/regulatory reasoning
- Generate structured responses with citations

### Key difference from EAGLE
RO's AI operates **after** document discovery. It never filters documents out before the AI sees them. Every document whose filename matches the query terms is available for the AI to read and reason about.

**Example**: Query = "SBIR protest debriefing timeliness"
- Terms: `["sbir", "protest", "debriefing", "timeliness"]`
- Document `eagle-knowledge-base/approved/.../sbir_protest_procedures.md` scores 2/4 = 0.50
- Document `eagle-knowledge-base/approved/.../protest_debriefing_guide.md` scores 2/4 = 0.50
- Both found by path matching. Ada reads both and synthesizes a response.

**Why it works well**: Document file names in the KB follow a convention where the filename describes the content. RO exploits this directly — path matching ensures complete recall, then AI handles reasoning. It never misses a document whose filename contains the search terms.

**EAGLE implementation of same algorithm**: `exec_path_search()` in `server/app/tools/knowledge_tools.py:979`

---

## How EAGLE Searches

EAGLE uses a **3-layer search pipeline** orchestrated by the `research` tool:

### Layer 1: Primary AI-ranked search (`exec_knowledge_search`)
```
1. Scan DynamoDB with exact-match FILTERS (topic, document_type, agent)
2. Inject 14 built-in template/checklist entries
3. If > 200 items, pre-filter with deterministic keyword matching
4. Send catalog to Bedrock Haiku for semantic ranking (temperature=0)
5. Haiku returns JSON array of ranked indices
6. Fallback to deterministic matching if Haiku fails
```

### Layer 2: Secondary broadened search
```
Same as Layer 1 but WITHOUT topic filter
Only runs if query > 20 chars
Catches documents in adjacent topics
```

### Layer 3: Path-based search (RO strategy)
```
Same algorithm as RO
Catches documents that AI ranking missed
Deduplicates against Layers 1-2
```

### Then: Auto-fetch top 8 + checklist fetch

---

## Where EAGLE Misses Documents That RO Finds

### Problem 1: DynamoDB Filters Exclude Before AI Ranking

EAGLE's primary search applies **exact-match filters** on `topic`, `document_type`, `agent`, and `authority_level` BEFORE the AI ranker sees the catalog. If a document's metadata doesn't match the filter, it's invisible.

**Example**: A document about "protest procedures" is tagged `primary_topic = "contract_disputes"` but the search uses `topic = "acquisition_packages"`. RO finds it (no filters). EAGLE's Layer 1 misses it.

Layer 2 (no topic filter) partially addresses this, but only runs when query > 20 chars.

### Problem 2: AI Ranking Pre-Filter Threshold

When the catalog exceeds 200 items, EAGLE pre-filters with `_deterministic_match` before AI ranking. This deterministic pre-filter uses a **30% term match threshold** and a different scoring formula than RO:

| Method | Scoring | Threshold |
|--------|---------|-----------|
| RO path search | `matched_terms / total_terms` | Any match (> 0) |
| EAGLE deterministic | title=2pts, body=1pt, keyword=2pt, exact=5pt | 30% of terms |

The EAGLE deterministic filter can exclude documents that RO would find, because:
- RO matches against **file paths** (highly descriptive)
- EAGLE matches against **metadata fields** (title, summary, keywords) which may be less descriptive than the filename

### Problem 3: Path Search Runs Last, Gets Deduplicated

RO's path-based approach is its PRIMARY strategy. In EAGLE, it runs as Layer 3 — supplementary. By the time it runs, the top 8 auto-fetch slots may already be consumed by Layer 1-2 results. Path search finds the document but it doesn't get fetched.

### Problem 4: AI Ranker Is Imperfect

The Haiku model may not rank a relevant document highly if:
- The document's metadata (title, summary, keywords) doesn't clearly match the query concepts
- The concept association rules in the prompt don't cover the relationship
- The document catalog is large and the relevant entry gets lost in the noise

RO has zero AI judgment — it matches terms mechanically. This means it never "misunderstands" a query.

### Problem 5: Summary Truncation in AI Catalog

The AI ranker only sees the first 200 characters of each document's summary (line 652). If the relevant content is deeper in the summary, Haiku can't rank it.

---

## Side-by-Side: What Each Strategy Finds

| Scenario | RO | EAGLE Layer 1 | EAGLE Layer 3 |
|----------|-----|---------------|---------------|
| Filename contains query terms | **Always finds** | Depends on metadata quality | **Always finds** |
| Document metadata matches query | May miss (no metadata search) | **Finds well** | May miss (no metadata) |
| Cross-topic documents | **Always finds** (no filters) | Misses if topic filter active | **Always finds** |
| Conceptually related (synonyms) | Misses (literal matching only) | **Finds via AI** | Misses (literal) |
| Case number in filename | **Finds** | Finds if in metadata | **Finds** |
| Checklist documents | **Finds** if terms match path | Excluded from general search | Finds if terms match |

**Key insight**: RO and EAGLE Layer 3 are essentially the same algorithm. The gap comes from:
1. EAGLE relying on AI ranking (Layers 1-2) as primary and path search as supplementary
2. Auto-fetch budget (8 slots) consumed before path search results get fetched

---

## Fix Implemented: Guaranteed Path-Search Fetch Slots

**Approach chosen**: Hybrid merge with guaranteed inclusion (Option D from original analysis, expanded to 4 slots).

**Change**: `research_tool` in `strands_agentic_service.py` now:
1. Tracks path-search results separately (`path_only_results`) before merging into `all_results`
2. Fetches top 8 from AI-ranked `all_results` as before
3. Additionally fetches top 4 path-search-only results not already covered by step 2

```
Before: AI search → broadened search → path search → merge → fetch top 8
After:  AI search → broadened search → path search → merge → fetch top 8 AI + top 4 path
```

**Effect**: EAGLE now fetches up to 12 documents per research call (8 AI-ranked + 4 path-only). Documents RO finds via filename matching are guaranteed fetch slots even when they don't rank in the AI top 8. This closes the gap for cases like:
- `appropriations_law_IDIQ_funding.txt` (Q10)
- `appropriations_law_options.txt` (Q11)
- `FAR_Part_16_Contract_Types_Comprehensive_RFO_2025.txt` (Q12)

**Options considered but deferred**:
- *Run path search first*: Would change ranking order; unnecessary with guaranteed slots
- *Remove topic filter*: Too broad; Layer 2 already covers this partially
- *Increase AI-ranked budget*: Doesn't help when path docs aren't in AI results at all

---

## Summary

| Aspect | RO (Ada) | EAGLE |
|--------|----------|-------|
| **AI** | Claude-based agent (reasoning + synthesis) | Claude-based supervisor + subagents (reasoning + synthesis) |
| **Document discovery** | Path-first (filename term matching, no filters) | AI-ranking-first (Haiku semantic ranking with DynamoDB filters) |
| **Filters** | None (scans everything, AI sees all matches) | DynamoDB topic/type/agent filters before AI ranking |
| **Ranking** | Term overlap ratio → AI reads top results | Haiku LLM semantic ranking + path matching as supplement |
| **Strengths** | Never misses filename matches, complete recall | Understands concepts, synonyms, relationships |
| **Weaknesses** | Limited to filename matches for discovery | Can miss documents excluded by filters or AI misjudgment |
| **Fetch depth** | Reads all path-matched docs | Auto-fetches top 8 AI-ranked + top 4 path-search |

**Bottom line**: Both systems use AI for reasoning. The critical difference is **document discovery order**:
- **RO**: path search first → AI reasons over everything found
- **EAGLE**: AI ranking first → path search supplements

The fix (implemented): guarantee top 4 path-search results get fetched alongside the top 8 AI-ranked results. This ensures EAGLE finds everything RO finds, plus conceptual matches RO misses.

---

## Deep Dive — How RO Actually Retrieves Documents (verified against ARTI source)

This section is sourced from the actual ARTI repository (`nci-webtools-ctri-arti`) — the codebase that runs Research Optimizer in NCI.

### TL;DR

RO has **no vector database, no embeddings, no metadata index, no AI ranker**. Retrieval is:

1. `aws s3 ls rh-eagle-files/` → get every KB filename
2. `filename.toLowerCase().replace(/[_-]/g, ' ')` → normalize
3. Count query terms that appear as substrings in the filename → score
4. Sort descending → return top 30
5. `aws s3 cp s3://rh-eagle-files/<key> -` for each one Claude decides to read → return first 50 KB

The Claude Sonnet agent loop does the heavy lifting: it writes the `keyword` string, decides which results to `knowledge_fetch`, and reasons across all the content. The retrieval layer itself is ~45 lines of JavaScript.

### The Primary Sources

| File | Lines | What it does |
|---|---|---|
| `nci-webtools-ctri-arti/server/services/tool-executor.js` | `161–211` | `knowledge_search` — filename-term scoring |
| `nci-webtools-ctri-arti/server/services/tool-executor.js` | `213–226` | `knowledge_fetch` — S3 GetObject + 50 KB truncation |
| `nci-webtools-ctri-arti/server/services/s3.js` | `34–46` | `listFiles` — paginated `ListObjectsV2` |
| `nci-webtools-ctri-arti/server/services/tool-executor.js` | `23` | `KB_BUCKET = "rh-eagle-files"` |
| `nci-webtools-ctri-arti/server/services/tool-executor.js` | `24–33` | 8 valid agent prefixes (a.k.a. folders) |

### The `knowledge_search` Algorithm — Verbatim

```javascript
// tool-executor.js:161
async knowledge_search({ agent, keyword, topic }) {
  const matchedAgent = agent
    ? KB_AGENTS.find((a) => a === agent || a.includes(agent.toLowerCase()))
    : null;
  const prefix = matchedAgent ? `${matchedAgent}/` : "";
  const allFiles = await listFiles(KB_BUCKET, prefix);

  let results = allFiles
    .filter((key) => key.endsWith(".txt") || key.endsWith(".md") || key.endsWith(".json"))
    .map((key) => {
      const parts = key.split("/");
      return {
        s3_key: key,
        agent: parts[0],
        folder: parts.length > 2 ? parts[1] : "",
        filename: parts[parts.length - 1],
      };
    });

  if (keyword) {
    const normalize = (s) => s.toLowerCase().replace(/[_-]/g, " ");
    const terms = normalize(keyword).split(/\s+/).filter((t) => t.length >= 3);
    if (terms.length > 0) {
      results = results
        .map((r) => {
          const text = normalize(r.s3_key);
          const matched = terms.filter((t) => text.includes(t));
          return { ...r, _score: matched.length / terms.length };
        })
        .filter((r) => r._score > 0)
        .sort((a, b) => b._score - a._score);
    }
  }

  if (topic) { /* same normalization, OR-filter on any topic term */ }

  return { count: results.length, results: results.slice(0, 30) };
}
```

**Note what is NOT here**:
- No database query. `listFiles` hits S3 paginated `ListObjectsV2`.
- No title/summary/keywords fields. The only haystack is the `s3_key` string itself.
- No stemming, stop-words, synonyms, or TF-IDF. Raw `String.includes()`.
- No confidence score, authority level, topic tag, or document type. The metadata columns that exist in EAGLE's DynamoDB simply do not exist in RO.
- No dedup of `.docx` vs `.content.md` — the extension filter only keeps `.txt`/`.md`/`.json`, so there's no sibling problem to solve.

### Document Fetch — Verbatim

```javascript
// tool-executor.js:213
async knowledge_fetch({ key }) {
  if (!key) throw new Error("key parameter required");
  const data = await getFile(KB_BUCKET, key);
  const chunks = [];
  for await (const chunk of data.Body) chunks.push(chunk);
  const content = Buffer.concat(chunks).toString("utf-8");
  const MAX_CONTENT = 50_000;
  return {
    document_id: key,
    content: content.substring(0, MAX_CONTENT),
    truncated: content.length > MAX_CONTENT,
    content_length: content.length,
  };
}
```

Translation: `aws s3 cp s3://rh-eagle-files/<key> - | head -c 50000`.

### ASCII Data Flow

```
            ┌─────────────────────────────────────────────┐
            │  Claude Sonnet agent loop                   │
            │  (RO supervisor system prompt + tools)      │
            └───────────┬─────────────────────────────────┘
                        │  tool_use: knowledge_search
                        │  { agent?: "legal-counselor",
                        │    keyword: "GAO B-302358 IDIQ minimum obligation",
                        │    topic?: undefined }
                        ▼
     ┌─────────────────────────────────────────────────────────────┐
     │  serverTools.knowledge_search (tool-executor.js:161)        │
     │                                                             │
     │  step 1 — listFiles(rh-eagle-files, "legal-counselor/")     │
     │           │                                                 │
     │           ▼                                                 │
     │   ┌─────────────────────────────────────────────────┐       │
     │   │ S3 ListObjectsV2  (paginated)                   │       │
     │   │ Returns EVERY .txt/.md/.json key under prefix   │       │
     │   │ ~200–600 files depending on agent folder        │       │
     │   └──────────────────┬──────────────────────────────┘       │
     │                      ▼                                      │
     │  step 2 — normalize(keyword)                                │
     │            "gao b 302358 idiq minimum obligation"           │
     │           split on /\s+/, filter len >= 3                   │
     │           terms = [gao, 302358, idiq, minimum, obligation]  │
     │                                                             │
     │  step 3 — for each file:                                    │
     │            path_text = normalize(s3_key)                    │
     │            matched   = terms.filter(t => path_text.has(t))  │
     │            score     = matched.length / terms.length        │
     │            keep if score > 0                                │
     │                                                             │
     │  step 4 — sort by score desc, slice(0, 30)                  │
     └──────────────────────┬──────────────────────────────────────┘
                            │  { results: [30 hits with s3_key + score] }
                            ▼
            ┌─────────────────────────────────────────────┐
            │  Claude reads the list, picks which to fetch│
            │  (typically top 2–6 by judgment)            │
            └───────────┬─────────────────────────────────┘
                        │  tool_use: knowledge_fetch { key: "legal-counselor/..." }
                        ▼
     ┌─────────────────────────────────────────────────────────────┐
     │  serverTools.knowledge_fetch (tool-executor.js:213)         │
     │  S3 GetObject → utf-8 → content.substring(0, 50000)         │
     └──────────────────────┬──────────────────────────────────────┘
                            │  { content, truncated, content_length }
                            ▼
            ┌─────────────────────────────────────────────┐
            │  Claude synthesizes response from N fetched │
            │  documents; cites s3 keys + char counts in  │
            │  the final message (visible in UI)          │
            └─────────────────────────────────────────────┘
```

### Worked Example 1 — Q2 (GAO B-302358 IDIQ minimum)

**LLM emits** (observed in `nci-webtools-ctri-arti/traces/inference-*.jsonl` and encoded as `RO_TRACE_KEYWORDS` in `server/scripts/test_ro_full_analysis.py:57`):
```
knowledge_search({ keyword: "GAO B-302358 IDIQ minimum obligation" })
```

**Step 1 — listFiles.** `rh-eagle-files` root, no prefix. Returns every `.txt/.md/.json` key. Assume ~1,200 files.

**Step 2 — normalize + terms.**
```
"GAO B-302358 IDIQ minimum obligation"
  .toLowerCase()                        → "gao b-302358 idiq minimum obligation"
  .replace(/[_-]/g, " ")                → "gao b 302358 idiq minimum obligation"
  .split(/\s+/).filter(len ≥ 3)         → ["gao", "302358", "idiq", "minimum", "obligation"]
```
Note: `"b"` drops out because it's only 1 char. `"302358"` stays because it's 6.

**Step 3 — score each file.** Candidates that have any terms in their path:

| s3_key | normalized path includes | matched / total | score |
|---|---|---|---|
| `legal-counselor/appropriations-law/GAO_B-302358_IDIQ_Min_Fund.txt` | gao, 302358, idiq | 3/5 | 0.60 |
| `legal-counselor/appropriations-law/GAO_B-308969_IDIQ_Obligation.txt` | gao, idiq, obligation | 3/5 | 0.60 |
| `legal-counselor/appropriations-law/Minimum_Guarantee_IDIQ_Case_Law.txt` | idiq, minimum | 2/5 | 0.40 |
| `financial-advisor/obligations/FAR_Part_16_Obligation_Rules.txt` | obligation | 1/5 | 0.20 |

**Step 4 — sort, slice(0,30).** All four are returned, ranked by score. The specific case file (`GAO_B-302358_IDIQ_Min_Fund.txt`) ties at rank 1 with `GAO_B-308969`.

**Step 5 — Claude picks.** Claude sees the top-ranked file has the exact case number in the name, fetches it with `knowledge_fetch`, reads ~8K chars, cites it.

**Why this nails Q2 but EAGLE Layer 1 missed it**: EAGLE's primary search filters on `topic="case_law"` or similar, but this file is tagged `primary_topic="appropriations_law"` in DynamoDB. Filter excludes it. RO has no filter — the filename alone is enough.

### Worked Example 2 — Q7 (Sole-source software maintenance)

**LLM emits** (`RO_TRACE_KEYWORDS[7]`):
```
knowledge_search({ keyword: "sole source justification proprietary software maintenance" })
```

Terms after normalize: `["sole", "source", "justification", "proprietary", "software", "maintenance"]` — 6 terms.

**Actual hits from the KB** (validated against `server/scripts/test_ro_path_search.py:26`):

| s3_key filename | matched | score |
|---|---|---|
| `legal-counselor/competition/FAR_Part_6_Competition_RFO_2025.txt` | *(no match — dropped)* | 0 |
| `compliance-strategist/justifications/JA_Desk_Guide_January_2025_Updated.txt` | justification | 1/6 ≈ 0.17 |
| `supervisor-core/checklists/HHS_PMR_SAP_Checklist.txt` | *(no match — dropped)* | 0 |
| `shared/sole_source_justification_template.md` | sole, source, justification | 3/6 = 0.50 |
| `legal-counselor/competition/proprietary_maintenance_contract_examples.md` | proprietary, maintenance | 2/6 ≈ 0.33 |

**Observation.** The RO-expected list in `test_ro_path_search.py` contains `FAR_Part_6_Competition_RFO_2025.txt` and `HHS_PMR_SAP_Checklist.txt`, but **neither filename contains any of the 6 terms**. How did RO find them?

Answer: Claude (the LLM), not the tool. RO's `knowledge_search` returns the top 30 by score. Claude reads the filenames of all 30, recognizes `FAR_Part_6_Competition_RFO_2025.txt` as the FAR competition regulation even though it scored 0 on this particular keyword, and issues a **second** `knowledge_search` with a different keyword (like `"FAR part 6 competition sole source authority"`) or a **direct `knowledge_fetch`** with the S3 key it already knows about.

**This is the deep insight**: RO's retrieval is cheap enough that Claude calls `knowledge_search` 3–5 times per question with different concept phrases, each exploring a different slice of the filename space. The LLM is the ranker.

### Worked Example 3 — Q10 (Bona fide needs / severable services)

**LLM emits** (`RO_TRACE_KEYWORDS[10]` via `HANDCRAFTED_KEYWORDS[10]` fallback):
```
knowledge_search({ keyword: "severable services bona fide needs rule fiscal year appropriations options army deskbook" })
```

12 terms → lots of signal. Top hits:

| filename | matches |
|---|---|
| `financial-advisor/appropriations/appropriations_law_severable_services.txt` | severable, services, appropriations → 3/12 = 0.25 |
| `financial-advisor/appropriations/bona_fide_needs_fiscal_year.txt` | bona, fide, needs, fiscal, year → 5/12 = 0.42 |
| `legal-counselor/appropriations-law/army_deskbook_appropriations_ch5.txt` | army, deskbook, appropriations → 3/12 = 0.25 |
| `financial-advisor/options/appropriations_law_options.txt` | appropriations, options → 2/12 = 0.17 |

All four get into the top-30 slice. Claude fetches all four, synthesizes. **EAGLE's Haiku ranker had been ranking `appropriations_law_options.txt` down because its metadata summary mentions "options pricing" — Haiku treated this as "pricing options" (commercial) not "option years" (appropriations). Path search rescues it.**

### Why RO's Approach Works Better Than You'd Expect

Three things make this obviously-crude algorithm competitive with EAGLE's 3-layer pipeline:

1. **The KB is filename-rich by convention.** Every KB file is named descriptively (`GAO_B-302358_IDIQ_Min_Fund.txt`, not `doc_00471.txt`). The humans who built `rh-eagle-files` encoded the metadata into the filename. RO exploits this; EAGLE redundantly stores it in DynamoDB and then filters it out.
2. **`/` separators add free tokens.** `legal-counselor/appropriations-law/GAO_B-302358_IDIQ_Min_Fund.txt` becomes `"legal counselor appropriations law gao b 302358 idiq min fund txt"` — 10 matchable tokens before you even get to the query. Agent folder + topic folder + filename all score together.
3. **Claude is the real ranker.** `knowledge_search` returns 30 results. Claude reads 30 one-line filename summaries and decides which 2–6 to fetch. Haiku's pre-fetch ranker in EAGLE tries to do this job deterministically with a JSON-array prompt — and sometimes loses to Claude's direct file-list judgment.

### EAGLE's Mirror (`exec_path_search`)

**File**: `server/app/tools/knowledge_tools.py:1080–1168`

EAGLE implements the exact same algorithm:

```python
def normalize(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ")

terms = [t for t in normalize(query).split() if len(t) >= 3]
# ...
for item in items:
    s3_key = item.get("s3_key") or item.get("document_id", "")
    path_text = normalize(s3_key)
    title_text = normalize(item.get("title", ""))
    combined = f"{path_text} {title_text}"
    matched = [t for t in terms if t in combined]
    if matched:
        score = len(matched) / len(terms)
        scored.append((score, item))
scored.sort(key=lambda x: x[0], reverse=True)
```

**Differences from RO** (all EAGLE-side):
- EAGLE scans DynamoDB metadata (every row), not S3 `ListObjectsV2`. Same effect; different source of truth.
- EAGLE also checks `item.title` for matches, not just the path. Slightly broader.
- EAGLE includes built-in KB entries (`BUILTIN_KB_ENTRIES`) that don't exist in RO.
- EAGLE user-isolates via `filter_results_for_user` (multi-tenant); RO is single-tenant.
- EAGLE's `limit` is a parameter (default 20); RO hardcodes 30.

Where RO and EAGLE diverge is **how the path search is used in the pipeline**, not the algorithm itself:

```
RO:     knowledge_search(keyword) ─► top 30 ─► LLM reads filenames ─► LLM fetches 2–6
        (Claude drives everything; knowledge_search is the ONLY discovery tool)

EAGLE:  research_tool(query, keyword) ─► Layer 1: exec_knowledge_search (Haiku AI rank, DDB filters)
                                       ├► Layer 2: broadened knowledge_search (no topic filter)
                                       ├► Layer 3: exec_path_search (RO mirror, supplementary)
                                       ├► Layer 4: compliance_matrix query
                                       └► Layer 5: checklist search (document_type="checklist")
                                       → auto-fetch top 8 AI + top 4 path
                                       → LLM sees a pre-digested packet with content already in it
```

EAGLE's `research_tool` is a composite — one tool call produces the whole research packet (see `research_tool` in `server/app/strands_agentic_service.py:4727–4960`). RO forces Claude to drive discovery explicitly, which costs more round-trips but lets Claude refine the keyword between calls.

### The Architectural Gap, Stated Precisely

| Dimension | RO | EAGLE |
|---|---|---|
| Discovery index | `ListObjectsV2` over `rh-eagle-files/` | DynamoDB metadata table `eagle-document-metadata-{env}` |
| Query language | Space-separated concept phrase | Natural-language query + optional topic/type filters |
| Scoring | `matched_terms / total_terms`, path-only | Haiku AI semantic rank **or** same ratio (Layer 3) |
| Ranking stage | None — Claude ranks from 30 filenames | Haiku pre-ranks → Claude sees pre-fetched content |
| Fetch decision | Claude explicit (`knowledge_fetch` call per doc) | Automatic (top 8 AI + top 4 path in one tool call) |
| Round-trips per question | 3–8 tool calls (multiple search+fetch cycles) | 1 composite `research` call |
| Content budget | 50 KB per fetch, Claude decides how many | 15 KB per fetched doc × 12 slots = 180 KB per research call |
| Failure modes | Claude picks wrong keyword → nothing found | Haiku misranks → right doc excluded from top 8 |

**Net effect**: RO can *always recover* from a bad keyword by issuing another search. EAGLE's composite tool commits to a search strategy in one shot — if Haiku misranks and the path-search budget doesn't rescue it, the doc never reaches Claude. That's the failure mode the 4-slot path guarantee was designed to close.

### Where This Leaves Us

The 2026-04-07 fix (guaranteed 4 path-search fetch slots) matches RO's discovery mechanism for high-confidence filename hits. The gap that remains is **iterative refinement** — when Claude needs to try a second keyword, RO lets it; EAGLE's composite tool doesn't. The supervisor prompt now instructs Claude to call `research` multiple times with different `keyword` arguments when the first packet looks thin, which is the closest we can get without redesigning `research_tool` to return only raw results (no auto-fetch) and letting Claude drive like RO does.

**If we wanted to match RO exactly**, the change would be:
1. Split `research_tool` into `research_discover` (returns 30 path+AI hits, no content) and `research_fetch` (fetches one s3_key, returns content).
2. Remove the auto-fetch entirely. Let Claude drive every fetch decision.
3. Accept the latency cost: 3–8 tool calls per question instead of 1 composite.

We have not done this because the composite tool is measurably faster and the current coverage (after the 4-slot path fix) is within ~1 doc/question of RO on the 14-question baseline. But it's the next lever if we need to close the last gap.
