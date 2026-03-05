# Plan: Metadata Schema Migration & Knowledge Base Integration

**ID**: 20260304-132745-plan-metadata-schema-migration-v1
**Created**: 2026-03-04
**Updated**: 2026-03-04
**Status**: Draft (Ready for Review)
**Owner**: TBD

---

## Executive Summary

Migrate the 195 knowledge base documents from `rh-eagle-files` S3 bucket to `eagle-documents-*` and update the metadata extraction Lambda to capture the full schema defined in `metadata-schema.md`. This enables intelligent document discovery and agent routing without vector embeddings.

---

## Current State

| Component | Status | Location |
|-----------|--------|----------|
| Knowledge base documents | 195 files | `s3://rh-eagle-files/` |
| Document bucket (CDK) | Empty | `s3://eagle-documents-695681773636-dev/` |
| Metadata table | Empty (0 items) | `eagle-document-metadata-dev` (DynamoDB) |
| Lambda extractor | Partial schema | `infrastructure/cdk-eagle/lambda/metadata-extraction/` |
| Full schema spec | Documented | `/Users/hoquemi/Downloads/metadata-schema.md` |
| Bedrock model | ✅ Updated | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

### Schema Gap Analysis

The Lambda currently extracts 9 fields. The full schema defines 28+ fields.

**Missing fields (15+)**:
- `effective_date`, `expiration_date`, `fiscal_year` (temporal)
- `key_requirements`, `section_summaries` (content)
- `related_topics`, `relevant_agents` (routing)
- `statute_references`, `agency_references`, `authority_level` (regulatory)
- `complexity_level`, `audience` (discovery)
- `word_count`, `page_count`, `file_size_kb` (file metadata)
- `catalog_version`, `added_to_catalog`, `last_validated` (catalog)

---

## Target State

1. **Lambda extracts full schema** — all 28 fields from `metadata-schema.md`
2. **DynamoDB populated** — 195+ documents with complete metadata
3. **Agents can retrieve** — `knowledge_search` and `knowledge_fetch` tools enable document discovery
4. **Catalog synced** — `metadata-catalog.json` in S3 for bulk reads

---

## Implementation Plan

### Phase 1: Update Lambda Schema

#### Task 1.1: Update `models.py`

Add missing fields to `DocumentMetadata` dataclass:

```python
# New fields to add
effective_date: str = ""           # ISO 8601
expiration_date: str = ""          # ISO 8601 or null
fiscal_year: int = 0               # YYYY
key_requirements: List[str] = field(default_factory=list)
section_summaries: dict = field(default_factory=dict)
related_topics: List[str] = field(default_factory=list)
relevant_agents: List[str] = field(default_factory=list)
statute_references: List[str] = field(default_factory=list)
agency_references: List[str] = field(default_factory=list)
authority_level: str = "guidance"  # statute|regulation|policy|guidance|internal
complexity_level: str = "intermediate"  # basic|intermediate|advanced
audience: List[str] = field(default_factory=list)
word_count: int = 0
page_count: int = 0
file_size_kb: int = 0
source_agency: str = ""
catalog_version: str = "1.0"
added_to_catalog: str = field(default_factory=_now_iso)
last_validated: str = field(default_factory=_now_iso)
```

**File**: `infrastructure/cdk-eagle/lambda/metadata-extraction/models.py`

#### Task 1.2: Update `extractor.py` Prompt

Modify the Bedrock prompt to extract all fields:

```python
EXTRACTION_PROMPT = """You are a federal acquisition document analyst. Extract metadata from this document.

## Document
Filename: {filename}
Content:
{content}

## Required Output (JSON)
Return a JSON object with these fields:
- title: Document title
- summary: 2-3 sentence summary (max 500 chars)
- document_type: regulation|guidance|policy|template|memo|checklist|reference
- source_agency: FAR|GSA|OMB|DOD|GAO|HHS|NIH|Agency-specific
- primary_topic: funding|acquisition_packages|contract_types|compliance|legal|market_research|socioeconomic|labor|intellectual_property|termination|modifications|closeout|performance|subcontracting
- related_topics: array of secondary topics
- primary_agent: supervisor-core|financial-advisor|legal-counselor|compliance-strategist|market-intelligence|technical-translator|public-interest-guardian
- relevant_agents: array of other agents that should reference this
- key_requirements: array of 3-5 main requirements (short bullets)
- far_references: array of FAR citations (e.g., "FAR 16.505")
- statute_references: array of USC citations (e.g., "31 USC 1341")
- agency_references: array of agency regs (e.g., "DFARS 232.7")
- authority_level: statute|regulation|policy|guidance|internal
- keywords: array of 5-15 search terms
- complexity_level: basic|intermediate|advanced
- audience: array of roles (contracting_officer|legal_counsel|program_manager|financial_advisor|supervisor)
- effective_date: ISO date or empty string
- expiration_date: ISO date or empty string
- fiscal_year: number or 0
- confidence_score: 0.0-1.0 confidence in extraction accuracy

Return ONLY valid JSON, no markdown fences."""
```

