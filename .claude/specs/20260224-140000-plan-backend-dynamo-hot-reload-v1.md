# Plan: Backend Hot Reload + DynamoDB Improvements
**Date**: 2026-02-24
**Spec**: `.claude/specs/20260224-140000-plan-backend-dynamo-hot-reload-v1.md`
**Status**: PLAN (awaiting approval) — v3 expanded with PLUGIN# as DynamoDB source of truth

---

## Problem Statement

The EAGLE backend has three interrelated problems:

1. **No live prompt injection** — Agent/skill prompts are bundled into the Docker image via `eagle_skill_constants.py` reading `eagle-plugin/*.md` at startup. Changing any prompt requires a full image rebuild + ECS redeploy (~5–10 min cycle time).

2. **No hot reload path** — Uvicorn runs without `--reload` in ECS. All module-level state (MODEL, SKILL_AGENT_REGISTRY, TIER_BUDGETS) is frozen at container startup.

3. **DynamoDB scan antipatterns** — 4 functions in `session_store.py` use `table.scan()`. The `eagle` table already writes `GSI1PK`/`GSI1SK` on every session item but **the CDK never creates the GSI** — so the index doesn't exist.

4. **Reference data is file-locked** — `thresholds.json`, `far-database.json`, `contract-vehicles.json` are bundled in the Docker image. FAR thresholds change every 2 years and require a container rebuild today.

5. **Templates are file-locked** — SOW, IGCE, AP, Market Research, Justification templates live in `eagle-plugin/data/templates/`. Users cannot customize them without a code change.

6. **The plugin itself is double-stored and not authoritative** — `eagle-plugin/` is bundled in the Docker image AND read from disk at startup by `eagle_skill_constants.py`. There is no single authoritative source. Changes require git commit + image rebuild + ECS redeploy for any content. DynamoDB should be the authoritative runtime source; the bundled files should be bootstrap seeds only.

6. **No user-created skills** — Users cannot define their own mini-agents. The skill registry is plugin-defined and static.

7. **No acquisition package persistence** — The `oa-intake` skill guides users through intake, but completed packages are only in session messages — not addressable, not versionable, not approvable.

---

## Architecture: How Hot Reload Works in ECS (No File Watching)

ECS Fargate containers are immutable. The correct pattern is:

```
Container reads config/prompts/templates from DynamoDB on each request
  └── 60-second in-process TTL cache per ECS task
  └── Admin PUT to DynamoDB → visible to ALL tasks within 60s
  └── POST /api/admin/reload → force-flush cache instantly (all tasks)
```

Update DynamoDB → visible within 60 seconds. **Zero restarts. Zero redeploys.**

---

## User Workspace Isolation Model

Every user operates inside a **workspace** — an isolated environment that defaults to the base PLUGIN# prompts and accumulates only that user's modifications. Changes made in one user's workspace are completely invisible to all other users.

### Resolution Chain (per request, in priority order)

```
For any agent/skill/template/config lookup:

  1. WSPC#{tenant_id}#{user_id}#{workspace_id} / {entity}   ← user workspace override
     (only this user sees this; their personal customization)

  2. PROMPT#{tenant_id} / PROMPT#admin#{agent_name}          ← tenant admin pushes to all users
     (org-wide guardrails; user can't override these unless permitted)

  3. PROMPT#global / PROMPT#{agent_name}                     ← platform admin emergency override

  4. PLUGIN#agents / PLUGIN#{agent_name}                     ← canonical DynamoDB default
     (seeded from eagle-plugin/, hot-editable by platform admin)

  5. bundled eagle-plugin/ on disk                           ← never reached after seed
```

### Key Behaviors

| Behavior | Design |
|---------|--------|
| User modifies supervisor prompt | Stored in `WSPC#{tenant}#{user}#{workspace}` — invisible to others |
| User logs in fresh | Default workspace auto-provisioned, inherits all PLUGIN# defaults (no overrides) |
| Admin patches a prompt | Goes to `PROMPT#{tenant_id}` — pushed to all users (they see it in their workspace) |
| User overrides admin patch | Stored in their WSPC# — their workspace takes priority over the admin layer |
| User switches workspace | Active workspace flag flips; next session loads new workspace's overrides |
| Session is workspace-pinned | Sessions remember which workspace created them; switching workspaces doesn't break in-flight sessions |
| User resets to default | Delete their WSPC# overrides for that agent — falls through to PLUGIN# base |
| Admin reviews user workspace | Read-only WSPC# access for compliance audit |

