# Plan: Unified User State Schema + Recheck Tool Chain

**Date**: 2026-03-11
**Type**: plan
**Status**: draft
**Branch**: `feat/unified-state-schema`
**Depends on**: Alvee's `dev/strands-conversion-alvee` merge (document generation tools)

---

## 1. Problem Statement

EAGLE currently has **fragmented state** across 9+ DynamoDB entities, localStorage, IndexedDB, and `/tmp/` files. No single object represents "where is this user in their acquisition journey." The agent has no memory between turns beyond raw chat history — it can't see checklist progress, compliance status, vehicle selection rationale, or what documents exist without re-querying everything.

Additionally, when the knowledge base or compliance matrix changes, there is no mechanism to detect that existing packages are stale or to re-analyze and remediate affected documents.

### What this plan unifies

| Current location | Problem | Unified into |
|-----------------|---------|--------------|
| `PACKAGE#` in DynamoDB | Agent can't read it mid-turn without explicit query | `STATE#current` — loaded at turn start |
| `DOCUMENT#` in DynamoDB | Agent doesn't know what docs exist for a package | `STATE#current.packages[].documents[]` |
| `WORKSPACE#` in DynamoDB | Agent doesn't know user's active workspace or overrides | `STATE#current.workspace` |
| `PREF#` in DynamoDB | Agent doesn't know user's preferred model/format/vehicle | `STATE#current.preferences` |
| `TEMPLATE#` in DynamoDB | Agent doesn't know which custom templates to use | `STATE#current.templates[]` |
| `SKILL#` in DynamoDB | Agent doesn't know user's custom skills | `STATE#current.custom_skills[]` |
| `/tmp/` workflow files (Alvee) | Ephemeral, lost on restart | Replaced by `STATE#current.packages[]` |
| localStorage (frontend) | Not accessible to agent | Hydrated from `STATE#current` via SSE |
| Intake form answers | Lost after submission | `STATE#current.packages[].decisions[]` |
| Uploaded user documents | No link to packages | `STATE#current.uploaded_documents[]` |
| Compliance status | Only computed on-demand | `STATE#current.packages[].compliance[]` |
| KB/matrix changes | No detection or notification | `CHANGELOG#` entity + `needs_recheck` flag |

---

## 2. Architecture Overview

### 2.1 Two New DynamoDB Entities

```
STATE#{tenant_id}#{user_id}  /  STATE#current
  → Per-user unified state (single item, ~10-50KB)
  → Read at turn start, written by update_state tool
  → SSE METADATA pushes deltas to frontend

CHANGELOG#{tenant_id}  /  CHANGELOG#{timestamp}#{change_id}
  → Tenant-scoped change log for KB, matrix, templates, skills
  → Written by admin actions (KB approval, matrix edit, template update)
  → Read by recheck_compliance to detect staleness
```

### 2.2 Tool Chain

```
                    ┌──────────────────┐
                    │   update_state   │ ← Agent writes after reasoning
                    │   (13 state_types)│
                    └──────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
       User actions     Doc generation    Recheck chain
       (intake Q&A,     (Alvee's tools    (KB/matrix
        vehicle pick,    write docs →      changes →
        preferences)     update_state)     detect/analyze/fix)

RECHECK CHAIN:
┌─────────────────────┐     ┌────────────────────────────┐     ┌─────────────────────────┐     ┌─────────────┐
│ recheck_compliance  │ ──► │ reanalyze_compliance_matrix │ ──► │ regenerate_package_docs  │ ──► │update_state │
│ (detect)            │     │ reanalyze_decision_matrix   │     │ (remediate)              │     │(persist)    │
│                     │     │ reanalyze_viability_matrix   │     │                          │     │             │
│ "what changed?"     │     │ "how does it affect us?"     │     │ "fix affected docs"      │     │"record it"  │
└─────────────────────┘     └────────────────────────────┘     └─────────────────────────┘     └─────────────┘
       READ-ONLY                    READ-ONLY                       WRITES S3 + DOCUMENT#         WRITES STATE#
```

### 2.3 Data Flow

```
Turn start:
  1. Load STATE#current from DynamoDB
  2. Check packages[].needs_recheck — if true, agent proactively runs recheck chain
  3. Inject state summary into system prompt context

Turn processing:
  4. Agent reasons about user message
  5. Agent calls domain tools (create_document, knowledge_search, etc.)
  6. Agent calls update_state with appropriate state_type
  7. update_state writes to DynamoDB + pushes SSE METADATA

Turn end:
  8. Frontend receives METADATA events → usePackageState updates UI
  9. ChecklistPanel, compliance alerts, phase badges all react

Admin actions (async, outside chat):
  10. KB review approved → update_changelog called
  11. update_changelog scans PACKAGE# entities → sets needs_recheck=true on affected packages
  12. Next user turn picks up the flag (step 2)
```

---

## 3. Unified State Schema

### 3.1 DynamoDB Key

| Field | Value |
|-------|-------|
| PK | `STATE#{tenant_id}#{user_id}` |
| SK | `STATE#current` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `STATE#{user_id}` |
| TTL | None (persistent) |

### 3.2 Full Schema

```json
{
  "pk": "STATE#{tenant_id}#{user_id}",
  "sk": "STATE#current",
  "GSI1PK": "TENANT#{tenant_id}",
  "GSI1SK": "STATE#{user_id}",

  "user": {
    "tenant_id": "string",
    "user_id": "string",
    "email": "string",
    "tier": "basic | advanced | premium",
    "roles": ["string"]
  },

  "preferences": {
    "default_model": "haiku | sonnet | opus",
    "default_doc_format": "docx | pdf | md",
    "preferred_vehicle": "string | null",
    "ui_theme": "light | dark",
    "show_far_citations": "boolean",
    "notification_email": "boolean",
    "default_template": {
      "{doc_type}": "template_id"
    }
  },

  "workspace": {
    "workspace_id": "string",
    "name": "string",
    "is_active": "boolean",
    "override_count": "number",
    "overrides": [
      {
        "entity_type": "AGENT | SKILL | TEMPLATE | CONFIG",
        "name": "string",
        "is_append": "boolean"
      }
    ]
  },

  "active_session_id": "string | null",
  "active_package_id": "string | null",

  "packages": [
    {
      "package_id": "PKG-{YYYY}-{NNNN}",
      "title": "string",
      "phase": "intake | planning | drafting | review | approved | awarded | closed",
      "previous_phase": "string | null",
      "status": "string",
      "acquisition_pathway": "micro_purchase | simplified | full_competition | sole_source",
      "estimated_value": "number (decimal USD)",
      "requirement_type": "it | services | supplies | construction | r_and_d",
      "contract_vehicle": "string | null",
      "vehicle_rationale": "string | null",
      "far_citations": ["string"],
      "session_id": "string | null",
      "created_at": "ISO timestamp",
      "updated_at": "ISO timestamp",

      "documents": [
        {
          "doc_type": "sow | igce | market_research | acquisition_plan | justification | cost_pricing_certification | section_508 | cor_certification",
          "document_id": "string | null",
          "version": "number",
          "status": "not_started | pending | draft | final | superseded",
          "s3_key": "string | null",
          "template_id": "string | null",
          "generated_by": "string",
          "word_count": "number",
          "content_hash": "sha256:string",
          "created_at": "ISO timestamp"
        }
      ],

      "checklist": {
        "required": ["doc_type"],
        "completed": ["doc_type"],
        "missing": ["doc_type"],
        "progress_pct": "0-100",
        "complete": "boolean"
      },

      "compliance": [
        {
          "far_ref": "string",
          "status": "satisfied | pending | violation",
          "note": "string | null",
          "last_checked": "ISO timestamp"
        }
      ],

      "approvals": [
        {
          "step": "co_review | legal_review | hca_review | program_office",
          "status": "pending | approved | rejected | returned",
          "approver": "string | null",
          "decided_at": "ISO timestamp | null",
          "comments": "string | null"
        }
      ],

      "decisions": [
        {
          "question_id": "string",
          "question": "string",
          "options_presented": ["string"],
          "answer": "string",
          "agent_recommendation": "string | null",
          "agent_rationale": "string | null",
          "answered_at": "ISO timestamp",
          "turn_id": "string (message ID)",
          "impact": {
            "fields_set": ["string"],
            "values": {}
          }
        }
      ],

      "intake_data": {
        "security_concerns": {
          "fisma": "low | moderate | high | null",
          "fedramp": "boolean"
        },
        "section_508": "boolean",
        "cor_certification": "boolean",
        "eval_criteria": "lpta | best_value | trade_off",
        "small_business_set_aside": "string | null"
      },

      "needs_recheck": "boolean",
      "recheck_reason": "string | null",
      "recheck_triggered_by": "change_id | null",
      "last_compliance_check": "ISO timestamp | null"
    }
  ],

  "uploaded_documents": [
    {
      "s3_key": "eagle/{tenant}/{user}/uploads/{filename}",
      "filename": "string",
      "content_type": "string (MIME)",
      "size_bytes": "number",
      "uploaded_at": "ISO timestamp",
      "linked_package_id": "string | null"
    }
  ],

  "templates": [
    {
      "doc_type": "string",
      "source": "user_override | tenant_default | global | plugin",
      "template_id": "string",
      "display_name": "string",
      "version": "number",
      "variables": ["string"],
      "updated_at": "ISO timestamp"
    }
  ],

  "custom_skills": [
    {
      "skill_id": "string",
      "name": "string",
      "display_name": "string",
      "status": "draft | review | active | disabled",
      "visibility": "private | public",
      "triggers": ["string"],
      "version": "number"
    }
  ],

  "kb_context": {
    "recent_searches": [
      {
        "query": "string",
        "result_count": "number",
        "timestamp": "ISO timestamp"
      }
    ],
    "fetched_documents": [
      {
        "document_id": "string",
        "title": "string",
        "s3_key": "string"
      }
    ],
    "pending_reviews": "number"
  },

  "usage": {
    "messages_today": "number",
    "tokens_today": "number",
    "cost_today_usd": "number (decimal)",
    "active_sessions": "number",
    "tier_limits": {
      "messages_per_day": "number",
      "tokens_per_day": "number"
    }
  },

  "updated_at": "ISO timestamp"
}
```

### 3.3 Size Estimate

| Section | Typical size |
|---------|-------------|
| user + preferences + workspace | ~500 bytes |
| 1 package (5 docs, 8 compliance, 6 decisions) | ~3KB |
| 5 packages | ~15KB |
| uploaded_documents (10 files) | ~2KB |
| templates + skills + kb_context + usage | ~2KB |
| **Total (typical user)** | **~20KB** |
| **DynamoDB item limit** | **400KB** |

Comfortable headroom. If a power user somehow exceeds 400KB (100+ packages), we archive closed packages to `STATE#{tenant}#{user}` / `STATE#archive#{year}`.

---

## 4. Changelog Entity Schema

### 4.1 DynamoDB Key

| Field | Value |
|-------|-------|
| PK | `CHANGELOG#{tenant_id}` |
| SK | `CHANGELOG#{timestamp}#{change_id}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `CHANGELOG#{entity_type}#{timestamp}` |
| TTL | 90 days |

### 4.2 Item Schema

```json
{
  "pk": "CHANGELOG#{tenant_id}",
  "sk": "CHANGELOG#{timestamp}#{change_id}",

  "change_id": "string (uuid)",
  "change_type": "kb_document_added | kb_document_updated | kb_document_removed | matrix_rule_added | matrix_rule_updated | matrix_rule_removed | template_updated | skill_published | prompt_overridden",
  "entity_type": "knowledge_base | decision_matrix | compliance_matrix | template | skill | prompt",
  "entity_id": "string",
  "entity_title": "string",

  "actor": {
    "user_id": "string",
    "role": "admin | system",
    "method": "upload | api | review_approval | sync"
  },

  "before": {},
  "after": {},

  "downstream_impact": {
    "affected_pathways": ["full_competition", "simplified"],
    "affected_doc_types": ["sow", "igce"],
    "compliance_recheck_needed": "boolean"
  },

  "created_at": "ISO timestamp",
  "ttl": "epoch (90 days from creation)"
}
```