**File**: `infrastructure/cdk-eagle/lambda/metadata-extraction/extractor.py`

#### Task 1.3: Update `handler.py`

Add computed fields (word_count, page_count, file_size_kb):

```python
# After text extraction
word_count = len(text.split()) if text else 0
page_count = text.count('\f') + 1 if text else 0  # form feed = page break
file_size_kb = round(size / 1024)

# Pass to metadata constructor
metadata = DocumentMetadata(
    # ... existing fields ...
    word_count=word_count,
    page_count=page_count,
    file_size_kb=file_size_kb,
    # ... new extracted fields ...
)
```

**File**: `infrastructure/cdk-eagle/lambda/metadata-extraction/handler.py`

> **Note**: DynamoDB GSIs skipped — unnecessary for ~195 documents. Use `Scan` with `FilterExpression` instead. Add GSIs later if query performance becomes an issue at scale.

---

### Phase 2: Create Migration Scripts

#### Task 2.1: Write Migration Script

Create a script to copy documents from `rh-eagle-files` to `eagle-documents-*`:

```python
#!/usr/bin/env python3
"""Migrate knowledge base from rh-eagle-files to eagle-documents bucket."""

import boto3
import time

SOURCE_BUCKET = "rh-eagle-files"
DEST_BUCKET = "eagle-documents-695681773636-dev"
DEST_PREFIX = "eagle-knowledge-base/approved/"

s3 = boto3.client("s3")

def migrate_documents():
    """Copy all documents, preserving folder structure."""
    paginator = s3.get_paginator("list_objects_v2")

    copied = 0
    for page in paginator.paginate(Bucket=SOURCE_BUCKET):
        for obj in page.get("Contents", []):
            source_key = obj["Key"]
            dest_key = f"{DEST_PREFIX}{source_key}"

            print(f"Copying: {source_key} -> {dest_key}")
            s3.copy_object(
                CopySource={"Bucket": SOURCE_BUCKET, "Key": source_key},
                Bucket=DEST_BUCKET,
                Key=dest_key,
            )
            copied += 1

            # Rate limit to avoid Lambda throttling
            if copied % 10 == 0:
                time.sleep(1)

    print(f"Migrated {copied} documents")

if __name__ == "__main__":
    migrate_documents()
```

**File**: `scripts/migrate-knowledge-base.py`

#### Task 2.2: Write Backfill Script

For documents already in S3 (pre-Lambda), create a backfill trigger:

```python
#!/usr/bin/env python3
"""Trigger metadata extraction for existing documents."""

import boto3
import json

BUCKET = "eagle-documents-695681773636-dev"
PREFIX = "eagle-knowledge-base/approved/"
LAMBDA_NAME = "eagle-metadata-extractor-dev"

s3 = boto3.client("s3")
lambda_client = boto3.client("lambda")

def trigger_extraction():
    """Invoke Lambda for each document to extract metadata."""
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            size = obj["Size"]

            # Simulate S3 event
            event = {
                "Records": [{
                    "s3": {
                        "bucket": {"name": BUCKET},
                        "object": {"key": key, "size": size}
                    }
                }]
            }

            print(f"Processing: {key}")
            lambda_client.invoke(
                FunctionName=LAMBDA_NAME,
                InvocationType="Event",  # async
                Payload=json.dumps(event),
            )

if __name__ == "__main__":
    trigger_extraction()
```

**File**: `scripts/backfill-metadata.py`

---

### Phase 3: Add Agent Tools

#### Task 3.1: Create `knowledge_search` Tool