---

## Complete DynamoDB Entity Map

The `eagle` single-table design is extended with these prefixes. Existing `SESSION#`, `MSG#`, `USAGE#`, `COST#`, `SUB#` are unchanged.

```
Entity          PK                                        SK
────────────────────────────────────────────────────────────────────────────────────────
PLUGIN          PLUGIN#{entity_type}                      PLUGIN#{name}
WORKSPACE       WORKSPACE#{tenant_id}#{user_id}           WORKSPACE#{workspace_id}
WSPC            WSPC#{tenant_id}#{user_id}#{workspace_id} {entity_type}#{name}
PROMPT          PROMPT#{tenant_id}                        PROMPT#admin#{agent_name}
PROMPT (global) PROMPT#global                             PROMPT#{agent_name}
CONFIG          CONFIG#global                             CONFIG#{key}
TEMPLATE        TEMPLATE#{tenant_id}                      TEMPLATE#{doc_type}#{user_id}
SKILL           SKILL#{tenant_id}                         SKILL#{skill_id}
PACKAGE         PACKAGE#{tenant_id}                       PACKAGE#{package_id}
DOCUMENT        DOCUMENT#{tenant_id}                      DOCUMENT#{package_id}#{doc_type}
REFDATA         REFDATA#global                            REFDATA#{dataset}#{version}
AUDIT           AUDIT#{tenant_id}                         AUDIT#{ISO_timestamp}#{entity_type}
PREF            PREF#{tenant_id}                          PREF#{user_id}
APPROVAL        APPROVAL#{tenant_id}                      APPROVAL#{package_id}#{step}
FAVORITE        FAVORITE#{tenant_id}                      FAVORITE#{user_id}#{target_id}
```

### GSI Extensions Required (core-stack.ts)

| GSI | PK Attribute | SK Attribute | Purpose |
|-----|-------------|-------------|---------|
| GSI1 | `GSI1PK` | `GSI1SK` | Tenant-level session/workspace listing |
| GSI2 | `GSI2PK` | `GSI2SK` | Tier queries + skill listing by status |

---

## Entity Specifications

---

### `PLUGIN#` — Canonical Plugin Content (Source of Truth) *(new, highest priority)*

`eagle-plugin/` in git becomes the **bootstrap seed only**. DynamoDB `PLUGIN#` is the authoritative runtime content. `eagle_skill_constants.py` becomes a seeder that populates DynamoDB on first start (or when the manifest version is stale), then steps aside.

```
PK:  PLUGIN#{entity_type}
SK:  PLUGIN#{name}

entity_type values: "agents" | "skills" | "templates" | "refdata" | "tools" | "commands" | "manifest"

Attributes:
  entity_type:   str       — mirrors PK segment
  name:          str       — "supervisor", "oa-intake", "sow", "thresholds", etc.
  content:       str       — raw content (markdown for agents/skills/templates, JSON for refdata/tools)
  content_type:  str       — "markdown" | "json"
  metadata:      dict      — parsed YAML frontmatter (for agents/skills: name, description, triggers, tools, model)
  version:       int       — monotonically incrementing; 1 = initial seed
  checksum:      str       — SHA256 of content (integrity check; detect drift from bundled files)
  seeded_from:   str       — "bundled" | "admin_api" | "sync"
  is_active:     bool      — false disables without deleting
  created_at:    ISO
  updated_at:    ISO
  ttl:           epoch     — none for system content (never auto-expire)
```

