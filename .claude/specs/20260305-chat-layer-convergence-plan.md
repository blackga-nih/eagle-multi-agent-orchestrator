# Chat Layer Convergence Plan: EAGLE + nci-oa-agent

> Bring the best capabilities from nci-oa-agent (Ada) into EAGLE while preserving EAGLE's multi-tenant architecture, Strands SDK orchestration, and production infrastructure.

## Problem Statement

EAGLE has strong architecture (multi-tenant DynamoDB, 11 server-side tools, supervisor-specialist routing, ECS Fargate) but lacks:
- Persistent model workspace/memory across turns
- Web search and document browsing
- RAG / vector-based knowledge retrieval
- Prompt caching for cost optimization
- Client-side code sandbox

nci-oa-agent has rich capabilities (3-layer memory, web search, browse + LLM extraction, S3 KB, prompt caching) but lacks:
- Multi-tenant isolation
- Server-side tool execution
- Proper agent orchestration framework
- Production-grade infrastructure

## Phases

### Phase 1: Workspace Memory Tool (Low effort, High impact)

**What**: Port the `editor` tool pattern from nci-oa-agent — give the model a persistent scratchpad.

**Why**: This is the single highest-impact improvement. The model can self-manage context across turns, track ongoing work, and maintain institutional knowledge per session.

**Implementation**:

1. Add `workspace_memory` tool to `server/app/agentic_service.py`:
   - Operations: `view`, `write`, `append`, `clear`
   - Storage: DynamoDB `WORKSPACE#{tenant}#{user}` / `FILE#{filename}`
   - Default files: `_workspace.txt`, `_notes.txt`
   - Scoped per tenant+user (not per session — persists across sessions)

2. Inject workspace content into supervisor system prompt:
   ```python
   # In build_supervisor_prompt()
   workspace = workspace_store.get_files(tenant_id, user_id)
   prompt += f"\n\n<workspace>\n{workspace}\n</workspace>"
   ```

3. Add tool definition:
   ```python
   {
       "name": "workspace_memory",
       "description": "View and edit your persistent workspace files. Use to track ongoing work, key findings, and important context.",
       "input_schema": {
           "type": "object",
           "properties": {
               "command": {"type": "string", "enum": ["view", "write", "append", "clear"]},
               "path": {"type": "string", "description": "File path (e.g., _workspace.txt)"},
               "content": {"type": "string", "description": "Content for write/append"}
           },
           "required": ["command", "path"]
       }
   }
   ```

**Files to modify**:
- `server/app/agentic_service.py` — add tool definition + handler
- `server/app/strands_agentic_service.py` — register tool, inject workspace into prompt
- `server/app/session_store.py` — add workspace CRUD functions (new PK pattern)

**Validation**: `python -m pytest tests/ -v -k workspace`

---

### Phase 2: Web Search Tool (Medium effort, High impact)

**What**: Add Brave Search + GovInfo API as a server-side tool, matching nci-oa-agent's `search` capability.

**Why**: EAGLE currently cannot look up current regulations, news, or policy updates. COs need current information.

**Implementation**:

1. Add `web_search` tool to EAGLE:
   ```python
   {
       "name": "web_search",
       "description": "Search the web for current regulations, policy updates, and federal acquisition information.",
       "input_schema": {
           "type": "object",
           "properties": {
               "query": {"type": "string"},
               "search_type": {"type": "string", "enum": ["web", "news", "gov"], "default": "web"}
           },
           "required": ["query"]
       }
   }
   ```

2. Create `server/app/search_service.py`:
   - Brave Search API integration (web + news)
   - GovInfo API integration (federal documents)
   - Rate limiting per tenant
   - Result formatting for model consumption

3. Environment variables:
   - `BRAVE_SEARCH_API_KEY`
   - `DATA_GOV_API_KEY`

**Files to create**:
- `server/app/search_service.py` — search API clients

**Files to modify**:
- `server/app/agentic_service.py` — add tool + handler
- `server/app/strands_agentic_service.py` — register tool

**Validation**: `python -m pytest tests/ -v -k search`

---

### Phase 3: Document Browse + LLM Extraction (Medium effort, High impact)

**What**: Port the `browse` tool pattern — fetch URLs, extract content, optionally use a cheap model (Haiku) for targeted Q&A.

**Why**: COs need to read acquisition.gov, FAR references, and vendor documentation.

**Implementation**:

1. Add `browse_url` tool:
   ```python
   {
       "name": "browse_url",
       "description": "Fetch and analyze web pages, PDFs, or documents from URLs.",
       "input_schema": {
           "type": "object",
           "properties": {
               "urls": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
               "question": {"type": "string", "description": "What to extract from the documents"}
           },
           "required": ["urls"]
       }
   }
   ```

2. Create `server/app/browse_service.py`:
   - HTTP fetch with timeout and size limits
   - HTML → text extraction (trafilatura or beautifulsoup4)
   - PDF → text extraction (pymupdf or pdfplumber)
   - Optional LLM extraction via Haiku for focused Q&A
   - Truncation at 100K chars per document

3. Add dependency: `trafilatura` or `beautifulsoup4` to `requirements.txt`

**Files to create**:
- `server/app/browse_service.py` — URL fetch + extraction

**Files to modify**:
- `server/app/agentic_service.py` — add tool + handler
- `server/requirements.txt` — add dependencies

**Validation**: `python -m pytest tests/ -v -k browse`

---

### Phase 4: S3 Knowledge Base Access (Low effort, Medium impact)

