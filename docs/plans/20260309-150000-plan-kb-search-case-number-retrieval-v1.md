# Knowledge Base Search Fix - Implementation Plan

## Problem Statement

Users searching for specific documents by case number, citation, or identifier get generic results instead of the actual document.

**Example failure:**
- **User query**: "What did GAO hold in B-302358 regarding IDIQ minimum obligation requirements?"
- **Expected**: Return `GAO_B-302358_IDIQ_Min_Fund.txt` from `eagle-knowledge-base/approved/legal-counselor/appropriations-law/`
- **Actual**: System returns generic IDIQ legal principles from Claude's training data, not the specific GAO decision

**Root causes:**
1. `knowledge_search` tool only filters on topic, document_type, agent, authority_level, and keywords
2. The extraction prompt asks for "5-15 search terms" but doesn't explicitly request case numbers or identifiers
3. No way to search by document_id or filename

---

## Architecture Context

### Current Flow
```
User Query → Supervisor Agent → knowledge_search tool → DynamoDB Scan → keyword filtering → results
                                                                              ↓
                                        User asks for "B-302358" → keywords array doesn't contain "B-302358" → no match
```

### Storage Architecture
- **Documents**: S3 bucket `eagle-documents-{account}-{env}` under `eagle-knowledge-base/approved/` prefix
- **Metadata**: DynamoDB table `eagle-document-metadata-{env}` with ~135 documents indexed
- **Extraction**: Lambda triggered on S3 upload calls Claude via Bedrock to extract metadata

### Example Document Entry (from document-summaries.csv)
```
document_id: eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-302358_IDIQ_Min_Fund.txt
file_name: GAO_B-302358_IDIQ_Min_Fund.txt
title: GAO Decision B-302358: IDIQ Minimum Obligation Requirements and Recording Statute Compliance
document_type: guidance
primary_topic: funding
summary: GAO decision establishing that IDIQ contracts require agencies to obligate the guaranteed minimum amount at the time of contract award...
```

Note: The case number "B-302358" appears in document_id, file_name, and title, but likely NOT in the keywords array.

---

## Solution Overview

**Hybrid approach with 3 phases:**

| Phase | What | Why |
|-------|------|-----|
| 1. Query Parameter | Add `query` param to search document_id, title, keywords | Immediate fix - works without re-indexing |
| 2. Prompt Improvement | Update extraction prompt to capture case numbers | Long-term - better keywords for new/re-indexed docs |
| 3. Backfill | Re-extract all existing documents | Apply improved extraction to existing docs |

---

## Phase 1: Add Query Parameter to knowledge_search

### File: `/Users/hoquemi/Desktop/sm_eagle/server/app/tools/knowledge_tools.py`

### Change 1: Update tool schema (lines 50-97)

**Current KNOWLEDGE_SEARCH_TOOL definition (line 50):**
```python
KNOWLEDGE_SEARCH_TOOL = {
    "name": "knowledge_search",
    "description": (
        "Search the acquisition knowledge base for relevant documents, templates, and guidance. "
        "Returns summaries and metadata to help decide which documents to retrieve in full. "
        "Use this to find SOW templates, FAR guidance, policy documents, checklists, etc. "
        "Query by topic, document_type, agent, or keywords."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {...},
            "document_type": {...},
            "agent": {...},
            "authority_level": {...},
            "keywords": {...},
            "limit": {...},
        },
    },
}
```

**Add after line 90 (after "keywords" property, before "limit"):**
```python
            "query": {
                "type": "string",
                "description": (
                    "Free-text query to match against document_id, filename, title, and keywords. "
                    "Use for case numbers (e.g., 'B-302358'), GAO decisions, citations, or specific terms. "
                    "More flexible than keywords filter - does substring matching across multiple fields."
                ),
            },
```

**Update description (lines 52-56) to:**
```python
    "description": (
        "Search the acquisition knowledge base for relevant documents, templates, and guidance. "
        "Returns summaries and metadata to help decide which documents to retrieve in full. "
        "Use 'query' for specific case numbers, citations, or identifiers (e.g., 'B-302358'). "
        "Use topic/document_type/agent filters for broader discovery."
    ),
```

### Change 2: Add query filtering logic in exec_knowledge_search

**Current keyword filtering (lines 194-202):**
```python
    # Optional keyword filtering (if keywords provided)
    if keywords:
        keywords_lower = [k.lower() for k in keywords]
        filtered = []
        for item in items:
            item_keywords = [k.lower() for k in item.get("keywords", [])]
            if any(kw in item_keywords or any(kw in ik for ik in item_keywords) for kw in keywords_lower):
                filtered.append(item)
        items = filtered
```