**Bootstrap logic** (runs in `plugin_store.py` at app startup):
```python
def ensure_plugin_seeded():
    """Seed DynamoDB from bundled eagle-plugin/ if not present or version is stale."""
    manifest = get_plugin_item("manifest", "manifest")
    if manifest and manifest.get("version") == BUNDLED_PLUGIN_VERSION:
        return  # DynamoDB is current — skip seeding

    # Seed all entity types from PLUGIN_CONTENTS (eagle_skill_constants.py)
    for agent_name, entry in AGENTS.items():
        put_plugin_item("agents", agent_name, entry["body"], entry.get("metadata", {}))
    for skill_name, entry in SKILLS.items():
        put_plugin_item("skills", skill_name, entry["body"], entry.get("metadata", {}))
    for tmpl_name, content in TEMPLATES.items():
        put_plugin_item("templates", tmpl_name, content)
    put_plugin_item("refdata", "thresholds", json.dumps(THRESHOLDS))
    put_plugin_item("refdata", "far-database", json.dumps(FAR_DATABASE))
    put_plugin_item("refdata", "contract-vehicles", json.dumps(CONTRACT_VEHICLES))
    put_plugin_item("tools", "definitions", json.dumps(TOOL_DEFINITIONS))
    put_plugin_item("manifest", "manifest", json.dumps({"version": BUNDLED_PLUGIN_VERSION}))
```

**Resolution chain on every request** (priority order):
```
1. PROMPT#{tenant_id}#{agent_name}   → tenant-specific override
2. PROMPT#global#{agent_name}        → system-wide admin override
3. PLUGIN#agents#{agent_name}        → canonical DynamoDB content  ← authoritative
4. [bundled eagle-plugin/ on disk]   → never reached after seeding
```

**Admin API for plugin management**:
```
GET    /api/admin/plugin/status                   → version, seed date, entity counts, drift report
POST   /api/admin/plugin/sync                     → force reseed from bundled files (resets to factory)
GET    /api/admin/plugin/{entity_type}            → list all entities of a type
GET    /api/admin/plugin/{entity_type}/{name}     → get entity content
PUT    /api/admin/plugin/{entity_type}/{name}     → update entity (writes AUDIT# entry)
POST   /api/admin/plugin/{entity_type}/{name}/diff → compare DynamoDB vs bundled file
```

**`plugin.json` manifest in DynamoDB**: The `agents`, `skills`, `commands`, `capabilities` fields from `plugin.json` are stored as `PLUGIN#manifest/PLUGIN#manifest`. This drives which agents/skills are active — replacing the hardcoded `_load_plugin_config()` file read in `sdk_agentic_service.py`.

---

### `WORKSPACE#` — User Workspace Registry *(new)*

Every user has one or more named workspaces. A default workspace is auto-provisioned on first login/session creation. Only one workspace is `is_active` at a time per user.

```
PK:  WORKSPACE#{tenant_id}#{user_id}
SK:  WORKSPACE#{workspace_id}

Attributes:
  workspace_id:       str       — uuid4
  user_id:            str
  tenant_id:          str
  name:               str       — "Default", "Legal Review Mode", "Quick Intake"
  description:        str
  is_active:          bool      — the currently loaded workspace for this user
  is_default:         bool      — true = auto-provisioned on first login, cannot be deleted
  base_workspace_id:  str       — if forked from another workspace (copy-on-write)
  visibility:         str       — "private" | "shareable" (others can copy, not edit)
  override_count:     int       — how many WSPC# overrides are stored (informational)
  created_at:         ISO
  updated_at:         ISO
  GSI1PK:             TENANT#{tenant_id}
  GSI1SK:             WORKSPACE#{user_id}#{workspace_id}
```

**Auto-provisioning**: When a new session is created for a user with no workspace records, `workspace_store.get_or_create_default()` creates a `Default` workspace (`is_default=true`, `is_active=true`) with zero overrides. This is transparent — the user starts with clean base prompts.

**Multiple workspaces**: Users can create named workspaces for different contexts (e.g., one tuned for legal review with a modified legal-counsel prompt, one for fast micro-purchases). Switching workspace changes which WSPC# overrides are resolved.

**Session pinning**: When a session is created, the active `workspace_id` is stored on the session record. That session always resolves overrides from its pinned workspace — switching workspaces mid-conversation doesn't affect active sessions.

---

### `WSPC#` — User Workspace Content Overrides *(new, most specific layer)*

Stores every per-user, per-workspace override. This is the isolation unit — reads from this prefix are scoped to exactly one user's one workspace.

