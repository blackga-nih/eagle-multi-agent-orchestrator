# Plan: Document Generator Refactor — Agent-as-Tool with Template Guidelines

**Date:** 2026-03-11
**Type:** plan
**Status:** approved
**Branch:** feat/document-agent-refactor

---

## Problem Statement

The current document generation system uses 10 hardcoded Python f-string generators (`_generate_sow`, `_generate_igce`, etc.) that produce skeletal 40-90 line documents with `[To be determined]` placeholders. The LLM decides *which* doc to generate but has zero involvement in *what goes in it*. Context extraction is brittle regex pulling fragments from recent messages. The tool accepts ~20 optional parameters that are rarely filled.

### Current Flow
```
User → Supervisor → create_document(doc_type, title, data={...20 fields...})
                         │
                         ▼
                    _augment_document_data_from_context()  ← regex extraction
                         │
                         ▼
                    _generate_sow(title, data)  ← pure f-string formatting
                         │
                         ▼
                    "[To be determined]" everywhere
```

### Problems
1. **No LLM in document content** — generators are pure string formatting
2. **Brittle context extraction** — regex pulls fragments, misses nuance
3. **Too many parameters** — agent rarely fills more than 2-3
4. **No omission reasoning** — missing sections get silent defaults
5. **Reasoning appendix underused** — captures tool calls, not document decisions
6. **Templates unused by LLM** — `{{PLACEHOLDER}}` templates never seen by the model

---

## Solution: Agent-as-Tool with Template Guidelines

### New Flow
```
User → Supervisor → generate_document(doc_type="sow")
                         │
                         ▼
                    document_agent.py
                    ┌─────────────────────────────────┐
                    │ 1. Load template markdown        │
                    │ 2. Load conversation context     │
                    │    (state + messages + intake)    │
                    │ 3. Build focused prompt           │
                    │ 4. Call model (single turn)       │
                    │ 5. Validate required fields       │
                    │ 6. Parse appendices               │
                    │ 7. Save to S3, update state       │
                    └─────────────────────────────────┘
                         │
                         ▼
                    Full prose document + appendices
```

### Why Agent-as-Tool (not inline tool, not full agent)

| Pattern | Pros | Cons | Verdict |
|---------|------|------|---------|
| Inline tool (current) | Simple | No LLM content, no isolation | No |
| Full separate agent | Full autonomy, own tools | Over-engineered for single-turn | No |
| **Agent-as-Tool** | Focused system prompt, isolated context, single-turn | Slightly more code than inline | **Yes** |