**Add after line 202 (after keyword filtering block):**
```python
    # Free-text query filtering (search document_id, title, keywords)
    query = params.get("query")
    if query:
        query_lower = query.lower()
        filtered = []
        for item in items:
            # Build searchable text from multiple fields
            doc_id = item.get("document_id", "").lower()
            title = item.get("title", "").lower()
            summary = item.get("summary", "").lower()
            keywords_text = " ".join(item.get("keywords", [])).lower()

            # Combine all searchable fields
            searchable = f"{doc_id} {title} {summary} {keywords_text}"

            # Check if query appears anywhere in searchable text
            if query_lower in searchable:
                filtered.append(item)
        items = filtered
        logger.info("knowledge_search: query=%s filtered to %d results", query, len(items))
```

### Change 3: Update logging (line 151-154)

**Current:**
```python
    logger.info(
        "knowledge_search: tenant=%s topic=%s doc_type=%s agent=%s limit=%d",
        tenant_id, topic, document_type, agent, limit,
    )
```

**Replace with:**
```python
    logger.info(
        "knowledge_search: tenant=%s query=%s topic=%s doc_type=%s agent=%s limit=%d",
        tenant_id, params.get("query"), topic, document_type, agent, limit,
    )
```

---

## Phase 2: Improve Metadata Extraction Prompt

### File: `/Users/hoquemi/Desktop/sm_eagle/infrastructure/cdk-eagle/lambda/metadata-extraction/extractor.py`

### Change: Update keywords instruction (line 45)

**Current (line 45):**
```python
- keywords: 5-15 search terms (array of strings)
```

**Replace with:**
```python
- keywords: 10-20 search terms for discovery (array of strings). MUST include:
  - Case/decision numbers if present (e.g., "B-302358", "B-321640", "B-409528")
  - Statute citations (e.g., "31 USC 1341", "41 USC 3901")
  - FAR/DFARS references (e.g., "FAR 16.505", "DFARS 252.227")
  - Distinctive filename components (e.g., "IDIQ_Min_Fund", "ADA_Bonafide")
  - Acronyms and abbreviations (e.g., "IDIQ", "ADA", "TOAP", "COFC")
  - Key concepts and topics (e.g., "minimum obligation", "bona fide needs")
  - Agency names (e.g., "GAO", "SBA", "Customs")
  IMPORTANT: Users often search by exact identifiers like "B-302358" - include these verbatim.
```

---

## Phase 3: Backfill Existing Documents

### File: `/Users/hoquemi/Desktop/sm_eagle/scripts/backfill-metadata.py`

This script already exists and triggers the metadata extraction Lambda for each document.

### Execution Steps

```bash
# 1. Deploy Phase 2 changes to Lambda first
cd infrastructure/cdk-eagle
npm run build && npx cdk deploy EagleEvalStack --require-approval never

# 2. Verify Lambda has new prompt
aws lambda get-function --function-name eagle-metadata-extraction-dev --query 'Configuration.LastModified'

# 3. Dry run backfill
cd ../../server
python scripts/backfill-metadata.py --dry-run

# 4. Execute backfill (re-extracts all ~135 documents)
python scripts/backfill-metadata.py

# 5. Verify a specific document was updated
aws dynamodb get-item \
  --table-name eagle-document-metadata-dev \
  --key '{"document_id": {"S": "eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-302358_IDIQ_Min_Fund.txt"}}' \
  --projection-expression "keywords"
# Should now include "B-302358" in the keywords array
```

---

## Phase 4: Add Unit Tests

### File: `/Users/hoquemi/Desktop/sm_eagle/server/tests/test_knowledge_tools.py`

### Add these tests after line 119:

```python
def test_exec_knowledge_search_query_matches_document_id(monkeypatch):
    """Query parameter should find documents by case number in document_id."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(
                doc_id="eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-302358_IDIQ_Min_Fund.txt",
                title="GAO Decision B-302358: IDIQ Minimum Obligation Requirements",
                topic="funding",
                keywords=["IDIQ", "obligation", "GAO"],
            ),
            _ddb_item(
                doc_id="eagle-knowledge-base/approved/legal-counselor/appropriations-law/GAO_B-321640_ADA_Bonafide.txt",
                title="GAO Decision B-321640: ADA Bona Fide Needs",
                topic="funding",
                keywords=["ADA", "bona fide", "GAO"],
            ),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "_get_dynamodb", lambda: ddb)

    result = kt.exec_knowledge_search(
        {"query": "B-302358"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert "B-302358" in result["results"][0]["document_id"]


def test_exec_knowledge_search_query_matches_title(monkeypatch):
    """Query parameter should find documents by text in title."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="doc1", title="IDIQ Minimum Obligation Requirements"),
            _ddb_item(doc_id="doc2", title="Contract Closeout Procedures"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "_get_dynamodb", lambda: ddb)

    result = kt.exec_knowledge_search(
        {"query": "IDIQ Minimum"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1
    assert result["results"][0]["document_id"] == "doc1"


def test_exec_knowledge_search_query_case_insensitive(monkeypatch):
    """Query matching should be case-insensitive."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="GAO_B-302358.txt", title="GAO Decision"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "_get_dynamodb", lambda: ddb)

    # Lowercase query should match uppercase document_id
    result = kt.exec_knowledge_search(
        {"query": "b-302358"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 1


def test_exec_knowledge_search_query_combined_with_topic_filter(monkeypatch):
    """Query and topic filters should work together (AND logic)."""
    table = MagicMock()
    # DynamoDB returns both items (scan doesn't filter by query)
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="GAO_B-302358.txt", title="GAO Decision", topic="funding"),
            _ddb_item(doc_id="GAO_B-302358_Copy.txt", title="GAO Decision Copy", topic="compliance"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "_get_dynamodb", lambda: ddb)

    # Search with both query and topic
    result = kt.exec_knowledge_search(
        {"query": "B-302358", "topic": "funding"},
        tenant_id="dev-tenant",
    )

    # Only funding topic should be returned (DynamoDB filters topic, then query filters in Python)
    # Note: In real implementation, DynamoDB filters by topic first
    assert all(r["primary_topic"] == "funding" for r in result["results"])


def test_exec_knowledge_search_query_no_match_returns_empty(monkeypatch):
    """Query with no matches should return empty results."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            _ddb_item(doc_id="unrelated.txt", title="Unrelated Document"),
        ]
    }
    ddb = MagicMock()
    ddb.Table.return_value = table
    monkeypatch.setattr(kt, "_get_dynamodb", lambda: ddb)

    result = kt.exec_knowledge_search(
        {"query": "B-999999"},
        tenant_id="dev-tenant",
    )

    assert result["count"] == 0
    assert result["results"] == []
```

---

## Validation Commands

### After Phase 1 (query parameter)

```bash
# Start local server
cd /Users/hoquemi/Desktop/sm_eagle/server
uvicorn app.main:app --reload --port 8000

# Test query parameter via API
curl -X POST http://127.0.0.1:8000/api/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool": "knowledge_search", "params": {"query": "B-302358"}}'

# Expected: result with document_id containing "GAO_B-302358"
```

### After Phase 4 (unit tests)

```bash
cd /Users/hoquemi/Desktop/sm_eagle/server
python -m pytest tests/test_knowledge_tools.py -v

# All tests should pass including new query parameter tests
```

### End-to-end validation

```bash
# Chat test - ask about B-302358
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "What did GAO hold in B-302358 regarding IDIQ minimum obligation requirements?"}],
    "tenant_id": "dev-tenant"
  }'

# Should return response citing GAO_B-302358_IDIQ_Min_Fund.txt
```

---

## Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `server/app/tools/knowledge_tools.py` | 50-97, 151-154, 194-202 | Add query param to schema, logging, filtering |
| `infrastructure/cdk-eagle/lambda/metadata-extraction/extractor.py` | 45 | Improve keywords extraction prompt |
| `server/tests/test_knowledge_tools.py` | append | Add 5 new test functions |

---

## Rollback Plan

If issues arise:
1. **Phase 1**: Remove query parameter from tool schema and filtering logic
2. **Phase 2**: Revert extraction prompt changes in Lambda
3. **Phase 3**: No rollback needed - existing metadata still works, just with old keywords

---

## Success Criteria

1. `knowledge_search({"query": "B-302358"})` returns `GAO_B-302358_IDIQ_Min_Fund.txt`
2. `knowledge_search({"query": "GAO B-302358"})` returns same document
3. `knowledge_search({"query": "b-302358"})` returns same document (case-insensitive)
4. All existing tests pass
5. New query parameter tests pass
6. After backfill: document keywords include case numbers like "B-302358"