Add a tool for agents to search the metadata table:

```python
def _exec_knowledge_search(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Search knowledge base metadata in DynamoDB."""
    table = _get_dynamodb().Table(os.environ.get("METADATA_TABLE", "eagle-document-metadata-dev"))

    # Query parameters
    topic = params.get("topic")
    agent = params.get("agent")
    document_type = params.get("document_type")
    keywords = params.get("keywords", [])
    limit = params.get("limit", 10)

    # Build filter expression
    filter_parts = []
    expr_values = {}

    if topic:
        filter_parts.append("primary_topic = :topic")
        expr_values[":topic"] = topic
    if agent:
        filter_parts.append("primary_agent = :agent")
        expr_values[":agent"] = agent
    if document_type:
        filter_parts.append("document_type = :doc_type")
        expr_values[":doc_type"] = document_type

    # Scan with filters (efficient for ~200 docs)
    scan_kwargs = {"Limit": limit}
    if filter_parts:
        scan_kwargs["FilterExpression"] = " AND ".join(filter_parts)
        scan_kwargs["ExpressionAttributeValues"] = expr_values

    response = table.scan(**scan_kwargs)

    # Return summaries for agent to evaluate
    results = []
    for item in response.get("Items", []):
        results.append({
            "document_id": item["document_id"],
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "document_type": item.get("document_type", ""),
            "primary_topic": item.get("primary_topic", ""),
            "key_requirements": item.get("key_requirements", []),
            "s3_key": item.get("s3_key", ""),
        })

    return {"results": results, "count": len(results)}
```

**Tool Definition**:

```python
{
    "name": "knowledge_search",
    "description": (
        "Search the acquisition knowledge base for relevant documents, templates, and guidance. "
        "Returns summaries and metadata to help decide which documents to retrieve in full. "
        "Use this to find SOW templates, FAR guidance, policy documents, etc."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Primary topic: funding, compliance, market_research, contract_types, etc.",
            },
            "agent": {
                "type": "string",
                "description": "Filter by primary agent: legal-counselor, financial-advisor, etc.",
            },
            "document_type": {
                "type": "string",
                "enum": ["regulation", "guidance", "policy", "template", "memo", "checklist", "reference"],
                "description": "Type of document to search for",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search keywords",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (default 10)",
            },
        },
    },
}
```

**File**: `server/app/tools/knowledge_tools.py` (new file)

#### Task 3.2: Create `knowledge_fetch` Tool

Add a tool to fetch full document content:

```python
def _exec_knowledge_fetch(params: dict, tenant_id: str, session_id: str = None) -> dict:
    """Fetch full document content from S3 given a document_id or s3_key."""
    s3 = boto3.client("s3")
    bucket = os.environ.get("DOCUMENT_BUCKET", "eagle-documents-695681773636-dev")
    key = params.get("s3_key") or params.get("document_id")

    if not key:
        return {"error": "s3_key or document_id required"}

    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read().decode("utf-8", errors="replace")
        return {
            "document_id": key,
            "content": content[:50000],  # Limit to 50KB
            "truncated": len(content) > 50000,
            "content_length": len(content),
        }
    except s3.exceptions.NoSuchKey:
        return {"error": f"Document not found: {key}"}
    except Exception as e:
        return {"error": str(e)}
```

**Tool Definition**:

```python
{
    "name": "knowledge_fetch",
    "description": (
        "Fetch full document content from the knowledge base. "
        "Use after knowledge_search to retrieve a specific document, template, or guidance. "
        "Pass the s3_key from search results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "s3_key": {
                "type": "string",
                "description": "S3 key from knowledge_search results",
            },
        },
        "required": ["s3_key"],
    },
}
```

**File**: `server/app/tools/knowledge_tools.py`

#### Task 3.3: Register Tools

Add tools to the agent's tool registry:

```python
# In server/app/strands_agentic_service.py or tool registration
from app.tools.knowledge_tools import _exec_knowledge_search, _exec_knowledge_fetch

TOOL_REGISTRY = {
    # ... existing tools ...
    "knowledge_search": _exec_knowledge_search,
    "knowledge_fetch": _exec_knowledge_fetch,
}
```

---

### Phase 4: Deploy & Validate

#### Task 4.1: Deploy Lambda Changes