```
PK:  WSPC#{tenant_id}#{user_id}#{workspace_id}
SK:  {entity_type}#{name}

entity_type values: "AGENT" | "SKILL" | "TEMPLATE" | "CONFIG" | "REFDATA"

Example SKs:
  AGENT#supervisor           → user's override for the supervisor prompt
  AGENT#legal-counsel        → user's override for legal-counsel
  SKILL#oa-intake            → user's override for the OA intake skill
  TEMPLATE#sow               → user's preferred SOW template body
  CONFIG#model               → user's model preference (e.g., "sonnet")
  CONFIG#max_turns           → user's max turns preference

Attributes:
  entity_type:    str       — mirrors SK prefix
  name:           str       — agent/skill/template/config name
  content:        str       — override content (markdown or JSON)
  is_append:      bool      — true = append to base; false = replace (agents/skills only)
  version:        int       — monotonic within this user+workspace+entity
  created_at:     ISO
  updated_at:     ISO
  reset_at:       ISO       — last time user "reset to default" for this entity (informational)
```

**Query pattern**: All overrides for a user's active workspace in one query:
```python
# Fetch all overrides for this workspace (cheap — one partition key)
response = table.query(
    KeyConditionExpression="PK = :pk",
    ExpressionAttributeValues={":pk": f"WSPC#{tenant_id}#{user_id}#{workspace_id}"}
)
# Build override dict: {entity_type: {name: content}}
```

**Reset behavior**: `DELETE WSPC#{tenant_id}#{user_id}#{workspace_id} / AGENT#supervisor` → next request falls through to PLUGIN# base. User sees the original default again.

**Copy workspace**: Creating a new workspace from an existing one copies all WSPC# items with new `workspace_id` in the PK.

**API endpoints**:
```
GET    /api/workspace                           → list user's workspaces
POST   /api/workspace                           → create new workspace
GET    /api/workspace/{workspace_id}            → get workspace + override summary
PUT    /api/workspace/{workspace_id}/activate   → switch active workspace
DELETE /api/workspace/{workspace_id}            → delete non-default workspace (overrides deleted too)
POST   /api/workspace/{workspace_id}/copy       → fork into new named workspace

GET    /api/workspace/{workspace_id}/overrides              → list all overrides in workspace
GET    /api/workspace/{workspace_id}/overrides/{type}/{name} → get specific override + base for comparison
PUT    /api/workspace/{workspace_id}/overrides/{type}/{name} → set override
DELETE /api/workspace/{workspace_id}/overrides/{type}/{name} → reset to base default
DELETE /api/workspace/{workspace_id}/overrides              → reset entire workspace to defaults
```

---

### `PROMPT#` — Admin/Tenant Prompt Overrides *(layered below WSPC#, above PLUGIN#)*

```
PK:  PROMPT#{tenant_id}   (or PROMPT#global for system-wide)
SK:  PROMPT#{agent_name}

Attributes:
  agent_name:   str       — "supervisor", "oa-intake", "legal-counsel", etc.
  prompt_body:  str       — override text
  is_append:    bool      — true = append to bundled; false = replace entirely
  updated_at:   ISO
  updated_by:   user_id
  version:      int       — monotonic
  ttl:          epoch     — optional auto-expiry
```

Fallback chain: `user override → tenant override → global override → PLUGIN# canonical → bundled fallback (never after seed)`

---

### `CONFIG#` — Runtime Feature Flags & Tier Configuration

```
PK:  CONFIG#global
SK:  CONFIG#{key}

Keys and their value shapes:
  model            → "haiku" | "sonnet" | "opus"
  tier_budgets     → {"basic": 0.10, "advanced": 0.25, "premium": 0.75}
  tier_tools       → {"basic": [], "advanced": ["Read","Glob"], "premium": ["Read","Glob","Bash"]}
  rate_limits      → {"basic": 10, "advanced": 50, "premium": 200}
  max_turns        → 15
  skill_cache_ttl  → 60  (seconds)
  feature_flags    → {"streaming_v2": true, "user_skills": false, "mcp_enabled": false}
```

---

### `TEMPLATE#` — User/Tenant Document Template Overrides *(new)*

Document templates currently live in `eagle-plugin/data/templates/*.md` with `{{VARIABLE}}` placeholders. This entity stores modified versions.

