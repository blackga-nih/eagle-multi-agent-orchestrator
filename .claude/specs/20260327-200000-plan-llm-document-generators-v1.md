# Plan: Replace Dumb Markdown Generators with LLM-Backed Document Generation

**Date:** 2026-03-27
**Status:** Ready to implement
**Scope:** `server/app/tools/create_document_support.py` (10 generators) + `server/app/tools/document_generation.py` (caller)

---

## Problem Statement

The 10 `_generate_*` functions in `create_document_support.py` (lines 669-1432) are dumb f-string templates that string-interpolate raw conversation text into fixed markdown skeletons. When the Strands agent calls `create_document` without providing pre-composed `ai_content`, these generators produce garbage output:

- Raw user prompts pasted verbatim into Background/Scope sections
- Agent follow-up questions dumped into "Appendix A: Acquisition Context"
- Truncated/garbled regex-extracted text in Period of Performance
- Generic boilerplate placeholders (`[To be determined]`) for every substantive section

**Example failure:** A SOW for cloud hosting had "3-year base period plus 2 option years, starting October 2026. No existing vehicles -- new standalone contract." as both Background AND Scope, with the agent's "Perfect. This is a $750K FAR Part 15..." response pasted into Appendix A.

## Objectives

1. Replace all 10 `_generate_*` functions with a single `_llm_generate_document()` that calls Bedrock `converse()` synchronously
2. Each doc type gets a structured prompt that describes expected sections, NCI conventions, and FAR compliance requirements
3. Session context is provided as INPUT to the LLM (not string-interpolated into a skeleton)
4. Fallback to a minimal skeleton ONLY if Bedrock is completely unavailable (SSO expired, no credentials)
5. No change to the `exec_create_document` caller signature — drop-in replacement

---

## Technical Approach

### Architecture

```
exec_create_document()
  ├── ai_content provided? → use it directly (no change)
  ├── TemplateService succeeds? → use DOCX/XLSX (no change)
  └── Fallback path (THE FIX):
        OLD: _generate_sow(title, data) → f-string garbage
        NEW: _llm_generate_document("sow", title, data) → Bedrock converse() → real content
              └── Bedrock unavailable? → _minimal_skeleton(doc_type, title) → honest "[LLM unavailable]" stub
```

### Bedrock Client Pattern

Reuse the existing lazy-singleton pattern from `template_standardizer.py`:

```python
import boto3, json, os, logging
from botocore.config import Config

_DOC_GEN_MODEL = os.getenv("EAGLE_DOC_GEN_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
_AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_bedrock_doc_gen = None

def _get_doc_gen_bedrock():
    global _bedrock_doc_gen
    if _bedrock_doc_gen is None:
        _bedrock_doc_gen = boto3.client(
            "bedrock-runtime",
            region_name=_AWS_REGION,
            config=Config(read_timeout=120, retries={"max_attempts": 2}),
        )
    return _bedrock_doc_gen
```

**Model choice:** Haiku 4.5 by default — fast (~3-5s), cheap ($0.001/$0.005 per 1K tokens), sufficient quality for document generation. Override via `EAGLE_DOC_GEN_MODEL` env var. NOT Sonnet — that's overkill for structured document generation and would add 15-30s latency.

### Core LLM Function

```python
def _llm_generate_document(doc_type: str, title: str, data: dict) -> str:
    """Generate acquisition document content via Bedrock LLM call.

    Falls back to minimal skeleton if Bedrock is unavailable.
    """
    system_prompt = _DOC_TYPE_SYSTEM_PROMPTS.get(doc_type)
    if not system_prompt:
        return _minimal_skeleton(doc_type, title)

    # Build user message from session context
    user_message = _build_generation_prompt(doc_type, title, data)

    try:
        bedrock = _get_doc_gen_bedrock()
        response = bedrock.converse(
            modelId=_DOC_GEN_MODEL,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_message}]}],
            inferenceConfig={"maxTokens": 8192, "temperature": 0.3},
        )
        content = response["output"]["message"]["content"][0]["text"]
        return content.strip()
    except Exception as exc:
        logger.warning("Bedrock doc generation failed for %s: %s", doc_type, exc)
        return _minimal_skeleton(doc_type, title)
```

