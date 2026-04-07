# RO vs EAGLE: Document Search Comparison

**Date**: 2026-04-07
**Purpose**: Understand why RO finds documents that EAGLE misses, and close the gap.

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