```
PK:  TEMPLATE#{tenant_id}   (or TEMPLATE#global for system defaults)
SK:  TEMPLATE#{doc_type}#{user_id}

doc_type values: "sow" | "igce" | "acquisition-plan" | "market-research" | "justification"
user_id values:  specific user ID (personal override) or "shared" (tenant-wide)

Attributes:
  doc_type:        str
  tenant_id:       str
  owner_user_id:   str
  template_body:   str       — full template text with {{VARIABLES}}
  variables:       List[str] — extracted list of {{}} placeholders
  display_name:    str       — "NCI Standard SOW v3 (modified)"
  is_default:      bool      — true = this is the tenant default for this doc_type
  version:         int
  parent_version:  str       — which version this was forked from
  created_at:      ISO
  updated_at:      ISO
  ttl:             epoch     — optional
  GSI1PK:          TENANT#{tenant_id}
  GSI1SK:          TEMPLATE#{doc_type}#{updated_at}
```

**Fallback chain**: `user template → tenant shared template → global system template → PLUGIN#templates (DynamoDB canonical) → eagle-plugin/ bundled file (never after seed)`

**API endpoints**:
```
GET    /api/templates                              → list available templates for user
GET    /api/templates/{doc_type}                   → get active template (resolved fallback)
POST   /api/templates/{doc_type}                   → create user/tenant template
PUT    /api/templates/{doc_type}/{template_id}     → update template
DELETE /api/templates/{doc_type}/{template_id}     → delete (reverts to parent)
POST   /api/templates/{doc_type}/preview           → render template with sample data
GET    /api/templates/{doc_type}/history           → version history
```

---

### `SKILL#` — User-Created Custom Skills *(new)*

Users can define their own skill agents. The supervisor dynamically discovers active published skills at request time.

```
PK:  SKILL#{tenant_id}
SK:  SKILL#{skill_id}

Attributes:
  skill_id:        str       — uuid4
  tenant_id:       str
  owner_user_id:   str
  name:            str       — "budget-estimator"
  display_name:    str       — "Budget Estimation Specialist"
  description:     str       — shown to supervisor for routing decisions
  prompt_body:     str       — the skill's full system prompt
  triggers:        List[str] — phrases that route to this skill
  tools:           List[str] — allowed tools (gated by tier)
  model:           str       — model override for this skill
  status:          str       — "draft" | "review" | "active" | "disabled"
  visibility:      str       — "private" | "tenant" | "global"
  version:         int
  created_at:      ISO
  updated_at:      ISO
  published_at:    ISO       — when status → active
  GSI2PK:          SKILL_STATUS#{status}
  GSI2SK:          TENANT#{tenant_id}#{skill_id}
```

**Lifecycle**: `draft → review → active` (admin approval gate for government compliance)

**Integration with `sdk_agentic_service.py`**: `build_skill_agents()` queries `SKILL#{tenant_id}` for active skills and merges them with the bundled registry. User skills can override bundled skills with the same name.

**API endpoints**:
```
GET    /api/skills                    → list skills (bundled + user-created)
POST   /api/skills                    → create new skill (status=draft)
GET    /api/skills/{skill_id}         → get skill detail
PUT    /api/skills/{skill_id}         → update draft skill
POST   /api/skills/{skill_id}/submit  → submit for review
POST   /api/skills/{skill_id}/publish → admin: approve and activate
DELETE /api/skills/{skill_id}         → delete (or deactivate)
POST   /api/skills/{skill_id}/test    → test skill against a prompt
```

---

### `PACKAGE#` — Acquisition Packages *(new)*

The `oa-intake` skill guides users but has nowhere to persist a structured package. This entity tracks the lifecycle of a full acquisition package.

```
PK:  PACKAGE#{tenant_id}
SK:  PACKAGE#{package_id}

Attributes:
  package_id:          str       — "PKG-2026-0001" (auto-numbered)
  tenant_id:           str
  owner_user_id:       str
  title:               str       — "Microscopy Equipment Purchase"
  requirement_type:    str       — "supplies" | "services" | "construction" | "r&d"
  estimated_value:     Decimal
  acquisition_pathway: str       — "micro_purchase" | "simplified" | "full_competition" | "sole_source"
  contract_vehicle:    str       — "GSA MAS" | "NITAAC CIO-SP3" | etc.
  status:              str       — "intake" | "drafting" | "review" | "approved" | "awarded" | "closed"
  session_id:          str       — originating chat session
  required_documents:  List[str] — ["sow", "igce", "market-research"]
  completed_documents: List[str] — documents generated so far
  far_citations:       List[str] — relevant FAR clauses
  notes:               str
  created_at:          ISO
  updated_at:          ISO
  approved_at:         ISO
  ttl:                 epoch
  GSI1PK:              TENANT#{tenant_id}
  GSI1SK:              PACKAGE#{status}#{created_at}
```

