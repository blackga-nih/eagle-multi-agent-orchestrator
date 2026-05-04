# MEMORANDUM

**TO:** NCI Office of Acquisitions; EAGLE Engineering
**FROM:** EAGLE Engineering
**DATE:** 2026-05-01
**SUBJECT:** Proposal — Build a Graphify knowledge graph over the EAGLE approved knowledge base to improve acquisition-package authoring accuracy
**STATUS:** Draft for review · v1

---

## 1. Executive summary

We propose building a knowledge graph over EAGLE's 257 approved knowledge-base documents (`s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/`) using **Graphify** (`safishamsi/graphify`, PyPI `graphifyy`), a recently released open-source tool that extracts entities, relationships, and clusters from prose corpora. The graph would be **additive** to EAGLE's existing S3 vector index and would unlock structural and multi-hop queries that vector retrieval cannot answer — most importantly, deterministic **package-completeness checks**, **threshold-driven pathway routing**, and **citation-grounded document generation** for SOW, IGCE, J&A, and other acquisition artifacts.

First-run indexing is estimated at **15–30 minutes** of wall time and single-digit-dollars in Claude API spend. Recommended next step is a **10-file pilot** (~30 minutes) before committing to the full corpus and supervisor integration.

---

## 2. Background — what's in the approved KB

| Metric | Value |
|--|--|
| Total objects | 257 |
| Total size | ~12.9 MB |
| `.txt` | 214 (directly supported by Graphify) |
| `.pdf` | 4 (directly supported — citation mining) |
| `.docx` | 34 (requires conversion to `.md`/`.txt`) |
| `.xlsx` | 4 (requires conversion) |
| `.doc` | 1 (requires conversion) |

Content includes FAR/HHSAR-derived guidance, NIH supplements, J&A and SOW templates, PMR checklists, agile contracting guidance (TechFAR), human-subjects research rules (45 CFR 46), and technical-standards reference material.

---

## 3. What Graphify is

Graphify is an open-source Claude Code skill (released 2026-04-03; ~22k GitHub stars within 10 days) that turns any folder of code, documents, papers, and images into a queryable knowledge graph. Internally it combines Tree-sitter for code, Claude-driven semantic extraction for prose, optional vision models for images, NetworkX as the graph store, and Leiden clustering for community detection.

A key privacy property: only *semantic content* is sent to the upstream model — never raw source files. The CLI provides `query`, `path`, `explain`, and `add` primitives, plus an `--update` flag for incremental re-extraction.

---

## 4. Why this matters for Office of Acquisitions

EAGLE's current retrieval is similarity-based. That is good at *"find me passages about X"* but cannot answer the questions that actually drive acquisition-package quality:

### 4.1 Package completeness checking (highest-value)

The graph encodes nodes such as `Justification_and_Approval_Over_350K`, `FAR_6.303`, `IGCE`, `PMR_Common_Requirements`, with edges like `requires`, `cites`, `supersedes`. Given a draft package, an agent traverses from the package-type node and verifies every required edge is satisfied. Today RAG can *retrieve* a J&A template; only the graph can *enforce the dependency closure*.

### 4.2 Threshold-aware pathway routing

Federal procurement is a decision tree of dollar thresholds, contract types, and authority sources. The graph models thresholds as numeric attributes on nodes (`SAT=$250K`, `J&A_floor=$350K`, `micro_purchase=$10K`) connected to the procedures they unlock. A user enters *"$425K, sole source, IT services"*; the graph returns the exact pathway and required templates instead of a regenerated LLM guess.

### 4.3 Citation-grounded document generation

`document-generator` today drafts SOW/IGCE/J&A from retrieved chunks. The graph adds a grounding step: before drafting, the generator asks the graph *"what must this document cite?"* and receives a deterministic node list with S3 keys. Citations stop being model-memory and become graph-derived — directly addressing the citation-verify and compliance-matrix work currently scoped in phases 3–6 of the compliance-matrix initiative.

### 4.4 Supersession and conflict detection

Graphify models temporal supersession via edges. When a specialist retrieves older guidance, the agent can ask *"is anything superseding this?"* and surface the newer node, rather than silently quoting stale content.

### 4.5 Explainability for COs

Every clause in a generated package can carry a path: *"FAR 13.501(b) → because micro-purchase exceeded → because vendor is sole source → because [J&A justification node]"*. That is auditable in a way embedding similarity is not.

### 4.6 Precedent reuse

Leiden clustering groups structurally similar concepts. *"Show me past packages structurally similar to this intake"* — same threshold band, same contract type, same regulatory cluster — gives COs starting material instead of a blank page.

---

## 5. How it slots into EAGLE

| Existing component | What the graph adds |
|--|--|
| `oa-intake` skill | Threshold-driven pathway selection (§4.2) replaces heuristic routing |
| `compliance-strategist` specialist | Completeness checks (§4.1) become graph traversals |
| `document-generator` skill | Citations come from graph node IDs (§4.3), not LLM memory |
| `legal-counselor` specialist | Supersession check (§4.4) before quoting any clause |
| Compliance-matrix work (phases 3–6) | Graph becomes the natural backing store for matrix relationships |
| S3 vector index (`eagle-kb-approved`) | Stays — graph is additive; vectors still do passage retrieval |

The graph and vector index are complementary: vectors answer *"what does this say"*, graph answers *"what does this require, connect to, or supersede"*. The Strands supervisor invokes both.