The document generation task needs:
- A **focused system prompt** (template specialist instructions) — different from supervisor
- **Context isolation** (200-line output shouldn't clog supervisor context)
- **Single-turn execution** — no multi-step reasoning, just write the document
- **No additional tools** — just needs context, not tool access

This matches Strands' Agent-as-Tool pattern: a lightweight subagent wrapped in a `@tool` function.

---

## Design

### 1. Simplified Tool Signature

```python
{
    "name": "generate_document",
    "description": "Generate an acquisition document using AI-driven content based on conversation context and NCI templates. Pass only the document type — context is loaded automatically.",
    "input_schema": {
        "type": "object",
        "properties": {
            "doc_type": {
                "type": "string",
                "enum": [
                    "sow", "igce", "acquisition_plan", "justification",
                    "market_research", "eval_criteria", "security_checklist",
                    "section_508", "cor_certification", "contract_type_justification"
                ],
                "description": "The type of acquisition document to generate"
            },
            "special_instructions": {
                "type": "string",
                "description": "Optional user-specific guidance for this generation (e.g., 'emphasize security requirements', 'use FFP contract type')"
            }
        },
        "required": ["doc_type"]
    }
}
```

### 2. Template-as-Guidelines Prompt

```
You are a Federal Acquisition document specialist for the National Cancer Institute (NCI).

## Your Task
Write a complete {doc_type_display} document based on the conversation context below.

## Template Reference
Use these sections as structural guidelines. You do NOT need to follow them rigidly —
adapt, expand, or reorganize sections based on the context. Write full prose, not placeholders.

<template>
{template_content}
</template>

## Conversation Context
<context>
{conversation_summary}
</context>

## Intake State
<state>
{state_snapshot}
</state>

{special_instructions_block}

## Output Rules

1. Write full prose for each section — no placeholders, no [TBD], no {{VARIABLE}} tokens
2. Infer reasonable defaults from NCI/NIH context when appropriate (e.g., Bethesda location, FAR applicability)
3. Required fields that MUST appear in the document: {required_fields}
4. After the main document, include TWO appendices:

### Appendix A: Omissions & Information Gaps
A markdown table with columns: Section | Status (Partial/Omitted/Default) | Reason | Information Needed
Include every section where you lacked specific information.

### Appendix B: AI Decision Rationale
For each significant decision (contract type, set-aside, authority cited, pricing methodology, etc.),
write 2-3 sentences explaining the reasoning and the FAR/HHSAR basis.

## Format
Output the document as clean markdown. Start with the document title. End with the EAGLE footer.
Do not include any preamble or explanation outside the document itself.
```

### 3. Required Fields Per Document Type

File: `eagle-plugin/data/templates/required_fields.yaml`

```yaml
sow:
  display_name: "Statement of Work"
  required_sections:
    - title
    - background_and_purpose
    - scope
    - period_of_performance
    - tasks  # at least one task
    - deliverables  # at least one deliverable
  recommended_sections:
    - applicable_standards
    - place_of_performance
    - security_requirements
    - qasp

igce:
  display_name: "Independent Government Cost Estimate"
  required_sections:
    - title
    - purpose
    - methodology
    - cost_breakdown  # at least one line item
    - total_estimated_cost
  recommended_sections:
    - assumptions
    - confidence_level
    - data_sources

acquisition_plan:
  display_name: "Acquisition Plan"
  required_sections:
    - title
    - statement_of_need
    - competition_strategy
    - contract_type
    - milestones
  recommended_sections:
    - cost_estimate
    - set_aside_decision
    - source_selection
    - budgeting_and_funding

justification:
  display_name: "Justification & Approval"
  required_sections:
    - title
    - authority_cited
    - contractor_name
    - description_of_action
    - rationale
    - market_research_summary
  recommended_sections:
    - price_determination
    - efforts_to_compete
    - actions_to_increase_competition
    - approval_chain

market_research:
  display_name: "Market Research Report"
  required_sections:
    - title
    - description_of_need
    - sources_consulted
    - potential_sources
    - recommendation
  recommended_sections:
    - small_business_analysis
    - commercial_availability
    - contract_vehicle_analysis
    - pricing_analysis

eval_criteria:
  display_name: "Evaluation Criteria"
  required_sections:
    - title
    - evaluation_factors
    - rating_scale
    - basis_for_award
  recommended_sections:
    - evaluation_process
    - subfactors

security_checklist:
  display_name: "Security Checklist"
  required_sections:
    - title
    - security_assessment
    - impact_level
    - far_clauses
  recommended_sections:
    - it_systems
    - issm_review

section_508:
  display_name: "Section 508 Compliance Statement"
  required_sections:
    - title
    - applicability
    - product_types
    - exception_determination
  recommended_sections:
    - vpat_status
    - contract_language

cor_certification:
  display_name: "COR Certification"
  required_sections:
    - title
    - nominee_information
    - fac_cor_level
    - delegated_duties
  recommended_sections:
    - limitations
    - signatures

contract_type_justification:
  display_name: "Contract Type Justification"
  required_sections:
    - title
    - findings
    - determination
    - risk_assessment
  recommended_sections:
    - approval
```

### 4. Document Agent Implementation

File: `server/app/document_agent.py`

**Key functions:**

```python
def generate_document(
    doc_type: str,
    session_id: str,
    tenant_id: str,
    user_id: str,
    special_instructions: str = "",
) -> DocumentResult:
    """Agent-as-Tool: generate a complete acquisition document.

    1. Load template markdown from eagle-plugin/data/templates/
    2. Load conversation context (recent messages + state snapshot)
    3. Build focused prompt with template as guidelines
    4. Call model (single turn, no tools)
    5. Validate required fields present in output
    6. Parse and structure appendices
    7. Return DocumentResult with content + metadata
    """

def _load_template(doc_type: str) -> str:
    """Load template markdown from eagle-plugin/data/templates/{doc_type}-template.md"""

def _load_required_fields(doc_type: str) -> dict:
    """Load required/recommended fields from required_fields.yaml"""

def _build_context(session_id: str, tenant_id: str, user_id: str) -> str:
    """Build conversation context from recent messages + state snapshot"""

def _build_prompt(
    doc_type: str,
    template: str,
    context: str,
    required_fields: list[str],
    special_instructions: str,
) -> str:
    """Build the document generation prompt"""

def _validate_required_fields(content: str, required_fields: list[str]) -> list[str]:
    """Check that required sections appear in the generated content. Returns missing fields."""

def _parse_appendices(content: str) -> tuple[str, str, str]:
    """Split document into (main_content, omissions_appendix, reasoning_appendix)"""
```

**Model call approach:**
- Uses `strands.Agent` with no tools (pure text generation)
- Or direct `BedrockModel` / `AnthropicModel` call via `model.converse()`
- System prompt = template specialist instructions
- User message = context + template + rules
- Max tokens = 8192 (documents can be long)
- Temperature = 0.3 (structured but not robotic)

### 5. Evolved Reasoning Store

Add to `reasoning_store.py`:

```python
@dataclass
class SectionEntry:
    """Section-level reasoning for document appendices."""
    section_name: str
    status: str          # "complete", "partial", "omitted", "default"
    reason: str          # Why this status
    info_needed: str     # What would complete this section

@dataclass
class JustificationEntry:
    """Key decision reasoning for Appendix B."""
    decision: str        # e.g., "Contract Type → FFP"
    reasoning: str       # 2-3 sentence explanation
    far_basis: str       # FAR/HHSAR citation
    confidence: str      # "high", "medium", "low"

class ReasoningLog:
    # ... existing code ...

    def add_section_entry(self, ...):
        """Add a section-level omission/gap entry."""

    def add_justification_entry(self, ...):
        """Add a key decision justification entry."""

    def to_omissions_appendix(self) -> str:
        """Generate Appendix A: Omissions & Information Gaps."""

    def to_justification_appendix(self) -> str:
        """Generate Appendix B: AI Decision Rationale."""
```

### 6. Service Integration

In `strands_agentic_service.py`, the `generate_document` Strands `@tool`:

```python
@tool
def generate_document(doc_type: str, special_instructions: str = "") -> dict:
    """Generate an acquisition document using AI-driven content."""
    from app.document_agent import generate_document as _gen
    from app.document_service import create_package_document_version

    result = _gen(
        doc_type=doc_type,
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        special_instructions=special_instructions,
    )

    if not result.success:
        return {"error": result.error}

    # Save via canonical document service
    if package_id:
        canonical = create_package_document_version(
            tenant_id=tenant_id,
            package_id=package_id,
            doc_type=doc_type,
            content=result.content,
            title=result.title,
            file_type="md",
            created_by_user_id=user_id,
            session_id=session_id,
            change_source="agent_tool",
        )
        # ... emit SSE metadata, update state ...

    return {
        "doc_type": doc_type,
        "title": result.title,
        "content": result.content,
        "word_count": result.word_count,
        "omissions": result.omissions,
        "justifications": result.justifications,
        "missing_required": result.missing_required,
    }
```

### 7. State Updates

After generation, update:
```python
STATE#documents.{doc_type} = {
    "version": N,
    "status": "draft",
    "s3_key": "eagle/{tenant}/packages/{pkg}/{type}/v{N}/...",
    "generated_at": "2026-03-11T...",
    "word_count": 1250,
    "missing_required": [],
    "omission_count": 2,
}
STATE#checklist.{doc_type} = True
STATE#progress_pct = recalculated
```

SSE emission:
```json
{
    "type": "metadata",
    "data": {
        "type": "document_ready",
        "package_id": "...",
        "doc_type": "sow",
        "version": 1,
        "checklist": {"sow": true, "igce": false},
        "progress_pct": 40
    }
}
```

---

## Migration Plan

### What Gets Deleted

| Code | Location | Lines |
|------|----------|-------|
| `_generate_sow` | agentic_service.py:1768-1859 | 91 |
| `_generate_igce` | agentic_service.py:1862-1936 | 74 |
| `_generate_market_research` | agentic_service.py:1939-1999 | 60 |
| `_generate_justification` | agentic_service.py:2002-2061 | 59 |
| `_generate_acquisition_plan` | agentic_service.py:2070-2167 | 97 |
| `_generate_eval_criteria` | agentic_service.py:2170-2232 | 62 |
| `_generate_security_checklist` | agentic_service.py:2235-2296 | 61 |
| `_generate_section_508` | agentic_service.py:2299-2367 | 68 |
| `_generate_cor_certification` | agentic_service.py:2370-2439 | 69 |
| `_generate_contract_type_justification` | agentic_service.py:2443-2514 | 71 |
| `_augment_document_data_from_context` | agentic_service.py:316-388 | 72 |
| `_extract_first_money_value` | agentic_service.py:253-266 | 13 |
| `_extract_period` | agentic_service.py:269-277 | 8 |
| `_extract_section_bullets` | agentic_service.py:280-313 | 33 |
| **Total** | | **~838 lines** |

### What Gets Created

| File | Purpose | Lines (est) |
|------|---------|-------------|
| `server/app/document_agent.py` | Agent-as-Tool implementation | ~250 |
| `eagle-plugin/data/templates/required_fields.yaml` | Required field schema | ~120 |
| Updates to `reasoning_store.py` | Section + justification entries | ~80 |
| Updates to `strands_agentic_service.py` | New tool wiring | ~40 |

### What Stays

| Code | Reason |
|------|--------|
| `_exec_create_document` (thin wrapper) | Backward compat during transition — delegates to document_agent |
| `TemplateService` (DOCX/XLSX) | Still needed for official template population |
| `document_service.py` | Storage layer unchanged |
| `document_store.py` | DynamoDB queries unchanged |
| `reasoning_store.py` (existing methods) | Extended, not replaced |
| Template markdown files | Now used as guidelines instead of fill-in forms |

### Transition Strategy

1. **Phase 1**: Build `document_agent.py` alongside existing code
2. **Phase 2**: Wire `generate_document` tool, keep `create_document` as fallback
3. **Phase 3**: Remove old generators once new tool is validated
4. Feature flag: `USE_DOCUMENT_AGENT=true` (env var) controls which path runs

---

## Validation

```bash
# L1 — Lint
ruff check server/app/document_agent.py server/app/reasoning_store.py

# L2 — Unit tests
python -m pytest server/tests/test_document_agent.py -v

# L3 — Integration (manual)
# Start server, send "Generate a SOW for cloud migration" in chat
# Verify: full prose output, no [TBD], appendices present

# L3.5 — Agentic validation
# Run agent-browser with UC doc generation scenarios
```

---

## Files Touched

| File | Action |
|------|--------|
| `server/app/document_agent.py` | **CREATE** |
| `eagle-plugin/data/templates/required_fields.yaml` | **CREATE** |
| `server/app/reasoning_store.py` | **MODIFY** — add section/justification entries |
| `server/app/strands_agentic_service.py` | **MODIFY** — wire generate_document tool |
| `server/app/agentic_service.py` | **MODIFY** — delete generators, thin wrapper |
| `server/tests/test_document_agent.py` | **CREATE** — unit tests |