```bash
cd infrastructure/cdk-eagle
npm run build
npx cdk deploy EagleStorageStack-dev --require-approval never
```

#### Task 4.2: Run Migration

```bash
# Copy documents
python scripts/migrate-knowledge-base.py

# Trigger metadata extraction
python scripts/backfill-metadata.py
```

#### Task 4.3: Validate DynamoDB Population

```bash
# Check item count
aws dynamodb scan --table-name eagle-document-metadata-dev --select COUNT

# Sample items (verify new fields present)
aws dynamodb scan --table-name eagle-document-metadata-dev --limit 3
```

#### Task 4.4: Test Agent Tools

```python
# Test knowledge_search
from app.tools.knowledge_tools import _exec_knowledge_search, _exec_knowledge_fetch

result = _exec_knowledge_search({"document_type": "template", "limit": 5}, "test-tenant")
print(result)

# Test knowledge_fetch (use s3_key from search results)
if result["results"]:
    doc = _exec_knowledge_fetch({"s3_key": result["results"][0]["s3_key"]}, "test-tenant")
    print(doc["content"][:500])
```

---

## Validation Commands

```bash
# Phase 1: Lambda schema
cd infrastructure/cdk-eagle/lambda/metadata-extraction
python -c "from models import DocumentMetadata; print(DocumentMetadata.__dataclass_fields__.keys())"

# Phase 2: Migration
aws s3 ls s3://eagle-documents-695681773636-dev/eagle-knowledge-base/approved/ --recursive | wc -l
# Expected: 195

# Phase 3: DynamoDB
aws dynamodb scan --table-name eagle-document-metadata-dev --select COUNT
# Expected: {"Count": 195, ...}
```

---

## Rollback Plan

1. **Lambda rollback**: Redeploy previous version via CDK
2. **DynamoDB**: Delete items with scan + batch delete (data is regenerable)
3. **S3**: Keep `rh-eagle-files` as source of truth until migration confirmed

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Documents in `eagle-documents-*` | 195 |
| Metadata items in DynamoDB | 195 |
| Fields per item | 28+ |
| New fields populated | authority_level, complexity_level, key_requirements, etc. |
| `knowledge_search` returns results | Yes |
| `knowledge_fetch` retrieves document content | Yes |
| Agent can find SOW template via tools | Yes |

---

## Timeline

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Lambda schema | 2-3 hours | None |
| Phase 2: Migration scripts | 1 hour | Phase 1 |
| Phase 3: Agent tools | 2 hours | None (can parallelize with Phase 1-2) |
| Phase 4: Deploy & validate | 1 hour | Phases 1-3 |
| **Total** | **~1 day** | |

---

## Files to Modify

| File | Changes |
|------|---------|
| `infrastructure/cdk-eagle/lambda/metadata-extraction/models.py` | Add 15 new fields |
| `infrastructure/cdk-eagle/lambda/metadata-extraction/extractor.py` | Update Bedrock prompt |
| `infrastructure/cdk-eagle/lambda/metadata-extraction/handler.py` | Compute word_count, page_count, pass new fields |
| `infrastructure/cdk-eagle/config/environments.ts` | ✅ Already updated — Claude 4.5 Haiku |
| `server/app/tools/knowledge_tools.py` | New file — `knowledge_search`, `knowledge_fetch` |
| `server/app/strands_agentic_service.py` | Register new tools |
| `scripts/migrate-knowledge-base.py` | New file |
| `scripts/backfill-metadata.py` | New file |

---

## Decisions Made

| Question | Decision |
|----------|----------|
| Bedrock model | ✅ Claude 4.5 Haiku (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) — cost-effective for structured extraction |
| DynamoDB GSIs | ⏸️ Skipped — unnecessary at 195 docs, use Scan + FilterExpression |
| Agent tools | ✅ Included — `knowledge_search` + `knowledge_fetch` for agent document retrieval |

## Open Questions

1. **Authority on schema**: Is `metadata-schema.md` the canonical schema, or should we extend it?
2. **HITL review**: Should migrated docs go through `pending/` or direct to `approved/`?
3. **Cleanup**: Delete `rh-eagle-files` after migration, or keep as backup?

---

## References

- Schema spec: `/Users/hoquemi/Downloads/metadata-schema.md`
- Lambda code: `infrastructure/cdk-eagle/lambda/metadata-extraction/`
- Storage stack: `infrastructure/cdk-eagle/lib/storage-stack.ts`
- CDK config: `infrastructure/cdk-eagle/config/environments.ts`