**API endpoints**:
```
GET    /api/packages                          → list packages for user
POST   /api/packages                          → create package (from intake)
GET    /api/packages/{package_id}             → get package + documents
PUT    /api/packages/{package_id}             → update package
POST   /api/packages/{package_id}/submit      → submit for review
GET    /api/packages/{package_id}/checklist   → what's missing?
```

---

### `DOCUMENT#` — Generated Acquisition Documents *(new)*

Generated SOW/IGCE/AP documents are currently exported and discarded. This persists them with version history.

```
PK:  DOCUMENT#{tenant_id}
SK:  DOCUMENT#{package_id}#{doc_type}#{version}

Attributes:
  document_id:   str
  package_id:    str       — links to PACKAGE#
  doc_type:      str       — "sow" | "igce" | "acquisition-plan" | "market-research" | "justification"
  content:       str       — markdown content (export renders from this)
  template_id:   str       — which TEMPLATE# was used to generate
  version:       int
  status:        str       — "draft" | "final" | "superseded"
  generated_by:  str       — user_id
  session_id:    str       — chat session that generated it
  created_at:    ISO
  s3_key:        str       — optional: S3 path if exported to DOCX/PDF
```

---

### `REFDATA#` — Reference Data Versions *(superseded by PLUGIN#, kept for versioned snapshots)*

The active reference data (thresholds, FAR, contract vehicles) now lives in `PLUGIN#refdata`. The `REFDATA#` entity is retained only for **versioned snapshots** — when an admin updates thresholds for FY2027, the previous FY2026 version is archived here for audit purposes.

```
PK:  REFDATA#global
SK:  REFDATA#{dataset}#{version}

Attributes:
  dataset:     str       — "thresholds" | "far-database" | "contract-vehicles"
  version:     str       — "FY2024", "FY2026", "FY2027", etc.
  data:        str       — JSON snapshot at time of archival
  archived_at: ISO
  archived_by: str
  notes:       str
  ttl:         epoch     — 7 years (government records retention)
```

**Active data**: Always in `PLUGIN#refdata/PLUGIN#{dataset}` with version tracking. `REFDATA#` is the historical archive.

---

### `AUDIT#` — Immutable Audit Trail *(new, critical for government)*

Every mutation to PROMPT, CONFIG, TEMPLATE, SKILL, PACKAGE, DOCUMENT, REFDATA writes an audit record. Required for government accountability and FedRAMP.

```
PK:  AUDIT#{tenant_id}
SK:  AUDIT#{ISO_timestamp}#{entity_type}#{entity_id}

Attributes:
  action:        str       — "create" | "update" | "delete" | "publish" | "approve"
  entity_type:   str       — "prompt" | "template" | "skill" | "package" | "document" | "refdata"
  entity_id:     str
  user_id:       str
  before:        str       — JSON snapshot of state before change (null for creates)
  after:         str       — JSON snapshot of state after change
  ip_address:    str
  user_agent:    str
  created_at:    ISO
  ttl:           epoch     — 7 years (government records retention)
```

Audit records are write-once (no update, no delete via API). TTL set to 7 years to satisfy FAR record-keeping requirements.

---

### `PREF#` — User Preferences *(new)*

```
PK:  PREF#{tenant_id}
SK:  PREF#{user_id}

Attributes:
  default_model:        str       — "haiku" | "sonnet" | "opus"
  default_doc_format:   str       — "docx" | "pdf" | "markdown"
  preferred_vehicle:    str       — "NITAAC" | "GSA" | etc.
  ui_theme:             str       — "light" | "dark"
  notification_email:   bool
  show_far_citations:   bool      — show FAR clause citations in responses
  default_template:     Dict      — per doc_type preferred template_id
  updated_at:           ISO
```

---

### `APPROVAL#` — Document Review/Approval Chain *(new)*

Government packages require multi-step review. Tracks who reviewed, approved, or rejected each document.