---

## 6. Estimated time and cost

| Phase | Estimate | Notes |
|--|--|--|
| S3 sync (257 objects, 12.9 MB) | ~30 s | one `aws s3 sync` |
| Convert 39 Office docs (`.docx`/`.xlsx`/`.doc`) to `.md` | ~2–4 min | pandoc + small Python loop for `.xlsx` |
| Graphify indexing pass (218 prose + 4 PDFs) | ~10–25 min | Claude-API-bound; ~3–6 s/file × 4–8 workers; PDFs add ~30 s for citation mining |
| Leiden clustering + graph write | ~30–60 s | one-shot, small graph |
| First sanity query | ~5 s | |
| **Total first run** | **~15–30 min** | |
| Incremental re-runs (`--update`) | ~1–3 min | only changed files re-extracted |

Estimated Claude API cost for the full first pass: **single-digit dollars** based on ~50 KB average file size and one extraction call per prose file. A 10-file pilot will firm this up before commitment.

---

## 7. Sample workflow

Commands below are verbatim from the Graphify README; the S3 source matches the path already used by the in-repo `s3-knowledge-base-sync` skill.

```bash
# 0. Install (one-time)
uv tool install graphifyy && graphify install
graphify claude install

# 1. Pull approved KB to a local working dir
mkdir -p ./eagle-kb-graph/raw
aws s3 sync \
  s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/ \
  ./eagle-kb-graph/raw/ \
  --profile eagle --region us-east-1

# 2. Convert the 39 Office files to markdown
cd ./eagle-kb-graph/raw
find . -iname '*.docx' -o -iname '*.doc' | while read f; do
  pandoc "$f" -o "${f%.*}.md" && rm "$f"
done
python -c "
import pathlib, pandas as pd
for x in pathlib.Path('.').rglob('*.xlsx'):
    for sheet in pd.ExcelFile(x).sheet_names:
        df = pd.read_excel(x, sheet_name=sheet)
        x.with_suffix(f'.{sheet}.md').write_text(df.to_markdown(index=False))
    x.unlink()
"

# 3. Build the graph
cd ..
graphify ./raw

# 4. Query / inspect
graphify query   "Which clauses govern J&A over \$350K?"
graphify path    "FAR_6.303" "Justification_and_Approval_Over_350K_Template"
graphify explain "PMR Common Requirements"

# 5. Future re-runs after S3 sync
graphify ./raw --update
```

---

## 8. Tradeoffs and risks

1. **Schema curation is the real work.** Graphify auto-extracts entities and edges, but for regulated content the entity types (`Clause`, `Threshold`, `Template`, `Determination`, `Role`) and edge labels (`requires`, `cites`, `supersedes`, `is_evidence_for`) should be tuned once and re-extracted. Plan ~½ day after the first pass.
2. **Additive, not replacement.** The S3 vector index stays. Adding the graph as a second tool the supervisor can call is the cheaper, lower-risk path.
3. **Drift management.** Every KB refresh requires `graphify --update`. Wiring this into the existing `kb-regenerate` command is roughly a 1-day add.
4. **Hype-velocity vs. stability.** 22k stars in 10 days signals momentum, not maturity. We will pin a specific `graphifyy` version once we commit.
5. **Office-format coverage.** `.docx`/`.xlsx` are not first-class — pandoc loses Excel formula context and table structure. The 4 `.xlsx` files should be eyeballed after conversion.
6. **Where it runs.** Local laptop is fine for 257 files but ties up a developer's API key. EC2 devbox (already SSM-reachable) is preferable for scheduled refreshes.

---

## 9. Recommended next step

Run a **10-file pilot** spanning J&A, SOW template, PMR checklist, and a TechFAR guide. Execute three test queries: a completeness check, a threshold path, and a supersession lookup. Pilot will confirm:

- Graph quality is sufficient for OA-grade work.
- Real per-file timing and cost (replacing the estimate in §6 with a measurement).
- `.docx`/`.xlsx` conversion fidelity on representative samples.

Total pilot effort: **~30 minutes wall time, ~$1 in API cost.**

If the pilot passes, the full corpus pass plus supervisor-tool integration is roughly a **2–3 day** effort.

---

## 10. References

- Graphify GitHub repository — <https://github.com/safishamsi/graphify>
- Graphify project site — <https://graphify.net/>
- `graphifyy` on PyPI — <https://pypi.org/project/graphifyy/>
- Mustafa Genc, *"Graphify: Build a Knowledge Graph From Your Entire Codebase — Without Sending Your Code to Anyone"*, GoPenAI, April 2026 — <https://blog.gopenai.com/graphify-build-a-knowledge-graph-from-your-entire-codebase-without-sending-your-code-to-anyone-1b6924474b50>
- *"Knowledge Graphs for Codebases: A Complete Guide to Graphify"*, Emelia — <https://emelia.io/hub/knowledge-graph-graphify-guide>
- *"From Karpathy's LLM Wiki to Graphify: Building AI Memory Layers"*, Analytics Vidhya, April 2026 — <https://www.analyticsvidhya.com/blog/2026/04/graphify-guide/>
- In-repo: `.claude/skills/s3-knowledge-base-sync/SKILL.md` — canonical reference for the approved-KB S3 path
- In-repo: `infrastructure/cdk-eagle/lambda/metadata-extraction/handler.py` — current KB metadata pipeline