### System Prompts (per doc type)

Each doc type gets a system prompt that defines:
1. Document structure (required sections with numbering)
2. NCI-specific conventions (agency name, FAR references, HHSAR)
3. What content the LLM should compose vs. leave as placeholders
4. Quality requirements (no raw conversation text, no boilerplate filler)

Store in a dict `_DOC_TYPE_SYSTEM_PROMPTS` — not in external files, keep it co-located with the generation code for easy maintenance.

**Example for SOW:**

```python
_DOC_TYPE_SYSTEM_PROMPTS = {
    "sow": """You are an NCI federal acquisition document specialist. Generate a Statement of Work (SOW) in markdown format.

## Required Sections
1. BACKGROUND AND PURPOSE — Describe the agency need in 2-3 professional paragraphs
2. SCOPE — Define what the contractor shall provide, specific to the requirement
3. PERIOD OF PERFORMANCE — Base period + option years if applicable
4. APPLICABLE DOCUMENTS AND STANDARDS — FAR, HHSAR, and requirement-specific standards
5. TASKS AND REQUIREMENTS — Detailed task descriptions with measurable outcomes
6. DELIVERABLES — Specific deliverables with due dates/milestones
7. GOVERNMENT-FURNISHED PROPERTY — List items or state "None"
8. QUALITY ASSURANCE SURVEILLANCE PLAN — Performance standards and evaluation methods
9. PLACE OF PERFORMANCE — Specific location(s)
10. SECURITY REQUIREMENTS — Data sensitivity, clearance levels, compliance frameworks

## Rules
- Write professional federal acquisition language, not casual conversation
- Be specific to the requirement described in the context — do NOT use generic filler
- If information is missing for a section, write "[Contracting Officer to complete: <what's needed>]"
- Do NOT paste raw user messages or chat responses into the document
- Do NOT include appendices with conversation history
- Use markdown: H1 for doc type, H2 for sections, H3 for subsections, tables where appropriate
- Include "DRAFT — Generated {date}" in header metadata
- End with EAGLE footer""",
    # ... similar for other doc types
}
```

### User Message Builder

```python
def _build_generation_prompt(doc_type: str, title: str, data: dict) -> str:
    """Build a structured prompt from session context data."""
    parts = [f"Generate a {_DOC_TYPE_LABELS.get(doc_type, doc_type)} titled: {title}\n"]

    # Add structured context fields (not raw conversation)
    context_fields = {
        "description": "Requirement Description",
        "estimated_value": "Estimated Value",
        "period_of_performance": "Period of Performance",
        "security_requirements": "Security Requirements",
        "place_of_performance": "Place of Performance",
        "scope": "Scope Details",
        "deliverables": "Deliverables",
        "tasks": "Tasks",
        "competition": "Competition Strategy",
        "contract_type": "Contract Type",
        "set_aside": "Set-Aside",
    }

    for key, label in context_fields.items():
        value = data.get(key)
        if value:
            if isinstance(value, list):
                value = "\n".join(f"- {item}" for item in value)
            parts.append(f"**{label}:** {value}")

    # Add conversation history as context (NOT to be pasted in)
    conv_history = data.get("conversation_history", [])
    if conv_history:
        parts.append("\n## Conversation Context (for understanding only — do NOT paste into document)")
        for msg in conv_history[-8:]:
            role = msg.get("role", "user").upper()
            text = msg.get("text", "")[:500]
            parts.append(f"[{role}]: {text}")

    return "\n\n".join(parts)
```

### Minimal Skeleton Fallback

When Bedrock is unavailable, return an honest stub — NOT a fake-filled document:

```python
def _minimal_skeleton(doc_type: str, title: str) -> str:
    label = _DOC_TYPE_LABELS.get(doc_type, doc_type.replace("_", " ").title())
    return f"""# {label.upper()}
## {title}
### National Cancer Institute (NCI)

**Document Status:** DRAFT — Generated {time.strftime("%Y-%m-%d %H:%M UTC")}

---

> **Note:** This document could not be generated because the AI service is temporarily
> unavailable. Please try again, or use the chat to request document generation
> (e.g., "Generate a {label} for this acquisition").

---
*EAGLE — NCI Acquisition Assistant*
"""
```