```
PK:  APPROVAL#{tenant_id}
SK:  APPROVAL#{package_id}#{step}

Attributes:
  package_id:    str
  step:          int       — 1 = CO review, 2 = Competition Advocate, 3 = HCA
  role:          str       — "contracting_officer" | "competition_advocate" | "head_procuring_activity"
  assignee_id:   str       — user_id responsible for this step
  status:        str       — "pending" | "approved" | "rejected" | "returned"
  comments:      str
  decided_at:    ISO
  required_for:  List[str] — which document types trigger this step
```

**FAR-driven logic**: J&A approval thresholds are already in `thresholds.json`. The approval chain is auto-configured from the package's `estimated_value` and `acquisition_pathway` using the `j_a_approval` thresholds.

---

### `FAVORITE#` — Bookmarked Sessions and Documents *(new)*

```
PK:  FAVORITE#{tenant_id}
SK:  FAVORITE#{user_id}#{target_type}#{target_id}

target_type: "session" | "document" | "template" | "package" | "skill"

Attributes:
  label:      str       — user-defined label
  created_at: ISO
```

---

## What You Were Missing — Gap Analysis

| Gap | Risk | Priority |
|-----|------|----------|
| No user workspace isolation | All users share prompt environment — changes affect everyone | **Critical** |
| Plugin not in DynamoDB | Any content change requires a container rebuild | **High** |
| Templates file-locked | Users can't customize SOW/IGCE without code PR | **High** |
| User skills have no lifecycle | Draft/review gap creates compliance risk | **High** |
| No acquisition package persistence | Intake data only in session messages, not queryable | **High** |
| Reference data in container | FAR threshold updates require rebuild | **High** |
| No audit trail | Government records requirement, FedRAMP risk | **High** |
| Generated documents discarded | Users must re-generate on every export | **Medium** |
| No approval chain | J&A approval thresholds defined but not enforced | **Medium** |
| User preferences not stored | UX friction, repeated config per session | **Low** |
| No favorites | Nice-to-have for power users | **Low** |

### The Three Biggest Gaps

**1. User workspace isolation** — Without `WORKSPACE#` and `WSPC#`, every user shares the same prompt environment. A user modifying a prompt would affect every other user on the tenant. This is the foundational isolation requirement.

**2. Plugin locked in container** — The entire `eagle-plugin/` directory is bundled in Docker. Content changes of any kind — agent prompts, skill prompts, templates, thresholds — require a git commit, image rebuild, and ECS rolling deploy. `PLUGIN#` as source of truth eliminates this.

**3. Audit trail is mandatory, not optional** — For a government acquisition system, every change to prompts, templates, skills, packages, and reference data needs a tamper-evident, 7-year-retention audit log. This is a FedRAMP and FAR compliance requirement.

---

## Implementation Order (Updated)

```
Phase 1 — Foundation (workspace isolation + plugin-in-dynamo)
  Step 1  core-stack.ts             Add GSI1 + GSI2 to eagle table
  Step 2  plugin_store.py           PLUGIN# CRUD + bootstrap seeder + TTL cache
  Step 3  eagle_skill_constants.py  Convert to seeder: populate PLUGIN# on first start
  Step 4  workspace_store.py        WORKSPACE# CRUD + auto-provision default workspace
  Step 5  wspc_store.py             WSPC# CRUD + 4-layer resolution chain
  Step 6  sdk_agentic_service.py    workspace_id threaded through; resolve via wspc_store
  Step 7  session_store.py          Add workspace_id to session record; replace 4 scan() with GSI1
  Step 8  audit_store.py            AUDIT# write-only + 7yr TTL
  Step 9  prompt_store.py           PROMPT#admin tenant overrides (layer 2 of chain)
  Step 10 config_store.py           CONFIG# CRUD + typed accessors

Phase 2 — Content Customization
  Step 11 template_store.py         TEMPLATE# tenant overrides + fallback to PLUGIN#templates
  Step 12 skill_store.py            SKILL# CRUD + draft→review→active lifecycle
  Step 13 sdk_agentic_service.py    Merge user SKILL# into build_skill_agents()

Phase 3 — Acquisition Lifecycle
  Step 14 package_store.py          PACKAGE# CRUD + FAR threshold-driven pathway logic
  Step 15 document_store.py         DOCUMENT# CRUD + version tracking
  Step 16 approval_store.py         APPROVAL# chain + auto-config from PLUGIN#refdata thresholds

Phase 4 — UX + Admin
  Step 17 main.py                   All new endpoints (workspace, plugin, prompts, templates, skills, packages, config)
  Step 18 pref_store.py             PREF# + /api/user/preferences endpoints
  Step 17 POST /api/admin/reload    Force-flush all caches (plugin, prompt, config, template, refdata)
  Step 18 POST /api/admin/plugin/sync  Force reseed PLUGIN# from bundled files (factory reset)
```