### 4.3 Where Changelog Entries Are Created

| Admin Action | Endpoint | Changelog `change_type` |
|-------------|----------|------------------------|
| KB review approved | `POST /api/admin/kb-review/{id}/approve` | `kb_document_added` or `kb_document_updated` |
| KB review rejected | `POST /api/admin/kb-review/{id}/reject` | No changelog (rejection = no change) |
| Matrix rule edited | `PUT /api/admin/plugin/refdata/contract-matrix` | `matrix_rule_updated` |
| Template updated | `POST /api/templates/{doc_type}` | `template_updated` |
| Skill published | `POST /api/skills/{id}/publish` | `skill_published` |
| Prompt overridden | `PUT /api/admin/prompts/{agent}` | `prompt_overridden` |
| Plugin reseeded | `POST /api/admin/plugin/sync` | `matrix_rule_updated` (bulk) |

After writing the changelog entry, the endpoint calls a helper function `_flag_affected_packages(tenant_id, downstream_impact)` which:
1. Queries `PACKAGE#{tenant_id}` for active packages (status != closed)
2. Sets `needs_recheck=true` + `recheck_reason` + `recheck_triggered_by` on matching packages
3. Also updates the corresponding `STATE#current` items

---

## 5. Tool Definitions

### 5.1 `update_state` — State Persistence (expanded)

**Type**: Strands `@tool`
**Reads**: Current `STATE#current`
**Writes**: `STATE#current` in DynamoDB + SSE METADATA event

| `state_type` | Fields updated | When |
|--------------|---------------|------|
| `package_created` | `packages[]` += new, `active_package_id` | User starts acquisition |
| `document_ready` | `packages[].documents[]`, `checklist` | After `create_document` succeeds |
| `phase_change` | `packages[].phase`, `previous_phase` | Workflow transition |
| `checklist_update` | `packages[].checklist` | Any doc status change |
| `compliance_alert` | `packages[].compliance[]` | After compliance matrix query |
| `vehicle_selected` | `packages[].contract_vehicle`, `vehicle_rationale` | Vehicle recommendation accepted |
| `approval_update` | `packages[].approvals[]` | Approval chain progress |
| `upload_linked` | `uploaded_documents[].linked_package_id` | User uploads doc for package |
| `template_selected` | `templates[]`, `preferences.default_template` | User picks custom template |
| `intake_updated` | `packages[].intake_data` | Intake form fields filled |
| `decision_recorded` | `packages[].decisions[]` += new | Intake Q&A answer captured |
| `preferences_changed` | `preferences` | User changes settings |
| `workspace_switched` | `workspace` | User activates different workspace |
| `skill_created` | `custom_skills[]` | User creates/publishes custom skill |
| `compliance_rechecked` | `packages[].compliance[]`, clears `needs_recheck` | After recheck chain completes |
| `usage_warning` | `usage` | Approaching tier limits |

**Implementation notes**:
- Reads current state, merges delta, writes back (optimistic — no locking needed for single-user state)
- Pushes SSE METADATA with the delta (not the full state) for frontend reactivity
- Auto-stamps `updated_at` on every write
- Auto-stamps `answered_at` and `turn_id` for `decision_recorded`

### 5.2 `update_changelog` — Tenant Change Log

**Type**: Python function (not an agent tool — called by API endpoints)
**Reads**: Nothing
**Writes**: `CHANGELOG#` item + flags on affected `PACKAGE#` and `STATE#` items

```python
async def update_changelog(
    tenant_id: str,
    change_type: str,          # e.g., "kb_document_added"
    entity_type: str,          # e.g., "knowledge_base"
    entity_id: str,
    entity_title: str,
    actor: dict,               # { user_id, role, method }
    before: dict | None,
    after: dict | None,
    downstream_impact: dict,   # { affected_pathways, affected_doc_types, compliance_recheck_needed }
) -> str:                      # Returns change_id
```

### 5.3 `recheck_compliance` — Detection

**Type**: Strands `@tool`
**Reads**: `CHANGELOG#` entries newer than `package.last_compliance_check`, `STATE#current`
**Writes**: Nothing (read-only)

```python
@tool(name="recheck_compliance")
def recheck_compliance(package_id: str) -> str:
    """Check if a package has been affected by recent KB, matrix, or template changes.

    Args:
        package_id: The acquisition package ID to check

    Returns:
        JSON with changes_detected, changelog_entries, stale_items,
        matrices_affected (compliance, decision, vehicle), severity,
        and recommendation for which reanalyze tools to call.
    """
```

**Output schema**:
```json
{
  "changes_detected": "number",
  "changelog_entries": [
    {
      "change_id": "string",
      "change_type": "string",
      "entity_title": "string",
      "timestamp": "ISO timestamp"
    }
  ],
  "stale_items": {
    "documents": ["doc_type"],
    "compliance_rules": ["far_ref"],
    "vehicle_selection": "boolean"
  },
  "matrices_affected": {
    "compliance": "boolean",
    "decision": "boolean",
    "vehicle": "boolean"
  },
  "severity": "info | warning | critical",
  "recommendation": "string"
}
```

### 5.4 `reanalyze_compliance_matrix` — FAR/DFARS Compliance Analysis

**Type**: Strands `@tool`
**Reads**: Compliance matrix (contract_matrix.py), KB documents, `STATE#current`
**Writes**: Nothing (read-only)

```python
@tool(name="reanalyze_compliance_matrix")
def reanalyze_compliance_matrix(package_id: str, trigger: str = "") -> str:
    """Re-run the full FAR/DFARS compliance matrix against a package.

    Compares current compliance status with a fresh analysis to find
    new violations, newly satisfied rules, or changed requirements.

    Args:
        package_id: The acquisition package ID
        trigger: Optional changelog change_id that triggered this recheck

    Returns:
        JSON with previous_status, current_status, changes (diff of
        what moved between satisfied/pending/violation), and
        affected_documents that need updates.
    """
```

**Output schema**:
```json
{
  "previous_status": {
    "satisfied": "number",
    "pending": "number",
    "violations": "number"
  },
  "current_status": {
    "satisfied": "number",
    "pending": "number",
    "violations": "number"
  },
  "changes": [
    {
      "far_ref": "string",
      "previous": "satisfied | pending | violation | null",
      "current": "satisfied | pending | violation",
      "reason": "string",
      "remediation": "string"
    }
  ],
  "affected_documents": ["doc_type"]
}
```

### 5.5 `reanalyze_decision_matrix` — Acquisition Strategy Analysis

**Type**: Strands `@tool`
**Reads**: FAR thresholds, decision matrix data, `STATE#current`
**Writes**: Nothing (read-only)

```python
@tool(name="reanalyze_decision_matrix")
def reanalyze_decision_matrix(package_id: str, trigger: str = "") -> str:
    """Re-evaluate the acquisition pathway, required documents, approval
    chain, and evaluation criteria for a package.

    Called when estimated value changes, requirement type changes, or
    FAR threshold rules are updated.

    Args:
        package_id: The acquisition package ID
        trigger: Optional changelog change_id that triggered this recheck

    Returns:
        JSON with before/after diffs for pathway, required_documents,
        approval_chain, and evaluation_criteria. Only includes sections
        where changes were detected.
    """
```

**Output schema**:
```json
{
  "pathway": {
    "previous": "string",
    "current": "string",
    "changed": "boolean"
  },
  "required_documents": {
    "previous": ["doc_type"],
    "current": ["doc_type"],
    "added": ["doc_type"],
    "removed": ["doc_type"]
  },
  "approval_chain": {
    "previous": ["step"],
    "current": ["step"],
    "added": ["step"],
    "reason": "string"
  },
  "evaluation_criteria": {
    "changed": "boolean",
    "reason": "string",
    "previous_factors": ["string"],
    "current_factors": ["string"]
  }
}
```

### 5.6 `reanalyze_viability_matrix` — Vehicle Fitness Analysis

**Type**: Strands `@tool`
**Reads**: Vehicle data (load_data), `STATE#current`
**Writes**: Nothing (read-only)

```python
@tool(name="reanalyze_viability_matrix")
def reanalyze_viability_matrix(package_id: str, trigger: str = "") -> str:
    """Re-score the current contract vehicle against updated requirements.

    Checks if the selected vehicle still meets dollar thresholds, scope
    limitations, security requirements, and small business mandates.

    Args:
        package_id: The acquisition package ID
        trigger: Optional changelog change_id that triggered this recheck

    Returns:
        JSON with current vehicle score (before/after), concerns,
        alternative vehicles if score dropped, and whether a vehicle
        change is recommended.
    """
```

**Output schema**:
```json
{
  "current_vehicle": "string",
  "still_viable": "boolean",
  "viability_score": {
    "previous": "0.0-1.0",
    "current": "0.0-1.0",
    "delta": "number"
  },
  "concerns": [
    {
      "factor": "string",
      "impact": "string",
      "severity": "info | warning | critical",
      "mitigation": "string"
    }
  ],
  "alternatives_if_not_viable": [
    {
      "vehicle": "string",
      "viability_score": "0.0-1.0",
      "advantage": "string",
      "disadvantage": "string"
    }
  ],
  "recommendation": "string",
  "vehicle_change_needed": "boolean"
}
```

### 5.7 `regenerate_package_docs` — Document Remediation

**Type**: Strands `@tool`
**Reads**: Templates, KB, `STATE#current`
**Writes**: `DOCUMENT#` in DynamoDB, content to S3

```python
@tool(name="regenerate_package_docs")
def regenerate_package_docs(
    package_id: str,
    documents: list[str],
    reason: str,
    changes_to_apply: list[dict] | None = None,
    mode: str = "incremental"
) -> str:
    """Regenerate or patch acquisition documents affected by compliance,
    strategy, or KB changes.

    Args:
        package_id: The acquisition package ID
        documents: List of doc_types to regenerate (e.g., ["sow", "igce"])
        reason: Why regeneration is needed (shown in version history)
        changes_to_apply: Optional specific changes per doc (section adds/edits)
        mode: "incremental" (patch sections) or "full" (regenerate from scratch)

    Returns:
        JSON with regenerated documents (new versions, s3_keys),
        skipped documents, and any new documents needed.
    """
```

**Output schema**:
```json
{
  "regenerated": [
    {
      "doc_type": "string",
      "previous_version": "number",
      "new_version": "number",
      "changes_applied": ["string"],
      "s3_key": "string",
      "document_id": "string"
    }
  ],
  "skipped": [
    {
      "doc_type": "string",
      "reason": "string"
    }
  ],
  "new_documents_needed": ["doc_type"]
}
```

**Modes**:
- `incremental` — Loads current doc content from S3, applies targeted edits (add section, update clause, insert citation). Used for minor KB/compliance changes.
- `full` — Regenerates from template + KB + state. Used when pathway changes or document is fundamentally wrong.

---

## 6. System Prompt Additions

### 6.1 State Loading Preamble (injected at turn start)

```
Current User State:
  Tenant: {tenant_id} | User: {user_id} | Tier: {tier}
  Workspace: {workspace.name} ({override_count} overrides)
  Active Package: {active_package_id or "none"}
  {if active_package:}
    Phase: {phase} | Pathway: {acquisition_pathway} | Value: ${estimated_value}
    Checklist: {completed}/{required} ({progress_pct}%)
    Vehicle: {contract_vehicle or "not selected"}
    Compliance: {satisfied} satisfied, {pending} pending, {violations} violations
    Needs Recheck: {needs_recheck} {recheck_reason or ""}
  {endif}
  Uploaded Documents: {count}
  Custom Templates: {count}
  Custom Skills: {count}
```

### 6.2 State Push Rules (added to supervisor prompt)