---

## Conversation Summary (2026-03-04)

### What the Lambda Does

The metadata extraction Lambda (`eagle-metadata-extractor-dev`) performs:
1. **Triggers** on S3 uploads to `eagle-documents-*` bucket
2. **Reads** document content from S3
3. **Calls Bedrock LLM** (Claude) with a structured prompt to extract metadata
4. **Computes** file-level metrics (word_count, page_count, file_size_kb)
5. **Writes** extracted metadata to DynamoDB (`eagle-document-metadata-dev`)

### Model Configuration

| Context | Env Var | Model |
|---------|---------|-------|
| Backend (FastAPI/Strands) | `ANTHROPIC_MODEL` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Lambda (metadata extraction) | `BEDROCK_MODEL_ID` | Updated to `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

**Decision**: Use Claude 4.5 Haiku for metadata extraction — cost-effective for structured JSON extraction from documents.

### Why Haiku over Sonnet?

| Factor | Haiku | Sonnet |
|--------|-------|--------|
| Cost | ~$0.25/1M input | ~$3/1M input (12x more) |
| Speed | Faster | Slower |
| Structured extraction | Excellent | Overkill |
| 195 docs batch | ~$0.50 | ~$6+ |

Sonnet's strengths (nuance, reasoning, creativity) aren't needed for extracting titles, FAR references, and keywords from well-structured government docs.

### Why Skip DynamoDB GSIs?

For ~195 documents, a `Scan` with `FilterExpression` is fast and cheap. GSIs make sense when:
- Table has 100K+ items
- You need efficient queries on non-key attributes at scale

**Decision**: Skip GSIs now. Add later only if query performance becomes an issue.

### Why We Need Agent Tools

**Current state when user asks "I need an SOW":**

| Step | What Happens | Source |
|------|--------------|--------|
| 1 | Agent recognizes document intent | Skill triggers |
| 2 | Uses **hardcoded template** | Embedded in skill markdown |
| 3 | Generates document | `create_document` tool |
| 4 | Saves to user's S3 folder | `s3_document_ops` tool |

**The Gap:**
- No `knowledge_search` → Agent can't discover templates/guidance in knowledge base
- No `knowledge_fetch` → Agent can't retrieve documents from S3 knowledge base
- Templates are **static** in skill markdown — same template every time

**After this plan:**
- Agent can **dynamically search** metadata table by topic, document_type, agent
- Agent can **fetch** templates/guidance from S3 knowledge base
- Enables intelligent document discovery without vector embeddings

### Deployment Note

Changes to CDK config (`environments.ts`) only take effect after deployment. The Lambda reads `BEDROCK_MODEL_ID` from environment variables baked in at deploy time. Since this plan includes Lambda code changes, we'll deploy everything once at the end — no need for multiple deploys.

### Key Files

| File | Purpose |
|------|---------|
| `infrastructure/cdk-eagle/lambda/metadata-extraction/extractor.py` | Bedrock prompt + extraction logic |
| `infrastructure/cdk-eagle/lambda/metadata-extraction/models.py` | `DocumentMetadata` dataclass |
| `infrastructure/cdk-eagle/lambda/metadata-extraction/handler.py` | Lambda entry point |
| `infrastructure/cdk-eagle/config/environments.ts` | `bedrockMetadataModelId` config |
| `server/app/agentic_service.py` | Current tools: `TOOL_DISPATCH`, `EAGLE_TOOLS` |
| `server/app/template_store.py` | Template resolution chain (user → tenant → global → plugin) |
| `eagle-plugin/skills/document-generator/SKILL.md` | Hardcoded SOW/IGCE/AP templates |
| `eagle-plugin/skills/knowledge-retrieval/SKILL.md` | Aspirational knowledge search (not implemented) |

### Storage Architecture

| Data | Location |
|------|----------|
| Documents (PDFs, templates) | S3: `eagle-documents-*-dev` |
| Document metadata (summaries, topics) | DynamoDB: `eagle-document-metadata-dev` |
| User templates (overrides) | DynamoDB: `eagle` table, `TEMPLATE#` entities |
| User documents (generated) | S3: `eagle/{tenant}/{user}/` |