---

## Implementation Steps

### Step 1: Add Bedrock client + core LLM function (~50 lines)

In `create_document_support.py`, add:
- `_get_doc_gen_bedrock()` — lazy singleton
- `_llm_generate_document(doc_type, title, data)` — core function
- `_build_generation_prompt(doc_type, title, data)` — prompt builder
- `_minimal_skeleton(doc_type, title)` — honest fallback

### Step 2: Write system prompts for all 10 doc types (~200 lines)

Add `_DOC_TYPE_SYSTEM_PROMPTS` dict with prompts for:
- `sow` — Statement of Work
- `igce` — Cost Estimate
- `market_research` — Market Research Report
- `justification` — J&A
- `acquisition_plan` — Acquisition Plan
- `eval_criteria` — Evaluation Criteria
- `security_checklist` — Security Checklist
- `section_508` — 508 Compliance
- `cor_certification` — COR Certification
- `contract_type_justification` — Contract Type D&F

### Step 3: Replace all 10 `_generate_*` functions (~-750 lines)

Replace each function body to delegate to `_llm_generate_document`:

```python
def _generate_sow(title: str, data: dict) -> str:
    return _llm_generate_document("sow", title, data)

def _generate_igce(title: str, data: dict) -> str:
    return _llm_generate_document("igce", title, data)

# ... etc for all 10
```

### Step 4: Remove dead code

- Delete `_extract_sow_sections_from_history()` — no longer needed
- Delete `_extract_section_bullets()` — only used by old generators
- Clean up unused imports

### Step 5: Update `_augment_document_data_from_context`

Simplify the context augmentation — it no longer needs to extract individual fields for string interpolation. Keep the session message loading but remove the field-specific extraction (money, period, scope override) that was designed for the f-string templates.

Actually — keep `_augment_document_data_from_context` as-is for now. The structured fields it extracts (description, estimated_value, period_of_performance) are still useful as prompt input to the LLM. The difference is they'll be provided as context, not interpolated.

---

## Testing Strategy

### Validation commands

```bash
# Level 1: Lint
cd server && ruff check app/tools/create_document_support.py app/tools/document_generation.py

# Level 2: Existing tests still pass
python -m pytest tests/test_document_pipeline.py tests/test_document_helpers.py tests/test_create_document_observability.py -v

# Level 3: Manual integration test
python -c "
from app.tools.document_generation import exec_create_document
result = exec_create_document(
    params={'doc_type': 'sow', 'title': 'Cloud Hosting Services for NCI', 'data': {'description': 'FedRAMP High cloud hosting for research data platform', 'period_of_performance': '3-year base + 2 option years', 'estimated_value': '\$750,000'}},
    tenant_id='dev-tenant',
    session_id=None
)
print(result.get('content', '')[:2000])
"
```

### What to verify
- [ ] Generated SOW has professional language, not raw prompt text
- [ ] Missing context produces `[Contracting Officer to complete: ...]` not `[TBD]`
- [ ] No conversation history pasted into document body
- [ ] Bedrock unavailable → honest "AI unavailable" stub, not fake-filled template
- [ ] Existing tests pass (the function signature is unchanged)
- [ ] IGCE with line items still produces proper cost tables

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bedrock latency adds 3-5s to document generation | Medium | Use Haiku 4.5 (fast), acceptable since doc gen is already async |
| SSO expired → all generations fail | High | `_minimal_skeleton` fallback returns honest stub |
| LLM hallucinates FAR citations | Medium | System prompt says "only cite FAR sections mentioned in context" |
| Existing tests mock `_generate_sow` directly | Low | Keep function signatures identical, tests still pass |
| IGCE line-item math needs to be exact | High | IGCE system prompt should include math instructions; verify in testing |

---

## Success Criteria

1. No document output contains raw user messages pasted verbatim
2. Every section has either professional content or an explicit "[Contracting Officer to complete]" marker
3. No "Appendix A: Acquisition Context" dumping conversation history
4. Bedrock failure produces an honest stub, not a fake document
5. All existing tests pass
6. Document generation adds < 10s latency (Haiku target: 3-5s)