```
State Management Rules:
You have access to a persistent user state object. It is loaded at the start of every turn.

DECISION RECORDING:
When you ask the user a question and they answer (requirement type, estimated value,
vehicle selection, security requirements, evaluation criteria, etc.):
1. Process their answer and determine what fields it sets
2. Call update_state with state_type="decision_recorded" including:
   - question_id: stable identifier for the question
   - question: the question you asked
   - options_presented: if you gave choices, list them
   - answer: the user's answer
   - agent_recommendation: your recommendation if you gave one
   - agent_rationale: why you recommended it
   - impact: { fields_set: [...], values: { ... } }
This creates an audit trail of how the package was configured.

STATE UPDATES AFTER ACTIONS:
- After create_document → update_state(state_type="document_ready", ...)
- After compliance query → update_state(state_type="compliance_alert", ...)
- After vehicle selection → update_state(state_type="vehicle_selected", ...)
- After phase transition → update_state(state_type="phase_change", ...)
- After user uploads doc → update_state(state_type="upload_linked", ...)

COMPLIANCE RECHECK PROTOCOL:
When you load a package with needs_recheck=true:
1. Tell the user: "I've detected changes to [reason] since your last session."
2. Call recheck_compliance(package_id) to identify what changed
3. Based on matrices_affected, call ONLY the relevant reanalyze tools:
   - compliance=true → reanalyze_compliance_matrix
   - decision=true  → reanalyze_decision_matrix
   - vehicle=true   → reanalyze_viability_matrix
4. Present findings to the user with specific impacts
5. Ask: "Should I update the affected documents?"
6. If yes → call regenerate_package_docs (incremental for minor changes, full if pathway changed)
7. Call update_state(state_type="compliance_rechecked") to clear the flag
NEVER auto-regenerate documents without user confirmation.
```

---

## 7. Implementation Plan

### Phase 1: State Store + `update_state` Tool

**Files to create**:

| File | Purpose |
|------|---------|
| `server/app/state_store.py` | CRUD for `STATE#current` DynamoDB entity |
| `server/app/changelog_store.py` | CRUD for `CHANGELOG#` DynamoDB entity |

**Files to modify**:

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Add `_make_update_state_tool()` (expand existing), add state loading at turn start |
| `server/app/streaming_routes.py` | Load `STATE#current` before streaming, inject into system prompt context |
| `server/app/stream_protocol.py` | Ensure `write_metadata()` handles all 16 state_types |
| `server/app/main.py` | Add `GET /api/state` and `PUT /api/state` endpoints for frontend hydration |
| `client/hooks/use-package-state.ts` | Expand to handle all new state_types from SSE METADATA |
| `client/hooks/use-agent-stream.ts` | No change needed — already forwards metadata events |
| `client/components/chat-simple/checklist-panel.tsx` | Expand to show decisions, compliance details, vehicle info |

**Validation**:
```bash
ruff check server/app/state_store.py server/app/changelog_store.py
python -m pytest tests/test_state_store.py -v
```

### Phase 2: Changelog + Recheck Detection

**Files to create**:

| File | Purpose |
|------|---------|
| `server/tests/test_state_store.py` | Unit tests for state CRUD + merge logic |
| `server/tests/test_changelog_store.py` | Unit tests for changelog CRUD + package flagging |

**Files to modify**:

| File | Change |
|------|--------|
| `server/app/main.py` | Add `update_changelog()` calls to KB review, matrix edit, template update endpoints |
| `server/app/strands_agentic_service.py` | Add `recheck_compliance` tool + `run_recheck` graph wrapper |
| `server/app/tools/contract_matrix.py` | Expose matrix comparison function for recheck |

**Validation**:
```bash
ruff check server/app/
python -m pytest tests/test_state_store.py tests/test_changelog_store.py -v
```

### Phase 3: Reanalyze Tools + Graph-Based Recheck Chain

**Architecture change**: Instead of 3 individual reanalyze tools registered on the supervisor, we build a Strands `Graph` that the supervisor calls via a single `run_recheck` tool. The graph executes detect → parallel analysis → remediation with conditional edges.

**Files to create**:

| File | Purpose |
|------|---------|
| `server/app/tools/decision_matrix.py` | Decision matrix logic (pathway, required docs, approval chain, eval criteria) |
| `server/app/tools/viability_matrix.py` | Vehicle viability scoring + alternatives |
| `server/app/recheck_graph.py` | `build_recheck_graph()` — Strands Graph with 5 nodes + conditional edges |
| `server/tests/test_reanalyze_tools.py` | Unit tests for all 3 reanalyze tools |
| `server/tests/test_recheck_graph.py` | Graph integration tests — conditional edges, parallel execution, metrics |

**Files to modify**:

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Add `run_recheck` tool (Graph wrapper), register in compliance tool group |
| `server/app/tools/contract_matrix.py` | Add `compare_compliance()` function for before/after diff |

**Graph topology**:
```
detect → [compliance ‖ decision ‖ vehicle] → remediate
         (conditional)  (conditional)  (conditional)
         (parallel execution of ready nodes)
```

**Validation**:
```bash
ruff check server/app/tools/ server/app/recheck_graph.py
python -m pytest tests/test_reanalyze_tools.py tests/test_recheck_graph.py -v
```

### Phase 4: Regeneration Tool + AgentSkills Plugin + Dynamic Tools

**Files to modify**:

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Replace `list_skills`/`load_skill` with `AgentSkills` plugin, add `load_tools` meta-tool, add `regenerate_package_docs` tool, add `_resolve_phase_tools()`, update `build_supervisor_prompt()` |
| `server/app/document_service.py` | Add `regenerate_document()` method (incremental + full modes) |
| `eagle-plugin/agents/supervisor/agent.md` | Add state management, recheck protocol, progressive disclosure instructions |

**Files to create**:

| File | Purpose |
|------|---------|
| `server/tests/test_regenerate_docs.py` | Unit tests for incremental and full regeneration |
| `server/tests/test_dynamic_tools.py` | Tests for `load_tools`, `_resolve_phase_tools`, phase→tool mapping |

**Key changes**:
- Delete `_make_list_skills_tool()` and `_make_load_skill_tool()` factories
- Add `AgentSkills(skills=["./eagle-plugin/skills/", "./eagle-plugin/agents/"])` plugin
- Add `load_tools()` meta-tool for dynamic tool registration
- Add `TOOL_GROUPS` and `TOOL_FACTORIES` dicts
- Change `Agent(tools=skill_tools + service_tools)` → `Agent(plugins=[skills_plugin], tools=phase_tools)`

**Validation**:
```bash
ruff check server/app/
python -m pytest tests/ -v
npx tsc --noEmit  # Frontend type check
```

### Phase 5: Frontend Integration

**Files to modify**:

| File | Change |
|------|--------|
| `client/hooks/use-package-state.ts` | Handle all 16 state_types, expand PackageState interface |
| `client/components/chat-simple/checklist-panel.tsx` | Show decisions trail, compliance diff, vehicle status, recheck banner |
| `client/components/chat-simple/simple-chat-interface.tsx` | Load initial state from `GET /api/state`, pass to checklist panel |
| `client/lib/document-store.ts` | Sync with backend state instead of localStorage-only |

**Validation**:
```bash
npx tsc --noEmit
npx playwright test
```

---

## 8. Migration Strategy

### Existing packages → STATE#current

When `GET /api/state` is called and no `STATE#current` exists:
1. Query `PACKAGE#{tenant_id}` for user's packages
2. Query `WORKSPACE#{tenant_id}#{user_id}` for active workspace
3. Query `PREF#{tenant_id}` / `PREF#{user_id}` for preferences
4. Query `SKILL#{tenant_id}` for user's custom skills
5. Query `TEMPLATE#{tenant_id}` for user's template overrides
6. Assemble into STATE schema and write `STATE#current`
7. Return assembled state

This is a **lazy migration** — state is assembled on first access, then maintained by `update_state` going forward.

### Keeping STATE# in sync with source entities

`STATE#current` is a **denormalized view**. The source-of-truth entities (`PACKAGE#`, `DOCUMENT#`, `WORKSPACE#`, etc.) continue to exist. Two sync strategies:

1. **Write-through**: When `update_state` updates `packages[].phase`, it also writes to `PACKAGE#`. This keeps both in sync.
2. **Periodic reconciliation**: A background job or turn-start check compares `STATE#current` with source entities and resolves drift.

Recommend **write-through** for Phase 1 (simpler, no drift), with reconciliation added in Phase 3 as a safety net.

---

## 9. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| STATE# item exceeds 400KB | DynamoDB rejects write | Archive closed packages to `STATE#archive#{year}` |
| Race condition on STATE# updates | Lost updates if two tabs open | Last-writer-wins is acceptable for single-user state; add `version` field for optimistic locking if needed |
| Changelog spam on bulk KB import | Hundreds of `needs_recheck` flags | Batch changelog entries, debounce flagging to once per import |
| Recheck chain burns tokens | 3 reanalyze tools + regeneration = expensive turn | Agent asks user before running; `recheck_compliance` is cheap (read-only), only fans out if user approves |
| Alvee's branch merge conflicts | `strands_agentic_service.py` heavily modified on both branches | Merge Alvee's doc generation tools first, then layer state tools on top |
| Frontend state desync | SSE metadata lost (network drop) | `GET /api/state` on reconnect to hydrate full state |

---

## 10. Validation Commands

```bash
# L1 — Lint
ruff check server/app/state_store.py server/app/changelog_store.py
ruff check server/app/tools/decision_matrix.py server/app/tools/viability_matrix.py
npx tsc --noEmit

# L2 — Unit tests
python -m pytest tests/test_state_store.py tests/test_changelog_store.py -v
python -m pytest tests/test_reanalyze_tools.py tests/test_regenerate_docs.py -v

# L3 — E2E
npx playwright test

# L3.5 — Agentic validation
# Send message → verify STATE#current updated → verify SSE METADATA received
# Upload KB doc → verify CHANGELOG# created → verify needs_recheck set
# Start new session with stale package → verify recheck flow triggered

# L4 — Infra (no CDK changes needed — uses existing table)
# No validation needed unless adding GSI
```

---

## 11. Open Questions

1. **Should `STATE#current` replace or coexist with `PACKAGE#`?** Recommend coexist (write-through) — `PACKAGE#` is queryable by admins across all users, while `STATE#` is per-user.

2. **Should closed packages be auto-archived from STATE?** Yes — once a package reaches `closed` status, move it to `STATE#archive#{year}` to keep the main item small.

3. **How long should `CHANGELOG#` entries persist?** 90 days recommended — enough for audit trail, TTL handles cleanup.

4. **Should the agent auto-run recheck, or only when user starts a conversation?** Only at conversation start (turn 1) or when user explicitly asks. Don't interrupt mid-conversation.

5. **Merge order with Alvee's branch?** Merge Alvee first (his doc generation tools are a dependency for `regenerate_package_docs`). Then layer state schema on top.

---

## 12. Strands SDK Native Integration

### 12.1 What Strands Gives Us For Free

Strands Agents SDK (v1.30.0) provides native features that replace significant parts of our custom implementation:

| Feature | Strands native | Our custom layer |
|---------|---------------|-----------------|
| `agent.state` dict | JSON-serializable key-value store, auto-persisted | We store our full schema here |
| `SessionManager` | Auto-saves state + messages after every invocation | Replaces manual DynamoDB writes |
| `ToolContext.state` | Tools read/write `agent.state` directly | Our `update_state` tool uses this |
| `invocation_state` | Parent → child state passing (PR #761) | Supervisor passes context to subagents |
| Interleaved text + tools | Model naturally emits text between tool calls via `recurse_event_loop()` | No custom work needed — agent narrates between each tool call |
| `ConversationManager` | Sliding window + summarization for context control | We use this for long conversations |
| **AgentSkills plugin** (v1.30.0) | Progressive disclosure: metadata in system prompt, full instructions on-demand via `skills` tool | **Replaces our custom `list_skills()` + `load_skill()`** |
| **ToolRegistry.register_tool()** | Add tools post-construction, takes effect on next model turn | Powers our `load_tools()` meta-tool |
| **BeforeToolCallEvent hooks** | Block/redirect tool calls based on state (`cancel_tool`, `selected_tool`) | Phase-based tool gating |
| **Plugin system** (v1.28.0+) | `@hook` + `@tool` auto-discovery, `init_agent()` lifecycle | Our AgentSkills integration |
| **Swarm** | Self-organizing agent teams with `handoff_to_agent` tool + `SharedContext` | Not used — EAGLE needs central coordinator |
| **Graph** (v1.30.0) | Deterministic DAG with conditional edges, parallel execution, nested graphs | **Powers our recheck chain** |
| **Steering system** (v1.30.0) | `Proceed`/`Guide`/`Interrupt` actions for just-in-time tool gating | Future: human-in-the-loop approval steps |

### 12.2 What We Still Build Custom

| Component | Why Strands can't do it |
|-----------|------------------------|
| `update_state` tool | `agent.state` is invisible to the model — tool gives the model a way to *reason* then write state |
| SSE METADATA push | Strands persists state but has no frontend notification mechanism |
| `CHANGELOG#` entity | Tenant-scoped change tracking — no Strands equivalent |
| `load_tools()` meta-tool | Strands has `register_tool()` but no built-in phase-driven tool group loader |
| `DynamoDBSessionRepository` | No built-in DynamoDB backend — we implement `SessionRepository` interface |
| State summary in system prompt | Strands doesn't inject state into prompt — we do it at turn start |

### 12.3 AgentSkills Plugin — Replaces `list_skills()` + `load_skill()`

**Before (custom, 3 factory functions)**:
```python
# Current: 3 custom tools + system prompt wiring
tools.append(_make_list_skills_tool(result_queue, loop))    # Layer 2
tools.append(_make_load_skill_tool(result_queue, loop))     # Layer 3
tools.append(_make_load_data_tool(result_queue, loop))      # Layer 4
```

**After (native plugin + 1 custom tool)**:
```python
from strands import Agent
from strands.vended_plugins.skills import AgentSkills

# Load all EAGLE skills from eagle-plugin/skills/ and agents/
skills_plugin = AgentSkills(
    skills=["./eagle-plugin/skills/", "./eagle-plugin/agents/"],
    state_key="eagle_skills",
)

supervisor = Agent(
    model=_model,
    system_prompt=system_prompt,
    plugins=[skills_plugin],          # ← Replaces list_skills + load_skill
    tools=core_tools + phase_tools,   # ← Only tools needed for current phase
)
```

**What the plugin does automatically**:
1. `BeforeInvocationEvent` hook fires → injects `<available_skills>` XML into system prompt:
   ```xml
   <available_skills>
   <skill><name>oa-intake</name><description>Guide users through OA intake...</description></skill>
   <skill><name>compliance</name><description>FAR/DFARS compliance analysis...</description></skill>
   ...
   </available_skills>
   ```
2. Agent calls `skills(skill_name="oa-intake")` → gets full SKILL.md instructions
3. Tracks activated skills in `agent.state["eagle_skills"]["activated_skills"]`
4. `set_available_skills()` allows swapping skill set at runtime (per-workspace overrides)

**What we keep custom**: `load_data(name, section?)` — for reference data (thresholds, vehicles, FAR rules). AgentSkills is for instructions, not data.

**Migration**: Delete `_make_list_skills_tool()` and `_make_load_skill_tool()` factories. Keep `_make_load_data_tool()`. Update supervisor prompt to remove manual Layer 2/3 documentation — the plugin handles it.

### 12.4 State-Driven Dynamic Tool Registry (Option C)

Instead of passing all ~25 tools at construction, the supervisor starts with **core tools** (~8) and loads phase-appropriate tools based on `STATE#current`. The agent can also call `load_tools(category)` mid-turn.

#### Tool Groups

```python
TOOL_GROUPS = {
    "intake": {
        "description": "Intake workflow, contract matrix, vehicle scoring",
        "tools": ["oa_intake", "intake_workflow", "query_contract_matrix"],
        "auto_for_phases": ["intake"],
    },
    "planning": {
        "description": "Acquisition strategy analysis, decision/viability matrices",
        "tools": ["query_contract_matrix", "reanalyze_decision_matrix",
                  "reanalyze_viability_matrix"],
        "auto_for_phases": ["planning"],
    },
    "drafting": {
        "description": "Document generation and regeneration",
        "tools": ["create_document", "regenerate_package_docs"],
        "auto_for_phases": ["planning", "drafting"],
    },
    "compliance": {
        "description": "Full recheck chain — detect, analyze, remediate",
        "tools": ["recheck_compliance", "reanalyze_compliance_matrix",
                  "reanalyze_decision_matrix", "reanalyze_viability_matrix",
                  "regenerate_package_docs"],
        "auto_for_phases": ["review"],
        "auto_for_flags": ["needs_recheck"],
    },
    "review": {
        "description": "Approval chain, compliance verification",
        "tools": ["recheck_compliance", "reanalyze_compliance_matrix"],
        "auto_for_phases": ["review", "approved"],
    },
}
```

#### Core Tools (always loaded, ~8)

```python
CORE_TOOLS = [
    "update_state",         # State persistence + SSE push
    "get_state",            # Read current state
    "load_data",            # Reference data (thresholds, vehicles, FAR rules)
    "load_tools",           # Meta-tool: register phase/specialist tools
    "knowledge_search",     # KB search
    "knowledge_fetch",      # KB document fetch
    "search_far",           # FAR/DFARS clause lookup
    "query_contract_matrix",# FAR 16.104 scoring (always useful)
]
```

#### `load_tools` Meta-Tool

```python
@tool(name="load_tools")
def load_tools(tool_context: ToolContext, category: str) -> str:
    """Load additional tools for a workflow phase or capability.

    Available categories:
      - intake: Intake workflow + contract matrix + vehicle scoring
      - planning: Decision matrix + viability analysis
      - drafting: Document generation + regeneration
      - compliance: Full recheck chain (detect → analyze → remediate)
      - review: Approval chain + compliance verification
      - specialist:{name}: Load a single specialist subagent tool
        (e.g., specialist:legal-counsel, specialist:market-intelligence)
      - all_specialists: Load all specialist subagent tools

    Tools persist for the remainder of this conversation turn.

    Args:
        category: Tool group or specialist name to load

    Returns:
        JSON with loaded tool names and their descriptions.
    """
    agent = tool_context.agent
    registry = agent.tool_registry
    loaded = []

    if category.startswith("specialist:"):
        name = category.split(":", 1)[1]
        if name not in registry.registry:
            tool_fn = _build_specialist_tool(name)
            if tool_fn:
                registry.register_tool(tool_fn)
                loaded.append({"name": name, "type": "specialist"})

    elif category == "all_specialists":
        for name in SKILL_AGENT_REGISTRY:
            if name not in registry.registry:
                tool_fn = _build_specialist_tool(name)
                if tool_fn:
                    registry.register_tool(tool_fn)
                    loaded.append({"name": name, "type": "specialist"})

    elif category in TOOL_GROUPS:
        group = TOOL_GROUPS[category]
        for tool_name in group["tools"]:
            if tool_name not in registry.registry:
                tool_fn = TOOL_FACTORIES[tool_name]()
                registry.register_tool(tool_fn)
                loaded.append({"name": tool_name, "type": "service"})

    _emit_tool_result("load_tools", json.dumps(loaded), result_queue, loop)
    return json.dumps({
        "loaded": loaded,
        "total_tools_now": len(registry.registry),
        "message": f"Loaded {len(loaded)} tools for '{category}'"
    })
```

#### Phase Resolution at Turn Start

```python
def _resolve_phase_tools(
    state: dict | None,
    tool_factories: dict,
    result_queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> list:
    """Return core + phase-appropriate tools based on user state."""
    tools = _build_core_tools(result_queue, loop)

    if not state:
        # New user — give intake tools
        tools += _build_group_tools("intake", tool_factories, result_queue, loop)
        return tools

    active_pkg_id = state.get("active_package_id")
    phase = None
    needs_recheck = False

    if active_pkg_id:
        for pkg in state.get("packages", []):
            if pkg["package_id"] == active_pkg_id:
                phase = pkg.get("phase", "intake")
                needs_recheck = pkg.get("needs_recheck", False)
                break

    loaded_groups = set()
    for group_name, group_def in TOOL_GROUPS.items():
        if phase in group_def.get("auto_for_phases", []):
            loaded_groups.add(group_name)
        if needs_recheck and "needs_recheck" in group_def.get("auto_for_flags", []):
            loaded_groups.add(group_name)

    if not loaded_groups:
        loaded_groups.add("intake")

    for group_name in loaded_groups:
        tools += _build_group_tools(group_name, tool_factories, result_queue, loop)

    return tools
```

#### Phase Change → Auto-Register New Tools

When `update_state` fires a `phase_change`, new phase tools are registered immediately:

```python
# Inside update_state tool handler
if state_type == "phase_change":
    new_phase = kwargs.get("phase")
    group = PHASE_TO_GROUP.get(new_phase)
    if group:
        registry = tool_context.agent.tool_registry
        for tool_name in TOOL_GROUPS[group]["tools"]:
            if tool_name not in registry.registry:
                tool_fn = TOOL_FACTORIES[tool_name]()
                registry.register_tool(tool_fn)
```

**Why this works**: `get_all_tool_specs()` is called every model turn (event_loop.py:329). After `update_state` executes, `recurse_event_loop()` loops back and calls the model again — the model sees the newly registered tools on its next turn.

#### Context Window Savings

| Scenario | Tools visible | vs current (~25) |
|----------|--------------|-------------------|
| New user, no state | 8 core + 3 intake = **11** | -14 tools |
| Active intake | 8 core + 3 intake = **11** | -14 |
| Planning phase | 8 core + 3 planning + 2 drafting = **13** | -12 |
| Drafting phase | 8 core + 2 drafting = **10** | -15 |
| Review + recheck | 8 core + 5 compliance + 2 review = **15** | -10 |
| Agent loads 2 specialists | above + 2 = **17** | -8 |

At ~200-400 tokens per tool schema, that's **2,000-6,000 tokens saved per turn**.

#### Updated Supervisor Prompt

```
Progressive Disclosure (how to access tools and information):
  You start each turn with CORE tools + tools for the user's current phase.

  CORE (always available):
    update_state, get_state, load_data, load_tools,
    knowledge_search, knowledge_fetch, search_far, query_contract_matrix

  PHASE-LOADED (auto-loaded based on acquisition phase):
    Currently loaded: {comma-separated list of auto-loaded tools}

  ON-DEMAND (load via load_tools):
    load_tools("drafting")                  → create_document, regenerate_package_docs
    load_tools("compliance")                → full recheck chain
    load_tools("specialist:legal-counsel")  → legal analysis subagent
    load_tools("all_specialists")           → all specialist subagents

  SKILLS (via AgentSkills plugin — see <available_skills> above):
    Call skills("oa-intake") to load full skill instructions.
    Prefer skills() for reading workflows over load_tools("specialist:...") for spawning subagents.

  REFERENCE DATA (via load_data):
    load_data("matrix", "thresholds")       → FAR threshold values
    load_data("contract-vehicles", "nitaac") → vehicle details

  RULES:
  1. Check if the tool you need is already loaded before calling load_tools.
  2. If you need a specialist, load ONLY that specialist — not all_specialists.
  3. After a phase_change, new phase tools are auto-registered.
  4. Prefer skills(name) for reading instructions over load_tools("specialist:name").
```

### 12.5 Graph-Based Recheck Chain

The recheck chain (detect → analyze → remediate) maps naturally to a Strands `Graph` with conditional edges and parallel execution.

#### Architecture

```
                          ┌─────────────────┐
                          │  detect          │
                          │  (recheck_       │
                          │   compliance)    │
                          └────────┬────────┘
                                   │
                     ┌─────────────┼─────────────┐
                     │ if compliance │ if vehicle  │
                     │ affected      │ affected    │
                     ▼               │             ▼
            ┌────────────┐    ┌─────▼──────┐   ┌──────────┐
            │ compliance │    │  decision  │   │ vehicle  │
            │ reanalyze  │    │  reanalyze │   │ reanalyze│
            └─────┬──────┘    └─────┬──────┘   └────┬─────┘
                  │                 │                │
                  └─────────────────┼────────────────┘
                                    ▼
                          ┌─────────────────┐
                          │  remediate       │
                          │  (regenerate_    │
                          │   package_docs + │
                          │   update_state)  │
                          └─────────────────┘

  Compliance, decision, and vehicle analysis run IN PARALLEL.
  Only affected matrices are analyzed (conditional edges).
  All converge at remediation.
```

#### Implementation

```python
from strands import Agent, tool
from strands.multiagent.graph import GraphBuilder
from strands.models.bedrock import BedrockModel

def build_recheck_graph(
    tenant_id: str,
    user_id: str,
    package_id: str,
    result_queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> GraphBuilder:
    """Build a Graph for the recheck chain.

    Detect → parallel analysis (conditional) → remediate.
    Returns a built Graph ready for invoke_async().
    """
    model = BedrockModel("us.anthropic.claude-sonnet-4-20250514")

    # --- Nodes ---
    detect_agent = Agent(
        name="detect",
        model=model,
        system_prompt=(
            f"You are checking package {package_id} for staleness. "
            "Call recheck_compliance to identify what changed. "
            "Return the raw JSON result — do not summarize."
        ),
        tools=[_make_recheck_compliance_tool(tenant_id, result_queue, loop)],
    )

    compliance_agent = Agent(
        name="compliance",
        model=model,
        system_prompt=(
            f"Re-run FAR/DFARS compliance analysis for package {package_id}. "
            "Compare previous status with current rules. Return the diff."
        ),
        tools=[_make_reanalyze_compliance_tool(tenant_id, result_queue, loop)],
    )

    decision_agent = Agent(
        name="decision",
        model=model,
        system_prompt=(
            f"Re-evaluate acquisition strategy for package {package_id}. "
            "Check pathway, required docs, approval chain, eval criteria."
        ),
        tools=[_make_reanalyze_decision_tool(tenant_id, result_queue, loop)],
    )

    vehicle_agent = Agent(
        name="vehicle",
        model=model,
        system_prompt=(
            f"Re-score the contract vehicle for package {package_id}. "
            "Check dollar thresholds, scope, security, small business mandates."
        ),
        tools=[_make_reanalyze_viability_tool(tenant_id, result_queue, loop)],
    )

    remediate_agent = Agent(
        name="remediate",
        model=model,
        system_prompt=(
            f"Based on the analysis from previous nodes, determine which documents "
            f"need regeneration for package {package_id}. "
            "List affected doc_types and recommend incremental vs full mode. "
            "Do NOT call regenerate_package_docs yet — present findings first."
        ),
        tools=[],  # No tools — just synthesizes the analysis
    )

    # --- Condition functions ---
    def _parse_detect_result(state) -> dict:
        """Extract the detect node's JSON result."""
        detect_result = state.results.get("detect")
        if not detect_result or not detect_result.result:
            return {}
        try:
            text = str(detect_result.result)
            import json as _json
            return _json.loads(text)
        except Exception:
            return {}

    def compliance_affected(state):
        r = _parse_detect_result(state)
        return r.get("matrices_affected", {}).get("compliance", False)

    def decision_affected(state):
        r = _parse_detect_result(state)
        return r.get("matrices_affected", {}).get("decision", False)

    def vehicle_affected(state):
        r = _parse_detect_result(state)
        return r.get("matrices_affected", {}).get("vehicle", False)

    # --- Build Graph ---
    builder = GraphBuilder()

    builder.add_node(detect_agent, "detect")
    builder.add_node(compliance_agent, "compliance")
    builder.add_node(decision_agent, "decision")
    builder.add_node(vehicle_agent, "vehicle")
    builder.add_node(remediate_agent, "remediate")

    # Conditional edges — only analyze affected matrices
    builder.add_edge("detect", "compliance", condition=compliance_affected)
    builder.add_edge("detect", "decision", condition=decision_affected)
    builder.add_edge("detect", "vehicle", condition=vehicle_affected)

    # All analysis converges to remediation
    builder.add_edge("compliance", "remediate")
    builder.add_edge("decision", "remediate")
    builder.add_edge("vehicle", "remediate")

    # Also connect detect directly to remediate
    # (in case no matrices were affected, remediate still runs)
    builder.add_edge("detect", "remediate")

    builder.set_entry_point("detect")

    return builder.build()
```

#### Supervisor Integration

The supervisor doesn't call recheck tools individually. Instead, it calls a single `run_recheck` tool that executes the graph:

```python
@tool(name="run_recheck")
def run_recheck(tool_context: ToolContext, package_id: str) -> str:
    """Run the full recheck chain for a package.

    Detects what changed, analyzes affected matrices IN PARALLEL,
    and presents findings for user review before any regeneration.

    Args:
        package_id: The acquisition package to recheck

    Returns:
        JSON with detection results, analysis from each affected matrix,
        and remediation recommendations.
    """
    graph = build_recheck_graph(
        tenant_id=tenant_id,
        user_id=user_id,
        package_id=package_id,
        result_queue=result_queue,
        loop=loop,
    )

    # Execute graph (blocking — Strands handles the async internally)
    result = asyncio.run_coroutine_threadsafe(
        graph.invoke_async(f"Recheck package {package_id}"),
        loop,
    ).result(timeout=120)

    # Aggregate results from all nodes
    findings = {
        "status": result.status.value,
        "nodes_executed": [n.node_id for n in result.execution_order],
        "detection": _extract_node_text(result, "detect"),
        "compliance_analysis": _extract_node_text(result, "compliance"),
        "decision_analysis": _extract_node_text(result, "decision"),
        "vehicle_analysis": _extract_node_text(result, "vehicle"),
        "remediation_recommendation": _extract_node_text(result, "remediate"),
        "metrics": {
            "total_tokens": result.accumulated_usage.get("totalTokens", 0),
            "latency_ms": result.accumulated_metrics.get("latencyMs", 0),
        },
    }

    _emit_tool_result("run_recheck", json.dumps(findings), result_queue, loop)
    return json.dumps(findings)
```

#### Benefits of Graph vs Serial Chain

| Aspect | Serial (current plan) | Graph-based |
|--------|----------------------|-------------|
| **Execution** | Sequential: detect → compliance → decision → vehicle → remediate | Parallel: detect → [compliance ‖ decision ‖ vehicle] → remediate |
| **Speed** | 5 sequential LLM calls (~15-25s) | 1 detect + 3 parallel + 1 remediate = **3 sequential calls (~9-15s)** |
| **Conditional** | Agent decides which to call (may skip or call wrong ones) | Graph edges enforce conditions — only affected matrices run |
| **Metrics** | Manual token tracking | `result.accumulated_usage` tracks tokens across all nodes |
| **Resilience** | Agent may abandon chain mid-way | Graph persists state; can resume from failed node |
| **Streaming** | SSE events from single agent | `multiagent_node_start/stop/handoff` events for real-time progress |
| **Cost** | All 5 tools always invoked | Only affected branches execute — saves tokens on clean packages |

#### Frontend Streaming Events

The Graph emits structured events that our SSE pipeline can forward:

```python
async for event in graph.stream_async(task):
    if event.get("type") == "multiagent_node_start":
        # → SSE: {"type": "recheck_progress", "node": "compliance", "status": "started"}
    elif event.get("type") == "multiagent_node_stop":
        # → SSE: {"type": "recheck_progress", "node": "compliance", "status": "completed"}
    elif event.get("type") == "multiagent_handoff":
        # → SSE: {"type": "recheck_progress", "from": ["detect"], "to": ["compliance","decision"]}
```

This enables a real-time progress UI in the RecheckBanner component.

### 12.6 DynamoDBSessionRepository (custom, ~100 lines)

Implements Strands' `SessionRepository` interface to store state in our existing `eagle` DynamoDB table:

```python
class DynamoDBSessionRepository(SessionRepository):
    """Store Strands agent state in DynamoDB eagle table."""

    def __init__(self, table_name: str = "eagle"):
        self.table = boto3.resource("dynamodb").Table(table_name)

    def save_session(self, session_id: str, agent_id: str, state: dict, messages: list) -> None:
        self.table.put_item(Item={
            "PK": f"STATE#{session_id}",
            "SK": f"STATE#{agent_id}",
            "state": json.dumps(state),
            "message_count": len(messages),
            "updated_at": datetime.utcnow().isoformat(),
        })
        # Messages stored separately as MSG# (existing pattern)

    def load_session(self, session_id: str, agent_id: str) -> tuple[dict, list] | None:
        resp = self.table.get_item(Key={
            "PK": f"STATE#{session_id}",
            "SK": f"STATE#{agent_id}",
        })
        item = resp.get("Item")
        if not item:
            return None
        return json.loads(item["state"]), []  # Messages loaded separately

    def session_exists(self, session_id: str, agent_id: str) -> bool:
        resp = self.table.get_item(
            Key={"PK": f"STATE#{session_id}", "SK": f"STATE#{agent_id}"},
            ProjectionExpression="PK",
        )
        return "Item" in resp

    def delete_session(self, session_id: str, agent_id: str) -> None:
        self.table.delete_item(Key={
            "PK": f"STATE#{session_id}",
            "SK": f"STATE#{agent_id}",
        })
```

### 12.7 Agent Construction — Complete Picture

```python
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.session import RepositorySessionManager
from strands.vended_plugins.skills import AgentSkills

# 1. Load skills via native plugin
skills_plugin = AgentSkills(
    skills=["./eagle-plugin/skills/", "./eagle-plugin/agents/"],
    state_key="eagle_skills",
)

# 2. Load user state to determine phase
state = state_store.get_state(tenant_id, user_id)

# 3. Resolve phase-appropriate tools
phase_tools = _resolve_phase_tools(state, TOOL_FACTORIES, result_queue, loop)

# 4. Construct agent with minimal tool set + plugin
supervisor = Agent(
    model=BedrockModel("us.anthropic.claude-sonnet-4-20250514"),
    system_prompt=build_supervisor_prompt(tenant_id, user_id, tier, state),
    plugins=[skills_plugin],
    tools=phase_tools,  # Core (~8) + phase-specific (~3-5) = ~11-13 total
    session_manager=RepositorySessionManager(
        session_id=f"{tenant_id}#{user_id}#{session_id}",
        repository=DynamoDBSessionRepository(table_name="eagle"),
    ),
    agent_id="supervisor",
    state={},  # Auto-hydrated from DynamoDB by SessionManager
)

# Turn start: Strands auto-loads agent.state from DynamoDB
# AgentSkills injects <available_skills> XML into system prompt
# Phase tools are pre-registered based on STATE#current
# Agent can call load_tools() to add more tools mid-turn
# Agent can call skills() to load full skill instructions
# Turn end: Strands auto-persists agent.state to DynamoDB
```

### 12.8 Interleaved Text + Tool Calls (confirmed from source)

From `strands/event_loop/event_loop.py` lines 179-195 and 532-535:

```
event_loop_cycle():
  1. Model streams text + tool_use blocks  → SSE "text" events to user
  2. stop_reason="tool_use"               → execute tools
  3. _handle_tool_execution()             → yields tool results
  4. recurse_event_loop()                 → BACK TO STEP 1
     → model sees tool results
     → generates MORE text              → SSE "text" events to user
     → optionally requests more tools
  5. stop_reason="end_turn"              → done
```

The user sees natural narration between every tool call. No custom streaming work needed.

### 12.9 Alvee's Workflow Mapping to Unified State

| Alvee's pattern | His code | Unified equivalent |
|----------------|----------|-------------------|
| `_exec_intake_workflow(action="start")` | Creates `/tmp/` JSON file | `update_state(state_type="package_created")` → writes to `agent.state.packages[]` |
| `_exec_intake_workflow(action="advance")` | `stages_completed[]` append | `update_state(state_type="phase_change")` + `decision_recorded` |
| `_exec_intake_workflow(action="status")` | Reads `/tmp/` file, builds progress bar | Agent reads `agent.state` directly — no tool needed |
| `_exec_intake_workflow(action="complete")` | Sets `status="submitted"` | `update_state(state_type="phase_change", phase="review")` |
| `_exec_create_document()` | Generates markdown, uploads to S3 | Keep as-is + add `update_state(state_type="document_ready")` after |
| `get_intake_status()` | Scans S3 for existing docs | `get_package_checklist` reads from `agent.state` (faster, no S3 scan) |
| `WORKFLOW_STAGES[]` | Fixed 4-stage array | `packages[].decisions[]` + `phase` (more flexible, auditable) |
| "Changelog" in doc headers | Just a markdown timestamp line | Unrelated — our `CHANGELOG#` is tenant-scoped KB/matrix tracking |

---

## 13. Frontend Wiring — Complete Integration

### 13.1 Current SSE → UI Pipeline (preserved)

```
Backend: update_state tool writes to agent.state + pushes to result_queue
  ↓
stream_protocol.py:142 → write_metadata(queue, payload)
  ↓
SSE wire: data: {"type":"metadata","metadata":{...}}
  ↓
use-agent-stream.ts:418 → options.onMetadata?.(event.metadata)
  ↓
simple-chat-interface.tsx:383 → onMetadata: handleMetadata
  ↓
use-package-state.ts:61 → handleMetadata(metadata) switch on state_type
  ↓
React re-render → ChecklistPanel, compliance alerts, phase badges
```

**Critical wiring point**: `simple-chat-interface.tsx:383` — `onMetadata: handleMetadata`
This single line connects the entire pipeline. All new state_types flow through this unchanged.

### 13.2 New State Types to Add to `usePackageState`

Current `handleMetadata` handles 4 state_types. Expand to 16:

```typescript
// client/hooks/use-package-state.ts — EXPANDED

interface PackageState {
  // Existing (keep)
  packageId: string | null;
  phase: string | null;
  previousPhase: string | null;
  checklist: PackageChecklist | null;
  progressPct: number;
  lastDocumentType: string | null;
  complianceAlerts: ComplianceAlert[];

  // NEW — decisions audit trail
  decisions: Decision[];

  // NEW — vehicle selection
  contractVehicle: string | null;
  vehicleRationale: string | null;

  // NEW — documents with version tracking
  documents: PackageDocument[];

  // NEW — approval chain
  approvals: ApprovalStep[];

  // NEW — intake form data
  intakeData: IntakeData | null;

  // NEW — uploaded user documents
  uploadedDocuments: UploadedDocument[];

  // NEW — recheck status
  needsRecheck: boolean;
  recheckReason: string | null;

  // NEW — workspace context
  workspace: WorkspaceInfo | null;

  // NEW — usage/tier warning
  usageWarning: UsageWarning | null;
}

// handleMetadata switch cases to ADD:
switch (stateType) {
  // ... existing 4 cases ...

  case 'package_created':
    next.packageId = metadata.package_id;
    next.phase = 'intake';
    next.checklist = { required: metadata.required_documents, completed: [], missing: metadata.required_documents, complete: false };
    next.progressPct = 0;
    break;

  case 'decision_recorded':
    next.decisions = [...prev.decisions, {
      questionId: metadata.question_id,
      question: metadata.question,
      answer: metadata.answer,
      agentRecommendation: metadata.agent_recommendation,
      answeredAt: new Date().toISOString(),
    }];
    break;

  case 'vehicle_selected':
    next.contractVehicle = metadata.contract_vehicle;
    next.vehicleRationale = metadata.vehicle_rationale;
    break;

  case 'approval_update':
    next.approvals = metadata.approvals;
    break;

  case 'upload_linked':
    next.uploadedDocuments = [...prev.uploadedDocuments, metadata.document];
    break;

  case 'intake_updated':
    next.intakeData = { ...prev.intakeData, ...metadata.intake_data };
    break;

  case 'compliance_rechecked':
    next.needsRecheck = false;
    next.recheckReason = null;
    next.complianceAlerts = metadata.compliance || prev.complianceAlerts;
    break;

  case 'workspace_switched':
    next.workspace = metadata.workspace;
    break;

  case 'usage_warning':
    next.usageWarning = metadata.warning;
    break;
}
```

### 13.3 New Frontend Components

| Component | File | Purpose |
|-----------|------|---------|
| `DecisionTrail` | `client/components/chat-simple/decision-trail.tsx` | Shows Q&A history that shaped the package |
| `VehicleBadge` | `client/components/chat-simple/vehicle-badge.tsx` | Shows selected vehicle + rationale tooltip |
| `ApprovalChain` | `client/components/chat-simple/approval-chain.tsx` | Shows approval steps with status badges |
| `RecheckBanner` | `client/components/chat-simple/recheck-banner.tsx` | Yellow banner when `needsRecheck=true` |
| `ComplianceDiff` | `client/components/chat-simple/compliance-diff.tsx` | Before/after compliance comparison |
| `UploadedDocsList` | `client/components/chat-simple/uploaded-docs-list.tsx` | User uploads linked to package |

### 13.4 Expanded ChecklistPanel

```typescript
// client/components/chat-simple/checklist-panel.tsx — EXPANDED

<ChecklistPanel state={packageState}>
  {/* Existing */}
  <PackageHeader packageId={packageId} phase={phase} />
  <ProgressBar pct={progressPct} />
  <DocumentChecklist checklist={checklist} />
  <ComplianceAlerts alerts={complianceAlerts} />

  {/* NEW sections */}
  {needsRecheck && <RecheckBanner reason={recheckReason} />}
  {contractVehicle && <VehicleBadge vehicle={contractVehicle} rationale={vehicleRationale} />}
  {approvals.length > 0 && <ApprovalChain steps={approvals} />}
  {decisions.length > 0 && <DecisionTrail decisions={decisions} />}
  {uploadedDocuments.length > 0 && <UploadedDocsList docs={uploadedDocuments} />}
</ChecklistPanel>
```

### 13.5 Initial State Hydration (page load)

```typescript
// client/components/chat-simple/simple-chat-interface.tsx — NEW

useEffect(() => {
  // Hydrate state from backend on mount (in case SSE events were missed)
  async function hydrateState() {
    const token = await getToken();
    const res = await fetch('/api/state', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const state = await res.json();
      if (state.active_package_id) {
        // Replay the state into usePackageState
        handleMetadata({
          state_type: 'full_hydration',
          ...state.packages.find(p => p.package_id === state.active_package_id),
        });
      }
    }
  }
  hydrateState();
}, [currentSessionId]);
```

### 13.6 Backend Endpoint for Hydration

```python
# server/app/main.py — NEW

@app.get("/api/state")
async def get_user_state(
    tenant_id: str = Depends(get_tenant_id),
    user_id: str = Depends(get_user_id),
):
    """Return the current user state for frontend hydration."""
    from app.state_store import get_state, assemble_state_from_sources

    state = get_state(tenant_id, user_id)
    if not state:
        # Lazy migration: assemble from existing entities
        state = assemble_state_from_sources(tenant_id, user_id)
    return state
```

---

## 14. Phase-by-Phase Test & Validation Plan

### Phase 1: State Store + update_state Tool

#### Files to create

| File | Purpose |
|------|---------|
| `server/app/state_store.py` | CRUD for `STATE#` in DynamoDB (or `DynamoDBSessionRepository` wrapper) |
| `server/app/changelog_store.py` | CRUD for `CHANGELOG#` entity |
| `server/tests/test_state_store.py` | Unit tests for state CRUD + merge logic |

#### Files to modify

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Expand `_make_update_state_tool()` with 16 state_types, wire `ToolContext.state` |
| `server/app/streaming_routes.py` | Load state at turn start, inject summary into system prompt |
| `server/app/stream_protocol.py` | Ensure `write_metadata()` handles all state_types (no change needed — generic) |
| `server/app/main.py` | Add `GET /api/state` endpoint |

#### Tests: `server/tests/test_state_store.py`

```python
"""Unit tests for state_store.py — STATE# CRUD + merge logic."""

class TestStateStore:
    """DynamoDB state persistence."""

    def test_create_initial_state(self):
        """First access creates STATE# with empty packages[]."""

    def test_get_state_returns_full_schema(self):
        """get_state returns all top-level keys (user, preferences, workspace, packages, etc.)."""

    def test_merge_state_delta_preserves_unmodified_fields(self):
        """Merging {phase: 'drafting'} into existing state keeps all other fields."""

    def test_merge_state_appends_to_decisions(self):
        """state_type=decision_recorded appends to packages[].decisions[] without overwriting."""

    def test_merge_state_updates_checklist(self):
        """state_type=checklist_update replaces checklist object entirely."""

    def test_merge_state_appends_compliance_alert(self):
        """state_type=compliance_alert appends to compliance[], doesn't replace."""

    def test_merge_state_clears_needs_recheck(self):
        """state_type=compliance_rechecked sets needs_recheck=false."""

    def test_write_through_updates_package_entity(self):
        """When packages[].phase changes, PACKAGE# entity is also updated."""

    def test_lazy_migration_assembles_from_sources(self):
        """When STATE# doesn't exist, assembles from PACKAGE#, WORKSPACE#, PREF#, SKILL#, TEMPLATE#."""

    def test_state_item_under_400kb(self):
        """State with 10 packages, each with 8 docs and 10 decisions, stays under 400KB."""


class TestStateStoreDynamoDBKeys:
    """Verify PK/SK/GSI patterns."""

    def test_pk_format(self):
        """PK = STATE#{tenant_id}#{user_id}."""

    def test_sk_format(self):
        """SK = STATE#current."""

    def test_gsi1_pk(self):
        """GSI1PK = TENANT#{tenant_id} for admin queries."""


class TestUpdateStateTool:
    """Test the Strands @tool that writes to agent.state + pushes SSE METADATA."""

    def test_package_created_sets_active_package(self):
        """state_type=package_created adds package to state and sets active_package_id."""

    def test_document_ready_updates_checklist(self):
        """state_type=document_ready updates documents[] and recalculates checklist."""

    def test_phase_change_records_previous(self):
        """state_type=phase_change sets previous_phase before updating phase."""

    def test_decision_recorded_includes_impact(self):
        """state_type=decision_recorded stores question, answer, options, and impact fields."""

    def test_vehicle_selected_sets_rationale(self):
        """state_type=vehicle_selected stores vehicle name + agent rationale."""

    def test_sse_metadata_emitted_for_each_state_type(self):
        """Every state_type results in an SSE METADATA event pushed to result_queue."""

    def test_unknown_state_type_returns_error(self):
        """Invalid state_type returns JSON error, no state modification."""
```

#### Validation commands
```bash
ruff check server/app/state_store.py server/app/changelog_store.py
python -m pytest tests/test_state_store.py -v
```

---

### Phase 2: Changelog + Recheck Detection

#### Files to create

| File | Purpose |
|------|---------|
| `server/tests/test_changelog_store.py` | Unit tests for CHANGELOG# CRUD + package flagging |

#### Files to modify

| File | Change |
|------|--------|
| `server/app/main.py` | Add `update_changelog()` calls to KB review, matrix edit, template endpoints |
| `server/app/strands_agentic_service.py` | Add `recheck_compliance` tool |
| `server/app/tools/contract_matrix.py` | Expose `get_applicable_rules()` for recheck comparison |

#### Tests: `server/tests/test_changelog_store.py`

```python
"""Unit tests for changelog_store.py — CHANGELOG# CRUD + downstream flagging."""

class TestChangelogStore:
    """CHANGELOG# entity persistence."""

    def test_create_changelog_entry(self):
        """Creates CHANGELOG# item with correct PK/SK/TTL."""

    def test_changelog_pk_format(self):
        """PK = CHANGELOG#{tenant_id}."""

    def test_changelog_sk_is_sortable(self):
        """SK = CHANGELOG#{ISO_timestamp}#{change_id} — sorts chronologically."""

    def test_ttl_set_to_90_days(self):
        """TTL = 90 days from creation."""

    def test_list_changelog_since_timestamp(self):
        """Query returns only entries newer than given timestamp."""

    def test_list_changelog_by_entity_type(self):
        """GSI1 query filters by entity_type (knowledge_base, decision_matrix, etc.)."""


class TestDownstreamFlagging:
    """When changelog is created, affected packages get needs_recheck=true."""

    def test_kb_change_flags_active_packages(self):
        """Adding KB document flags all non-closed packages in tenant."""

    def test_matrix_change_flags_matching_pathways(self):
        """Matrix rule for 'full_competition' only flags packages with that pathway."""

    def test_closed_packages_not_flagged(self):
        """Packages with status='closed' are never flagged for recheck."""

    def test_flag_sets_recheck_reason(self):
        """needs_recheck=true includes human-readable reason + change_id."""

    def test_flag_updates_state_entity(self):
        """Both PACKAGE# and STATE# entities get needs_recheck=true."""


class TestRecheckComplianceTool:
    """The recheck_compliance Strands @tool (read-only detection)."""

    def test_returns_no_changes_when_clean(self):
        """Package with no changelog entries since last_compliance_check returns changes_detected=0."""

    def test_detects_kb_change(self):
        """KB document added after last_compliance_check appears in changelog_entries."""

    def test_identifies_affected_matrices(self):
        """KB change → matrices_affected.compliance=true, decision=false, vehicle=false."""

    def test_threshold_change_affects_all_three(self):
        """FAR threshold rule update → all three matrices affected."""

    def test_severity_escalation(self):
        """Multiple changes → severity escalates from info → warning → critical."""
```

#### Tests: `server/tests/test_changelog_integration.py`

```python
"""Integration tests — admin actions trigger changelog + flagging."""

class TestKBReviewApprovalTriggersChangelog:
    """POST /api/admin/kb-review/{id}/approve creates CHANGELOG# + flags packages."""

    def test_approve_creates_changelog_entry(self):
        """Approving KB review writes CHANGELOG# with change_type=kb_document_added."""

    def test_approve_flags_active_packages(self):
        """Approving KB review sets needs_recheck=true on active packages."""

    def test_reject_does_not_create_changelog(self):
        """Rejecting KB review creates no CHANGELOG# entry."""


class TestTemplateUpdateTriggersChangelog:
    """POST /api/templates/{doc_type} creates CHANGELOG# for template changes."""

    def test_template_update_creates_changelog(self):
        """Updating a template writes CHANGELOG# with change_type=template_updated."""
```

#### Validation commands
```bash
ruff check server/app/
python -m pytest tests/test_state_store.py tests/test_changelog_store.py tests/test_changelog_integration.py -v
```

---

### Phase 3: Reanalyze Tools + Graph-Based Recheck Chain

#### Files to create

| File | Purpose |
|------|---------|
| `server/app/tools/decision_matrix.py` | Decision matrix logic — pathway, required docs, approval chain, eval criteria |
| `server/app/tools/viability_matrix.py` | Vehicle viability scoring + alternatives |
| `server/app/recheck_graph.py` | `build_recheck_graph()` — Strands Graph with conditional edges + parallel analysis |
| `server/tests/test_reanalyze_tools.py` | Unit tests for all 3 reanalyze tools |
| `server/tests/test_recheck_graph.py` | Graph integration tests — conditional edges, parallel execution, metrics |

#### Files to modify

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Add `run_recheck` tool (Graph wrapper), register in compliance tool group |
| `server/app/tools/contract_matrix.py` | Add `compare_compliance()` for before/after diff |

#### Tests: `server/tests/test_reanalyze_tools.py`

```python
"""Unit tests for the 3 reanalyze tools — all read-only, no side effects."""

class TestReanalyzeComplianceMatrix:
    """reanalyze_compliance_matrix — FAR/DFARS compliance diff."""

    def test_no_changes_returns_empty_diff(self):
        """When rules haven't changed, changes[] is empty."""

    def test_new_far_rule_detected(self):
        """New FAR rule in matrix appears as current=pending, previous=null."""

    def test_threshold_change_moves_status(self):
        """FAR 15.404 threshold lowered → satisfied→violation for affected package."""

    def test_affected_documents_identified(self):
        """Changed compliance rules map to specific doc_types that need updates."""

    def test_returns_previous_and_current_counts(self):
        """Output includes satisfied/pending/violations counts for before and after."""


class TestReanalyzeDecisionMatrix:
    """reanalyze_decision_matrix — acquisition strategy diff."""

    def test_value_increase_changes_pathway(self):
        """$200K → $600K moves pathway from simplified → full_competition."""

    def test_pathway_change_adds_required_docs(self):
        """full_competition adds sow, market_research, acquisition_plan to required."""

    def test_pathway_change_adds_approval_steps(self):
        """$500K+ triggers HCA review step in approval chain."""

    def test_no_change_returns_changed_false(self):
        """Same value + type → pathway.changed=false, all sections empty."""

    def test_eval_criteria_change_detected(self):
        """New evaluation factor from KB appears in current_factors."""


class TestReanalyzeViabilityMatrix:
    """reanalyze_viability_matrix — vehicle fitness scoring."""

    def test_vehicle_still_viable(self):
        """GSA MAS for $500K IT services → still_viable=true, score > 0.8."""

    def test_vehicle_not_viable_above_ceiling(self):
        """Vehicle with $1M ceiling for $2M acquisition → still_viable=false."""

    def test_alternatives_ranked_by_score(self):
        """When not viable, alternatives sorted by viability_score descending."""

    def test_concerns_include_mitigation(self):
        """Each concern has a mitigation suggestion."""

    def test_score_delta_calculated(self):
        """viability_score.delta = current - previous."""

    def test_security_requirement_change_affects_score(self):
        """Adding FedRAMP requirement lowers score for vehicles without pre-vetted vendors."""
```

#### Tests: `server/tests/test_recheck_graph.py`

```python
"""Integration tests for Graph-based recheck chain."""

class TestRecheckGraphTopology:
    """Verify Graph structure — nodes, edges, conditions."""

    def test_graph_has_5_nodes(self):
        """Graph contains detect, compliance, decision, vehicle, remediate."""

    def test_detect_is_entry_point(self):
        """Entry point is the detect node."""

    def test_conditional_edges_from_detect(self):
        """detect → compliance/decision/vehicle edges have condition functions."""

    def test_all_analysis_converges_to_remediate(self):
        """compliance, decision, vehicle all have edges to remediate."""

    def test_detect_has_direct_edge_to_remediate(self):
        """If no matrices affected, detect → remediate still runs."""


class TestRecheckGraphExecution:
    """End-to-end Graph execution with mock tools."""

    def test_only_compliance_affected_runs_one_branch(self):
        """When only compliance matrix changed, decision and vehicle nodes are skipped."""

    def test_all_three_affected_runs_parallel(self):
        """When all matrices affected, compliance/decision/vehicle run in parallel."""

    def test_no_changes_detected_goes_straight_to_remediate(self):
        """Clean package with no changelog → detect + remediate only."""

    def test_graph_metrics_accumulated(self):
        """result.accumulated_usage.totalTokens sums across all executed nodes."""

    def test_graph_execution_order_is_correct(self):
        """detect is always first, remediate is always last."""

    def test_run_recheck_tool_returns_aggregated_findings(self):
        """run_recheck tool JSON includes detection, analysis, and remediation sections."""
```

#### Validation commands
```bash
ruff check server/app/tools/ server/app/recheck_graph.py
python -m pytest tests/test_reanalyze_tools.py tests/test_recheck_graph.py -v
```

---

### Phase 4: Regeneration Tool + AgentSkills Plugin + Dynamic Tools

#### Files to create

| File | Purpose |
|------|---------|
| `server/tests/test_regenerate_docs.py` | Unit tests for incremental + full regeneration |
| `server/tests/test_dynamic_tools.py` | Tests for load_tools, _resolve_phase_tools, AgentSkills plugin |

#### Files to modify

| File | Change |
|------|--------|
| `server/app/strands_agentic_service.py` | Replace `list_skills`/`load_skill` with AgentSkills plugin, add `load_tools` meta-tool, add `regenerate_package_docs`, add `_resolve_phase_tools()`, update `build_supervisor_prompt()` |
| `server/app/document_service.py` | Add `regenerate_document()` method (incremental + full modes) |
| `eagle-plugin/agents/supervisor/agent.md` | Add state management, recheck protocol, progressive disclosure instructions |

#### Tests: `server/tests/test_regenerate_docs.py`

```python
"""Unit tests for regenerate_package_docs tool."""

class TestIncrementalRegeneration:
    """mode='incremental' — patch existing documents."""

    def test_adds_section_to_existing_doc(self):
        """Incremental mode loads SOW v2 from S3, adds Section 8, saves as v3."""

    def test_preserves_unmodified_sections(self):
        """Sections not in changes_to_apply are preserved verbatim."""

    def test_increments_version(self):
        """New document version = previous + 1."""

    def test_supersedes_prior_version(self):
        """Prior version status set to 'superseded' in DOCUMENT#."""

    def test_updates_s3_key_with_new_version(self):
        """S3 key follows pattern: eagle/{tenant}/packages/{pkg}/{type}/v{N}/{filename}.md."""

    def test_content_hash_changes(self):
        """New version has different content_hash than prior."""


class TestFullRegeneration:
    """mode='full' — regenerate from scratch using template + KB + state."""

    def test_uses_latest_template(self):
        """Full mode fetches template via 4-layer resolution chain."""

    def test_incorporates_kb_content(self):
        """Full mode calls knowledge_search + knowledge_fetch for relevant KB docs."""

    def test_uses_package_state_for_context(self):
        """Full mode reads intake_data, decisions, compliance from agent.state."""

    def test_new_documents_needed_returned(self):
        """If decision_matrix added a required doc_type, it appears in new_documents_needed."""


class TestRegenerationGuardrails:
    """Safety checks before regenerating."""

    def test_requires_user_confirmation(self):
        """Tool returns error if called without prior user confirmation (via system prompt rule)."""

    def test_skips_finalized_documents(self):
        """Documents with status='final' are not regenerated — appear in skipped[]."""

    def test_skips_nonexistent_documents(self):
        """Doc types with no prior version appear in new_documents_needed, not regenerated."""
```

#### Tests: `server/tests/test_dynamic_tools.py`

```python
"""Tests for state-driven dynamic tool registration and AgentSkills plugin."""

class TestResolvePhaseTools:
    """_resolve_phase_tools returns correct tools based on state."""

    def test_no_state_returns_core_plus_intake(self):
        """New user with no state gets core (~8) + intake (3) tools."""

    def test_intake_phase_returns_intake_tools(self):
        """Active package in intake phase → core + intake tools."""

    def test_planning_phase_returns_planning_and_drafting(self):
        """Planning phase → core + planning + drafting tools."""

    def test_drafting_phase_returns_drafting_tools(self):
        """Drafting phase → core + drafting tools."""

    def test_review_phase_returns_review_tools(self):
        """Review phase → core + review tools."""

    def test_needs_recheck_adds_compliance_group(self):
        """Package with needs_recheck=true → compliance group auto-loaded regardless of phase."""

    def test_no_active_package_defaults_to_intake(self):
        """State exists but no active_package_id → intake tools."""

    def test_tool_count_under_15(self):
        """No auto-resolution exceeds 15 tools (core + largest group)."""


class TestLoadToolsMetaTool:
    """The load_tools Strands @tool for dynamic tool registration."""

    def test_load_drafting_registers_create_document(self):
        """load_tools('drafting') → create_document appears in registry."""

    def test_load_compliance_registers_recheck_chain(self):
        """load_tools('compliance') → all 5 recheck tools registered."""

    def test_load_specialist_registers_single_agent(self):
        """load_tools('specialist:legal-counsel') → legal_counsel tool registered."""

    def test_load_all_specialists_registers_all_14(self):
        """load_tools('all_specialists') → all SKILL_AGENT_REGISTRY entries registered."""

    def test_duplicate_load_is_idempotent(self):
        """Calling load_tools('drafting') twice doesn't error (supports_hot_reload=True)."""

    def test_loaded_tools_visible_on_next_turn(self):
        """After register_tool(), get_all_tool_specs() includes the new tool."""

    def test_unknown_category_returns_error(self):
        """load_tools('nonexistent') returns JSON error."""


class TestPhaseChangeAutoRegistration:
    """update_state(phase_change) auto-registers new phase tools."""

    def test_phase_change_to_drafting_registers_create_document(self):
        """After phase_change to 'drafting', create_document is in registry."""

    def test_phase_change_to_review_registers_compliance_tools(self):
        """After phase_change to 'review', recheck tools are in registry."""


class TestAgentSkillsIntegration:
    """AgentSkills plugin integration with EAGLE skills."""

    def test_plugin_loads_all_eagle_skills(self):
        """AgentSkills loads skills from eagle-plugin/skills/ and agents/."""

    def test_skills_xml_injected_in_system_prompt(self):
        """BeforeInvocationEvent injects <available_skills> XML."""

    def test_skills_tool_returns_full_instructions(self):
        """Calling skills('oa-intake') returns full SKILL.md body."""

    def test_activated_skills_tracked_in_state(self):
        """agent.state['eagle_skills']['activated_skills'] tracks activations."""

    def test_list_skills_and_load_skill_removed(self):
        """Old list_skills/load_skill tools are NOT in the registry."""
```

#### Tests: `server/tests/test_system_prompt_state.py`

```python
"""Verify state is injected into system prompt correctly."""

class TestStateInjection:
    """State summary appears in system prompt at turn start."""

    def test_active_package_summary_in_prompt(self):
        """When active_package_id is set, prompt includes phase, pathway, checklist summary."""

    def test_no_package_shows_none(self):
        """When no active package, prompt shows 'Active Package: none'."""

    def test_needs_recheck_flag_in_prompt(self):
        """When needs_recheck=true, prompt includes recheck reason."""

    def test_vehicle_shown_in_prompt(self):
        """When vehicle is selected, prompt includes vehicle name."""

    def test_compliance_counts_in_prompt(self):
        """Prompt shows 'N satisfied, N pending, N violations'."""
```

#### Validation commands
```bash
ruff check server/app/
python -m pytest tests/test_regenerate_docs.py tests/test_system_prompt_state.py -v
npx tsc --noEmit
```

---

### Phase 5: Frontend Integration

#### Files to create

| File | Purpose |
|------|---------|
| `client/components/chat-simple/decision-trail.tsx` | Decision Q&A audit trail component |
| `client/components/chat-simple/vehicle-badge.tsx` | Vehicle selection badge with tooltip |
| `client/components/chat-simple/approval-chain.tsx` | Approval steps with status |
| `client/components/chat-simple/recheck-banner.tsx` | Yellow banner for stale packages |
| `client/components/chat-simple/compliance-diff.tsx` | Before/after compliance comparison |
| `client/components/chat-simple/uploaded-docs-list.tsx` | User uploads linked to package |
| `client/tests/validate-unified-state.spec.ts` | Playwright E2E for state flow |

#### Files to modify

| File | Change |
|------|--------|
| `client/hooks/use-package-state.ts` | Expand `PackageState` interface + `handleMetadata` switch to 16 cases |
| `client/components/chat-simple/checklist-panel.tsx` | Add new sections (vehicle, approvals, decisions, uploads, recheck) |
| `client/components/chat-simple/simple-chat-interface.tsx` | Add `GET /api/state` hydration on mount, pass expanded state |
| `client/lib/document-store.ts` | Add `syncWithBackendState()` to reconcile localStorage with STATE# |
| `client/types/stream.ts` | Add new interfaces (`Decision`, `ApprovalStep`, `UploadedDocument`, etc.) |

#### Tests: `client/tests/validate-unified-state.spec.ts`

```typescript
/**
 * E2E: Unified state schema — SSE metadata flows to UI components.
 *
 * These tests verify that state_type events from the backend
 * correctly update the checklist panel and related UI.
 */

test.describe('Unified State Schema — Frontend Integration', () => {

  test('package_created shows checklist panel', async ({ page }) => {
    // Send intake message → wait for checklist panel to appear
    // Verify: packageId shown, phase='intake', 0% progress
  });

  test('document_ready ticks checklist item', async ({ page }) => {
    // Trigger SOW generation → wait for checkmark on SOW
    // Verify: progress updates, SOW shows version badge
  });

  test('phase_change updates phase badge', async ({ page }) => {
    // Advance from intake → drafting
    // Verify: phase badge text changes, previousPhase stored
  });

  test('compliance_alert shows warning', async ({ page }) => {
    // Trigger compliance check with pending items
    // Verify: warning badges appear in alerts section
  });

  test('vehicle_selected shows vehicle badge', async ({ page }) => {
    // Select GSA MAS → verify badge appears with tooltip
  });

  test('decision_recorded shows in trail', async ({ page }) => {
    // Answer intake question → verify decision appears in trail
    // Verify: question, answer, agent recommendation shown
  });

  test('recheck banner appears when needs_recheck', async ({ page }) => {
    // Simulate stale package → verify yellow banner
    // Verify: banner shows recheck reason text
  });

  test('state hydration on page reload', async ({ page }) => {
    // Create package → reload page → verify checklist panel reappears
    // Verify: GET /api/state called, state hydrated correctly
  });

  test('multiple packages in one session', async ({ page }) => {
    // Create 2 packages → switch active → verify checklist updates
  });

  test('SSE reconnect hydrates full state', async ({ page }) => {
    // Simulate network drop → reconnect → verify state intact
  });
});
```

#### Tests: `client/tests/validate-state-types.spec.ts`

```typescript
/**
 * Schema validation for all 16 state_types.
 * Sends mock SSE events and verifies usePackageState handles them.
 */

test.describe('State Type Schema Validation', () => {

  const STATE_TYPES = [
    'package_created', 'document_ready', 'phase_change', 'checklist_update',
    'compliance_alert', 'vehicle_selected', 'approval_update', 'upload_linked',
    'template_selected', 'intake_updated', 'decision_recorded',
    'preferences_changed', 'workspace_switched', 'skill_created',
    'compliance_rechecked', 'usage_warning',
  ];

  for (const stateType of STATE_TYPES) {
    test(`handles ${stateType} without error`, async ({ page }) => {
      // Inject mock SSE event with state_type
      // Verify: no console errors, UI doesn't crash
    });
  }

  test('unknown state_type is silently ignored', async ({ page }) => {
    // Send state_type='nonexistent' → verify no crash, no state change
  });
});
```

#### Validation commands
```bash
npx tsc --noEmit                                           # L1 — TypeScript
npx playwright test validate-unified-state.spec.ts         # L3 — E2E
npx playwright test validate-state-types.spec.ts           # L3 — Schema validation
```

---

### Phase 6: Agentic End-to-End Validation

#### Tests: `client/tests/validate-state-e2e-agentic.spec.ts`

```typescript
/**
 * L3.5 — Agentic validation. Full acquisition flow with real agent responses.
 * Requires: backend running with Bedrock access.
 * Timeout: 3 minutes per test.
 */

test.describe('Agentic State Flow — Full Acquisition', () => {
  test.setTimeout(180_000);

  test('intake → document generation → compliance check', async ({ page }) => {
    // Step 1: Start intake
    // Send: "I need to buy cloud hosting for $500K"
    // Wait for: checklist panel appears, 4 required docs, 0%
    // Verify: package_created metadata received

    // Step 2: Generate SOW
    // Send: "Generate the SOW"
    // Wait for: document card appears, SOW checked in checklist
    // Verify: document_ready + checklist_update metadata received
    // Verify: progress = 25%

    // Step 3: Check compliance
    // Send: "Are we FAR compliant?"
    // Wait for: compliance alerts appear
    // Verify: compliance_alert metadata received
    // Screenshot: full state after compliance check
  });

  test('recheck flow triggers on stale package', async ({ page }) => {
    // Pre-condition: package with needs_recheck=true in DynamoDB
    // Step 1: Start conversation
    // Wait for: agent mentions "changes detected since last session"
    // Wait for: recheck_compliance tool called (visible in activity panel)
    // Verify: agent narrates between tool calls (interleaved text)
    // Verify: compliance_rechecked clears the banner
  });

  test('decision trail records all intake Q&A', async ({ page }) => {
    // Step 1: Start intake
    // Step 2: Answer 4 intake questions (type, value, vehicle, security)
    // Wait for: 4 decisions in trail
    // Verify: each decision has question, answer, impact
    // Verify: vehicle badge shows selected vehicle
  });
});
```

#### Validation commands
```bash
# L3.5 — Requires running backend with AWS credentials
AWS_PROFILE=eagle npx playwright test validate-state-e2e-agentic.spec.ts --project=chromium
```

---

## 15. Validation Matrix — Complete

| Phase | L1 (Lint) | L2 (Unit) | L3 (E2E) | L3.5 (Agentic) | Files |
|-------|-----------|-----------|----------|----------------|-------|
| **1: State Store** | `ruff check state_store.py changelog_store.py` | `test_state_store.py` (13 tests) | — | — | 3 new, 4 modified |
| **2: Changelog + Recheck** | `ruff check server/app/` | `test_changelog_store.py` (11 tests), `test_changelog_integration.py` (3 tests) | — | — | 1 new, 3 modified |
| **3: Reanalyze + Graph** | `ruff check server/app/tools/ recheck_graph.py` | `test_reanalyze_tools.py` (17 tests), `test_recheck_graph.py` (11 tests) | — | — | 4 new, 2 modified |
| **4: Regen + Skills + DynTools** | `ruff check server/app/` + `npx tsc --noEmit` | `test_regenerate_docs.py` (11 tests), `test_dynamic_tools.py` (22 tests), `test_system_prompt_state.py` (5 tests) | — | — | 2 new, 3 modified |
| **5: Frontend** | `npx tsc --noEmit` | — | `validate-unified-state.spec.ts` (10 tests), `validate-state-types.spec.ts` (18 tests) | — | 7 new, 5 modified |
| **6: Agentic E2E** | — | — | — | `validate-state-e2e-agentic.spec.ts` (3 tests) | 1 new |
| **TOTAL** | 5 lint passes | **93 unit tests** | **28 E2E tests** | **3 agentic tests** | 18 new, 17 modified |

### Running All Tests

```bash
# Full validation (all phases)
ruff check server/app/                                                    # L1
npx tsc --noEmit                                                          # L1
python -m pytest tests/test_state_store.py tests/test_changelog_store.py tests/test_changelog_integration.py tests/test_reanalyze_tools.py tests/test_recheck_graph.py tests/test_regenerate_docs.py tests/test_dynamic_tools.py tests/test_system_prompt_state.py -v  # L2
npx playwright test validate-unified-state.spec.ts validate-state-types.spec.ts  # L3
AWS_PROFILE=eagle npx playwright test validate-state-e2e-agentic.spec.ts  # L3.5
```