---

## Validation Commands

```bash
# Level 1: Lint
ruff check server/app/

# Level 2: Unit tests
python -m pytest server/tests/ -v

# Level 4: CDK synth (after core-stack.ts changes)
cd infrastructure/cdk-eagle && npx cdk synth --quiet

# Verify GSIs active post-deploy:
aws dynamodb describe-table \
  --profile eagle \
  --table-name eagle \
  --query 'Table.GlobalSecondaryIndexes[*].{Name:IndexName,Status:IndexStatus}' \
  --output table

# Hot-reload smoke test:
# 1. PUT /api/admin/prompts/supervisor       → inject override
# 2. POST /api/chat                          → confirm override active (no restart)
# 3. DELETE /api/admin/prompts/supervisor    → revert to bundled
# 4. POST /api/admin/reload                  → verify cache flush
```

---

## Rollback Plan

| Change | Rollback |
|--------|---------|
| GSI1/GSI2 CDK | Delete index from CDK → redeploy; no data loss |
| New store modules | Remove imports; all additive |
| sdk_agentic_service changes | Git revert; bundled defaults remain |
| session_store GSI queries | Git revert to scan() |
| New admin endpoints | Remove from main.py; no schema impact |
| REFDATA# migration | JSON files still bundled as fallback |

---

## New Files Summary

| File | Purpose |
|------|---------|
| `server/app/plugin_store.py` | **PLUGIN# entity — canonical source of truth, bootstrap seeder, TTL cache** |
| `server/app/workspace_store.py` | **WORKSPACE# entity — workspace registry, auto-provision, active workspace resolution** |
| `server/app/wspc_store.py` | **WSPC# entity — user workspace content overrides, 4-layer resolution chain** |
| `server/app/prompt_store.py` | PROMPT# entity — admin/tenant overrides (layer 2, above PLUGIN#) |
| `server/app/config_store.py` | CONFIG# entity + typed accessors |
| `server/app/audit_store.py` | AUDIT# write-once log (7yr TTL) |
| `server/app/template_store.py` | TEMPLATE# entity — user overrides, fallback to PLUGIN#templates |
| `server/app/skill_store.py` | SKILL# entity — user-created skills with draft→review→active lifecycle |
| `server/app/package_store.py` | PACKAGE# entity — acquisition lifecycle + FAR pathway logic |
| `server/app/document_store.py` | DOCUMENT# entity — generated doc versioning |
| `server/app/approval_store.py` | APPROVAL# chain auto-configured from PLUGIN#refdata thresholds |
| `server/app/pref_store.py` | PREF# entity — user preferences |

## Modified Files

| File | Changes |
|------|---------|
| `infrastructure/cdk-eagle/lib/core-stack.ts` | Add GSI1 + GSI2 to `eagle` table |
| `server/eagle_skill_constants.py` | Convert from primary source to bootstrap seeder for `plugin_store.py` |
| `server/app/sdk_agentic_service.py` | Read from `plugin_store` + `prompt_store`; merge `skill_store` user skills |
| `server/app/session_store.py` | Replace 4 `scan()` with GSI1 queries; write GSI2 fields |
| `server/app/main.py` | ~40 new admin/user endpoints across all entity types |

## What `eagle-plugin/` Becomes

The `eagle-plugin/` directory stays in git and stays in the Docker image — but **only as a bootstrap seed**.

After first startup seeds DynamoDB, `eagle-plugin/` is never the authoritative source again. All reads go to `PLUGIN#` in DynamoDB. `POST /api/admin/plugin/sync` is the escape hatch to reseed from bundled files (factory reset for any entity type). Changes go through DynamoDB API, not git commits.