**What**: Connect EAGLE to the `rh-eagle` S3 bucket that nci-oa-agent already has populated with acquisition guidance.

**Why**: 308 documents organized by domain (compliance, legal, market, templates) — immediate knowledge improvement.

**Implementation**:

1. Add `knowledge_base` tool:
   ```python
   {
       "name": "knowledge_base",
       "description": "Search the acquisition knowledge base. Lists files by domain or fetches specific document content.",
       "input_schema": {
           "type": "object",
           "properties": {
               "action": {"type": "string", "enum": ["list", "search", "fetch"]},
               "domain": {"type": "string", "enum": [
                   "compliance-strategist", "financial-advisor", "legal-counselor",
                   "market-intelligence", "public-interest-guardian", "supervisor-core",
                   "technical-translator", "shared"
               ]},
               "key": {"type": "string", "description": "S3 key to fetch specific file"},
               "query": {"type": "string", "description": "Search term for filename matching"}
           },
           "required": ["action"]
       }
   }
   ```

2. Reuse existing `s3_document_ops` infrastructure but point to `rh-eagle` bucket
3. Add filename-based search (glob matching on S3 key prefixes)

**Files to modify**:
- `server/app/agentic_service.py` — add tool + handler
- Environment: Add `EAGLE_KB_BUCKET=rh-eagle`

**Validation**: `python -m pytest tests/ -v -k knowledge`

---

### Phase 5: Prompt Caching (Low effort, Medium impact)

**What**: Port the sqrt(2) scaling cache boundary strategy from nci-oa-agent's `inference.js`.

**Why**: Long conversations with acquisition context get expensive. nci-oa-agent sees ~90% cache hit rates on long threads.

**Implementation**:

1. Add cache point injection in `strands_agentic_service.py`:
   - Calculate token boundaries at 1024, 1448, 2048, 2896, 4096, ...
   - Insert `cachePoint: {type: "default"}` at last 2 boundaries
   - Add cache point to system prompt and tools

2. This works with Bedrock Converse API's native prompt caching — no infrastructure needed.

**Files to modify**:
- `server/app/strands_agentic_service.py` — add cache point logic before agent invocation

**Validation**: Monitor CloudWatch for `cacheReadInputTokens` in Bedrock responses

---

### Phase 6: Vector Search RAG (High effort, High impact)

**What**: Wire the S3 Vectors knowledge base that's already configured in nci-oa-agent but not connected.

**Why**: Semantic search over FAR/HHSAR/NIH policies dramatically improves answer quality vs. filename-based lookup.

**Implementation**:

1. Create `server/app/vector_search.py`:
   - Bedrock Titan Embed v2 for query embedding (1024 dimensions)
   - S3 Vectors `QueryVectors` API for similarity search
   - Top-k filtering with configurable threshold (default 0.7)
   - Result formatting with confidence scores

2. Integrate as tool or as automatic context injection:
   - **Option A (Tool)**: Model decides when to search — lower cost, model-driven
   - **Option B (Auto-inject)**: Every user message triggers KB search, top 3 results injected into system prompt — higher quality, higher cost
   - **Recommended**: Start with Option A, move to B based on eval results

3. Document ingestion pipeline:
   - Watch S3 `rh-eagle` bucket for new/updated files
   - Chunk documents (500 tokens, 50 overlap)
   - Embed with Titan v2
   - Store in S3 Vectors index `acquisition-docs`
   - Lambda trigger or scheduled job

**Files to create**:
- `server/app/vector_search.py` — embedding + search
- `server/app/document_ingest.py` — chunking + indexing pipeline
- `infrastructure/cdk-eagle/lib/eagle-vectors-stack.ts` — S3 Vectors bucket + IAM

**Dependencies**: `boto3` (already present), S3 Vectors preview access

**Validation**: `python -m pytest tests/ -v -k vector`

---

## Priority Order

| Phase | Effort | Impact | Dependencies | ETA |
|-------|--------|--------|--------------|-----|
| 1. Workspace Memory | Low | High | None | - |
| 2. Web Search | Medium | High | API keys | - |
| 4. S3 KB Access | Low | Medium | S3 bucket access | - |
| 5. Prompt Caching | Low | Medium | None | - |
| 3. Document Browse | Medium | High | Phase 2 | - |
| 6. Vector Search RAG | High | High | Phase 4 + S3 Vectors | - |

Phases 1, 4, and 5 can run in parallel. Phase 3 depends on 2 (shared HTTP infrastructure). Phase 6 depends on 4 (needs KB documents accessible first).

## Success Criteria

- [ ] Model can maintain workspace notes across sessions (Phase 1)
- [ ] Model can search current regulations and news (Phase 2)
- [ ] Model can fetch and analyze external URLs (Phase 3)
- [ ] Model can browse acquisition KB by domain (Phase 4)
- [ ] Long conversations show >50% cache hit rate (Phase 5)
- [ ] Semantic search returns relevant FAR sections for natural language queries (Phase 6)

## What We're NOT Porting

- **Client-side tool execution** — EAGLE's server-side approach is more secure
- **IndexedDB/localStorage** — DynamoDB is the right persistence layer for multi-tenant
- **SolidJS frontend** — EAGLE's Next.js frontend is more mature
- **Multiple personas (Ada/FedPulse)** — EAGLE's specialist routing is architecturally superior
- **Gemini provider** — Bedrock is the approved provider for NCI

## Validation Commands

```bash
# After each phase
ruff check app/                          # Lint
python -m pytest tests/ -v              # Unit tests
npx playwright test                      # E2E (if frontend changes)
```
