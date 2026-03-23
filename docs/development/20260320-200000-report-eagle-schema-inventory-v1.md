# EAGLE Schema Inventory & Data Structure Report

**Generated:** 2026-03-20
**Scope:** All JSON data structures, DynamoDB entities, API schemas, TypeScript types, naming conventions

---

## Table of Contents

1. [Folder Structure](#1-folder-structure)
2. [DynamoDB Single-Table Design (14 Entities)](#2-dynamodb-single-table-design)
3. [Template System (36 Templates)](#3-template-system)
4. [Plugin / Agent / Skill Schemas](#4-plugin--agent--skill-schemas)
5. [Reference Data (matrix.json, thresholds.json)](#5-reference-data)
6. [Pydantic Models (Backend)](#6-pydantic-models-backend)
7. [TypeScript Types (Frontend)](#7-typescript-types-frontend)
8. [API Request/Response Schemas](#8-api-requestresponse-schemas)
9. [SSE Event Protocol](#9-sse-event-protocol)
10. [Naming Conventions](#10-naming-conventions)
11. [Compliance Matrix](#11-compliance-matrix)

---

## 1. Folder Structure

```
sm_eagle/
├── .claude/                          # Claude Code context
│   ├── commands/experts/             # 9 expert domains
│   ├── specs/                        # Implementation plans
│   ├── skills/                       # Skill configs
│   └── hooks/                        # Lifecycle hooks
├── .github/workflows/                # CI/CD (deploy.yml, claude-code-assistant.yml)
├── client/                           # Next.js 15+ Frontend (App Router)
│   ├── app/
│   │   ├── api/                      # Next.js API route proxies
│   │   │   ├── invoke/               # SSE proxy → backend /api/chat/stream
│   │   │   ├── chat/                 # REST chat proxy
│   │   │   ├── sessions/             # Session CRUD
│   │   │   ├── documents/            # Document management
│   │   │   ├── packages/             # Acquisition packages
│   │   │   ├── templates/            # Template management
│   │   │   ├── feedback/             # Feedback submission
│   │   │   ├── admin/                # Admin dashboard
│   │   │   ├── analytics/            # Event logging
│   │   │   └── health/               # Health check
│   │   ├── admin/                    # Admin dashboard pages
│   │   ├── chat/                     # Main chat interface
│   │   ├── documents/                # Document viewer
│   │   └── login/                    # Auth pages
│   ├── components/                   # React components (20+ categories)
│   │   ├── chat-simple/              # Main chat UI + tool result panels
│   │   ├── feedback/                 # Feedback modal (Ctrl+J)
│   │   ├── documents/                # Document viewing/editing
│   │   └── auth/                     # Auth components
│   ├── hooks/                        # Custom React hooks (10+)
│   ├── types/                        # TypeScript interfaces (9 files)
│   ├── lib/                          # Utilities
│   └── contexts/                     # React contexts (auth, session)
├── server/                           # FastAPI Backend
│   ├── app/
│   │   ├── main.py                   # All REST routes (2,700+ lines, 60+ endpoints)
│   │   ├── models.py                 # Pydantic BaseModel definitions
│   │   ├── streaming_routes.py       # SSE streaming endpoint
│   │   ├── stream_protocol.py        # SSE event schema + MultiAgentStreamWriter
│   │   ├── strands_agentic_service.py # Strands SDK orchestration
│   │   ├── session_store.py          # DynamoDB: SESSION#, MSG#, USAGE#, SUB#, COST#
│   │   ├── document_store.py         # DynamoDB: DOCUMENT#
│   │   ├── package_store.py          # DynamoDB: PACKAGE#
│   │   ├── approval_store.py         # DynamoDB: APPROVAL#
│   │   ├── workspace_store.py        # DynamoDB: WORKSPACE#
│   │   ├── plugin_store.py           # DynamoDB: PLUGIN#
│   │   ├── skill_store.py            # DynamoDB: SKILL#
│   │   ├── feedback_store.py         # DynamoDB: FEEDBACK#
│   │   ├── audit_store.py            # DynamoDB: AUDIT#
│   │   ├── template_registry.py      # Template → S3 mapping (11 entries)
│   │   ├── template_schema.py        # Template section/field parsing
│   │   ├── template_service.py       # Document generation pipeline
│   │   ├── template_store.py         # DynamoDB: TEMPLATE#
│   │   ├── subscription_service.py   # Tier limits & gating
│   │   ├── cost_attribution.py       # Bedrock/API pricing
│   │   └── telemetry/
│   │       └── dynamodb_trace_store.py # DynamoDB: TRACE#
│   ├── eagle_skill_constants.py      # Plugin auto-discovery loader
│   └── tests/                        # Pytest suite
├── eagle-plugin/                     # Agent & Skill Definitions (Source of Truth)
│   ├── plugin.json                   # Manifest: active agents + skills
│   ├── agents/                       # 8 agents (supervisor + 7 specialists)
│   │   ├── supervisor/agent.md
│   │   ├── policy-analyst/agent.md
│   │   ├── legal-counsel/agent.md
│   │   ├── market-intelligence/agent.md
│   │   ├── tech-translator/agent.md
│   │   ├── public-interest/agent.md
│   │   ├── policy-librarian/agent.md
│   │   └── policy-supervisor/agent.md
│   ├── skills/                       # 7 skills
│   │   ├── oa-intake/SKILL.md
│   │   ├── document-generator/SKILL.md
│   │   ├── compliance/SKILL.md
│   │   ├── knowledge-retrieval/SKILL.md
│   │   ├── tech-review/SKILL.md
│   │   ├── ingest-document/SKILL.md
│   │   └── admin-manager/SKILL.md
│   └── data/                         # Reference data + templates
│       ├── matrix.json               # FAR compliance matrix
│       ├── thresholds.json           # FAR dollar thresholds
│       ├── contract-vehicles.json    # Vehicle definitions
│       ├── templates/                # 5 markdown templates
│       └── template-metadata/        # 36 template metadata JSONs + _index.json
└── infrastructure/cdk-eagle/         # AWS CDK (TypeScript)
    ├── lib/
    │   ├── core-stack.ts             # VPC, Cognito, DynamoDB, IAM
    │   ├── compute-stack.ts          # ECS Fargate, ECR, ALB
    │   ├── storage-stack.ts          # S3, document_metadata table
    │   └── cicd-stack.ts             # GitHub Actions OIDC role
    └── config/environments.ts        # Account, region, bucket config
```

---

## 2. DynamoDB Single-Table Design

**Table Name:** `eagle` (env: `EAGLE_SESSIONS_TABLE`)
**Billing:** PAY_PER_REQUEST | **PITR:** Enabled | **TTL Attribute:** `ttl`

### Global Secondary Indexes

| GSI | Partition Key | Sort Key | Projection | Use Case |
|-----|--------------|----------|------------|----------|
| GSI1 | `GSI1PK` | `GSI1SK` | ALL | Tenant-level queries, workspace listing, feedback |
| GSI2 | `GSI2PK` | `GSI2SK` | ALL | Subscription tier lookups, skill status filtering |

### Entity Key Patterns (14 Total)

#### 2.1 SESSION# — Conversation Sessions
**Source:** `server/app/session_store.py`

| Key | Pattern |
|-----|---------|
| PK | `SESSION#{tenant_id}#{user_id}` |
| SK | `SESSION#{session_id}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `SESSION#{created_at_iso}#{session_id}` |

| Property | Type | Description |
|----------|------|-------------|
| `session_id` | string | Format: `s-{timestamp}-{uuid8}` |
| `tenant_id` | string | Owning tenant |
| `user_id` | string | Owning user |
| `title` | string | Default: "New Conversation" |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |
| `message_count` | int | Running count |
| `total_tokens` | int | Cumulative token usage |
| `status` | string | "active" |
| `metadata` | object | Arbitrary key-value |
| `ttl` | int | Epoch seconds (30 days default) |

---

#### 2.2 MSG# — Chat Messages

| Key | Pattern |
|-----|---------|
| PK | `SESSION#{tenant_id}#{user_id}` |
| SK | `MSG#{session_id}#{message_id}` |

| Property | Type | Description |
|----------|------|-------------|
| `message_id` | string | Format: `{timestamp_ms}-{md5_hash8}` |
| `session_id` | string | Parent session |
| `role` | string | `"user"` \| `"assistant"` |
| `content` | string | Text or JSON-serialized list |
| `content_type` | string | `"text"` \| `"list"` |
| `created_at` | string | ISO 8601 |
| `metadata` | object | Arbitrary key-value |

---

#### 2.3 USAGE# — Token Usage Tracking

| Key | Pattern |
|-----|---------|
| PK | `USAGE#{tenant_id}` |
| SK | `USAGE#{YYYY-MM-DD}#{session_id}#{timestamp_ms}` |

| Property | Type | Description |
|----------|------|-------------|
| `tenant_id` | string | |
| `user_id` | string | |
| `session_id` | string | |
| `input_tokens` | int | |
| `output_tokens` | int | |
| `total_tokens` | int | |
| `model` | string | Bedrock model ID |
| `cost_usd` | Decimal | Calculated cost |
| `created_at` | string | ISO 8601 |
| `date` | string | YYYY-MM-DD partition |

---

#### 2.4 COST# — Cost Attribution Metrics

| Key | Pattern |
|-----|---------|
| PK | `COST#{tenant_id}` |
| SK | `COST#{YYYY-MM-DD}#{timestamp_ms}` |

| Property | Type | Description |
|----------|------|-------------|
| `tenant_id` | string | |
| `user_id` | string | |
| `session_id` | string | |
| `metric_type` | string | `"bedrock_input_tokens"` \| `"weather_api_call"` \| `"agent_invocation"` |
| `value` | Decimal | |
| `timestamp` | string | ISO 8601 |
| `created_at` | string | ISO 8601 |
| `**metadata` | any | Dynamic key-value pairs |

---

#### 2.5 SUB# — Subscription Usage Counters

| Key | Pattern |
|-----|---------|
| PK | `SUB#{tenant_id}` |
| SK | `SUB#{tier}#current` |

| Property | Type | Description |
|----------|------|-------------|
| `tenant_id` | string | |
| `tier` | string | `"basic"` \| `"advanced"` \| `"premium"` |
| `daily_usage` | int | |
| `monthly_usage` | int | |
| `active_sessions` | int | |
| `last_reset_date` | string | ISO 8601 |

---

#### 2.6 DOCUMENT# — Versioned Documents

| Key | Pattern |
|-----|---------|
| PK | `DOCUMENT#{tenant_id}` |
| SK | `DOCUMENT#{package_id}#{doc_type}#{version}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `DOCUMENT#{package_id}#{doc_type}#{version:04d}` |

| Property | Type | Description |
|----------|------|-------------|
| `document_id` | string | UUID |
| `package_id` | string | Parent package |
| `doc_type` | string | See doc types below |
| `content` | string | Document body |
| `version` | int | Auto-incremented |
| `status` | string | `"draft"` \| `"final"` \| `"approved"` |
| `generated_by` | string | Agent name |
| `created_at` | string | ISO 8601 |
| `session_id` | string | Optional |
| `template_id` | string | Optional |

**Valid `doc_type` values:** `sow`, `igce`, `market_research`, `acquisition_plan`, `justification`, `funding_doc`, `eval_criteria`, `security_checklist`, `section_508`, `cor_certification`, `contract_type_justification`, `d_f`, `qasp`, `source_selection_plan`, `subcontracting_plan`, `sb_review`, `purchase_request`, `human_subjects`

---

#### 2.7 PACKAGE# — Acquisition Lifecycle Packages

| Key | Pattern |
|-----|---------|
| PK | `PACKAGE#{tenant_id}` |
| SK | `PACKAGE#{package_id}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `PACKAGE#{status}#{created_at}` |

| Property | Type | Description |
|----------|------|-------------|
| `package_id` | string | |
| `tenant_id` | string | |
| `title` | string | |
| `requirement_type` | string | |
| `estimated_value` | Decimal | USD — drives FAR pathway |
| `acquisition_pathway` | string | `"micro_purchase"` \| `"simplified"` \| `"full_competition"` \| `"sole_source"` |
| `acquisition_method` | string | |
| `contract_type` | string | |
| `flags` | list | |
| `contract_vehicle` | string | |
| `status` | string | `"draft"` \| `"in_progress"` \| `"pending_review"` \| `"approved"` \| `"completed"` |
| `notes` | string | |
| `completed_documents` | list | |
| `far_citations` | list | |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |

---

#### 2.8 APPROVAL# — FAR-Driven Approval Chains

| Key | Pattern |
|-----|---------|
| PK | `APPROVAL#{tenant_id}` |
| SK | `APPROVAL#{package_id}#{step:02d}` |

| Property | Type | Description |
|----------|------|-------------|
| `package_id` | string | |
| `step` | int | 01-03 based on FAR thresholds |
| `role` | string | `"contracting_officer"` \| `"competition_advocate"` \| `"head_procuring_activity"` |
| `status` | string | `"pending"` \| `"approved"` \| `"rejected"` |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |
| `reviewed_by` | string | user_id (optional) |
| `reviewed_at` | string | ISO 8601 (optional) |
| `notes` | string | Optional |

**FAR Threshold Rules:**
- < $250K → 1 step (contracting_officer)
- < $750K → 2 steps (+competition_advocate)
- >= $750K → 3 steps (+head_procuring_activity)

---

#### 2.9 WORKSPACE# — User Prompt Environments

| Key | Pattern |
|-----|---------|
| PK | `WORKSPACE#{tenant_id}#{user_id}` |
| SK | `WORKSPACE#{workspace_id}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `WORKSPACE#{user_id}#{workspace_id}` |

| Property | Type | Description |
|----------|------|-------------|
| `workspace_id` | string | UUID |
| `tenant_id` | string | |
| `user_id` | string | |
| `name` | string | |
| `description` | string | |
| `is_active` | bool | Only one active per user |
| `is_default` | bool | |
| `visibility` | string | `"private"` \| `"shared"` |
| `override_count` | int | |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |
| `base_workspace_id` | string | Optional (inheritance) |

---

#### 2.10 TEMPLATE# — Custom Tenant Templates

| Key | Pattern |
|-----|---------|
| PK | `TEMPLATE#{tenant_id}` |
| SK | `TEMPLATE#{doc_type}#{user_id}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `TEMPLATE#{doc_type}#{updated_at}` |

| Property | Type | Description |
|----------|------|-------------|
| `doc_type` | string | Document type |
| `tenant_id` | string | |
| `owner_user_id` | string | user_id or `"shared"` |
| `template_body` | string | Raw markdown/text |
| `variables` | list | Extracted `{{PLACEHOLDER}}` names |
| `display_name` | string | UI label |
| `is_default` | bool | Default for this doc type |
| `version` | int | Auto-incremented |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |
| `parent_version` | string | Optional |
| `ttl` | int | Optional |

**Resolution Chain:** User override → Tenant shared → Global default → Plugin canonical

---

#### 2.11 PLUGIN# — Runtime Plugin Content

| Key | Pattern |
|-----|---------|
| PK | `PLUGIN#{entity_type}` |
| SK | `PLUGIN#{name}` |

`entity_type` values: `"agents"` \| `"skills"` \| `"templates"` \| `"refdata"` \| `"tools"` \| `"manifest"`

| Property | Type | Description |
|----------|------|-------------|
| `entity_type` | string | |
| `name` | string | |
| `content` | string | Markdown or JSON body |
| `content_type` | string | `"markdown"` \| `"json"` |
| `metadata` | object | |
| `version` | int | Auto-incremented |
| `is_active` | bool | |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |

Cache: 60-second in-memory TTL

---

#### 2.12 SKILL# — Custom Tenant Skills

| Key | Pattern |
|-----|---------|
| PK | `SKILL#{tenant_id}` |
| SK | `SKILL#{skill_id}` |
| GSI2PK | `SKILL_STATUS#{status}` |
| GSI2SK | `TENANT#{tenant_id}#{skill_id}` |

| Property | Type | Description |
|----------|------|-------------|
| `skill_id` | string | UUID |
| `tenant_id` | string | |
| `owner_user_id` | string | |
| `name` | string | |
| `display_name` | string | |
| `description` | string | |
| `prompt_body` | string | |
| `triggers` | list | String patterns |
| `tools` | list | Tool names |
| `model` | string | Optional override |
| `status` | string | `"draft"` → `"review"` → `"active"` → `"disabled"` |
| `visibility` | string | |
| `version` | int | |
| `created_at` | string | ISO 8601 |
| `updated_at` | string | ISO 8601 |
| `published_at` | string | Optional |

---

#### 2.13 FEEDBACK# — User Feedback

| Key | Pattern |
|-----|---------|
| PK | `FEEDBACK#{tenant_id}` |
| SK | `FEEDBACK#{ISO_timestamp}#{feedback_id}` |
| GSI1PK | `TENANT#{tenant_id}` |
| GSI1SK | `FEEDBACK#{created_at}` |

| Property | Type | Description |
|----------|------|-------------|
| `feedback_id` | string | |
| `tenant_id` | string | |
| `user_id` | string | |
| `session_id` | string | |
| `message_id` | string | Optional |
| `content` | string | Feedback text |
| `feedback_type` | string | `"bug"` \| `"suggestion"` \| `"praise"` \| `"incorrect_info"` \| `"general"` |
| `created_at` | string | ISO 8601 |
| `ttl` | int | 7 years from write |

---

#### 2.14 AUDIT# — Immutable Event Log

| Key | Pattern |
|-----|---------|
| PK | `AUDIT#{tenant_id}` |
| SK | `AUDIT#{ISO_timestamp}#{entity_type}#{entity_name}` |

| Property | Type | Description |
|----------|------|-------------|
| `entity_type` | string | `"agent"` \| `"skill"` \| `"config"` |
| `entity_name` | string | |
| `event_type` | string | `"RELOAD"` \| `"CREATE"` \| `"DELETE"` \| `"UPDATE"` |
| `actor_user_id` | string | |
| `before` | string | Optional JSON snapshot |
| `after` | string | Optional JSON snapshot |
| `metadata` | object | |
| `occurred_at` | string | ISO 8601 |
| `ttl` | int | 7 years from write |

---

#### 2.15 TRACE# — Telemetry Trace Summaries

| Key | Pattern |
|-----|---------|
| PK | `TRACE#{tenant_id}` |
| SK | `TRACE#{YYYY-MM-DD}#{trace_id}` |
| GSI1PK | `SESSION#{session_id}` |
| GSI1SK | `TRACE#{trace_id}` |

| Property | Type | Description |
|----------|------|-------------|
| `trace_id` | string | |
| `tenant_id` | string | |
| `user_id` | string | |
| `session_id` | string | |
| `created_at` | string | ISO 8601 |
| `date` | string | YYYY-MM-DD |
| `duration_ms` | int | |
| `total_input_tokens` | int | |
| `total_output_tokens` | int | |
| `total_cost_usd` | Decimal | |
| `tools_called` | list | |
| `agents_delegated` | list | |
| `span_count` | int | |
| `spans` | string | JSON array |
| `status` | string | `"success"` \| `"error"` |
| `ttl` | int | 30 days |

---

#### 2.16 AGG# — Daily Aggregates

| Key | Pattern |
|-----|---------|
| PK | `AGG#{tenant_id}` |
| SK | `DAILY#{YYYY-MM-DD}` |

| Property | Type | Description |
|----------|------|-------------|
| `input_tokens` | int | |
| `output_tokens` | int | |
| `total_cost` | Decimal | |
| `request_count` | int | |
| `updated_at` | string | ISO 8601 |

---

## 3. Template System

### 3.1 Template Metadata Index
**File:** `eagle-plugin/data/template-metadata/_index.json`

```json
{
  "total_templates": 36,
  "by_category": {
    "acquisition_plan": ["file1.json", ...],
    "igce": [...],
    "sow": [...],
    "son_products": [...],
    "son_services": [...],
    "justification": [...],
    "market_research": [...],
    "conference_request": [...],
    "conference_waiver": [...],
    "promotional_item": [...],
    "exemption_determination": [...],
    "mandatory_use_waiver": [...],
    "buy_american": [...],
    "gfp_form": [...],
    "subk_plan": [...],
    "reference_guide": [...],
    "bpa_call_order": [...],
    "cor_certification": [...],
    "technical_questionnaire": [...],
    "quotation_abstract": [...],
    "receiving_report": [...],
    "srb_request": [...],
    "subk_review": [...]
  },
  "templates": [/* array of template metadata objects */]
}
```

### 3.2 Individual Template Metadata
**Files:** `eagle-plugin/data/template-metadata/{name}.json` (36 files)

| Property | Type | Description |
|----------|------|-------------|
| `filename` | string | Original document filename |
| `format` | string | `"docx"` \| `"xlsx"` \| `"pdf"` \| `"doc"` \| `"txt"` |
| `category` | string | Document classification |
| `variant` | string | Optional: `"above_sat"`, `"products"`, etc. |
| `sections` | array | Section objects (see below) |
| `total_placeholders` | int | Total `{{PLACEHOLDER}}` count |
| `total_sections` | int | Section count |
| `sheet_names` | array | For XLSX files |
| `parse_error` | string\|null | Parsing error if any |

**Section object:**

| Property | Type | Description |
|----------|------|-------------|
| `number` | string | e.g., `"1"`, `"1.1"`, `"2.1.1"` |
| `title` | string | Section heading |
| `has_table` | bool | Contains table |
| `placeholders` | array | `{{PLACEHOLDER}}` names |

### 3.3 Template Registry (Python)
**File:** `server/app/template_registry.py`

**TemplateMapping dataclass:**

| Property | Type | Description |
|----------|------|-------------|
| `doc_type` | string | Primary key |
| `s3_filename` | string | Template file in S3 |
| `file_type` | string | `"docx"` \| `"xlsx"` \| `"pdf"` |
| `placeholder_map` | dict | Field name → `{{PLACEHOLDER}}` |
| `alternates` | list | Alternate template filenames |
| `description` | string | Human-readable |
| `display_name` | string | UI label |
| `section_schema` | TemplateSchema\|None | Attached schema |

**11 Registered Templates:**

| doc_type | S3 File | Format | Key Placeholders |
|----------|---------|--------|-----------------|
| `sow` | `statement-of-work-template-eagle-v2.docx` | docx | title, description, period_of_performance, deliverables, tasks |
| `igce` | `01.D_IGCE_for_Commercial_Organizations.xlsx` | xlsx | title, contractor_name, total_estimate, line_items |
| `market_research` | `HHS_Streamlined_Market_Research_Template_FY26.docx` | docx | title, description, market_conditions, vendors_identified |
| `justification` | `Justification_and_Approval_Over_350K_Template.docx` | docx | title, authority, contractor, estimated_value, rationale |
| `acquisition_plan` | `HHS Streamlined Acquisition Plan Template.docx` | docx | title, description, estimated_value, competition, contract_type |
| `cor_certification` | `NIH COR Appointment Memorandum.docx` | docx | nominee_name, nominee_title, contract_number |
| `son_products` | `3.a. SON - Products...docx` | docx | (form template) |
| `son_services` | `3.b. SON - Services...docx` | docx | (form template) |
| `buy_american` | `DF_Buy_American_Non_Availability_Template.docx` | docx | (form template) |
| `subk_plan` | `HHS SubK Plan Template...doc` | doc | (form template) |
| `conference_request` | `Attachment A - NIH Conference...docx` | docx | (form template) |

### 3.4 Template Schema (Python dataclasses)
**File:** `server/app/template_schema.py`

```
TemplateSchema
├── doc_type: string
├── title: string
├── sections: list[TemplateSection]
├── total_fields: int
└── required_fields: int

TemplateSection
├── number: string
├── title: string
├── description: string
├── fields: list[SectionField]
├── subsections: list[TemplateSection]
└── has_table: bool

SectionField
├── name: string
├── required: bool (default: true)
└── field_type: string ("text" | "list" | "table" | "checkbox")

CompletenessReport
├── doc_type: string
├── total_sections: int
├── filled_sections: int
├── missing_sections: list[string]
├── completeness_pct: float
└── is_complete: bool
```

### 3.5 Template Categories

| doc_type | phase | use_case | group |
|----------|-------|----------|-------|
| sow | planning | competitive | requirements |
| igce | planning | competitive | cost |
| market_research | planning | competitive | research |
| justification | planning | sole_source | justification |
| acquisition_plan | planning | competitive | planning |
| eval_criteria | solicitation | competitive | evaluation |
| security_checklist | planning | compliance | compliance |

**Special Groups:**
- **Markdown-only:** eval_criteria, security_checklist, section_508, contract_type_justification
- **Form templates:** exemption_determination, mandatory_use_waiver, gfp_form, bpa_call_order, quotation_abstract, receiving_report, srb_request, technical_questionnaire
- **Reference guides:** ap_structure_guide, mr_template_guide

### 3.6 Field Name Aliases (30+ normalizations)

| Input Variation | Canonical Name |
|----------------|---------------|
| `competition_type` | `competition` |
| `estimated_cost` | `estimated_value` |
| `contract_period` | `period_of_performance` |
| `vendors` | `vendors_identified` |
| ... (26+ more mappings) | |

---

## 4. Plugin / Agent / Skill Schemas

### 4.1 Plugin Manifest
**File:** `eagle-plugin/plugin.json`

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Plugin identifier |
| `version` | string | Semantic version |
| `description` | string | |
| `author` | string | |
| `agent` | string | Primary agent (supervisor) |
| `agents` | array | Agent directory names |
| `skills` | array | Skill directory names |
| `commands` | array | Command aliases |
| `data` | object | `{ key: { file: "path" } }` — references matrix, thresholds, etc. |
| `capabilities` | object | `{ streaming, tools, multi-turn }` (booleans) |
| `requirements` | object | `{ model, aws_services }` |

### 4.2 Agent Definition (YAML frontmatter)
**Files:** `eagle-plugin/agents/*/agent.md`

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Agent identifier |
| `type` | string | Always `"agent"` |
| `description` | string | Multiline (`>`) |
| `triggers` | array | Intent patterns |
| `tools` | array | Available tool names |
| `model` | string\|null | Model override |

Body: Free-form markdown system prompt

### 4.3 Skill Definition (YAML frontmatter)
**Files:** `eagle-plugin/skills/*/SKILL.md`

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | Skill identifier |
| `description` | string | |
| `triggers` | array | User intent patterns |
| `display_name` | string | Optional UI label |
| `tools` | array | Optional tool names |
| `model` | string | Optional model override |

Body: Free-form markdown with workflow, templates, usage patterns

### 4.4 Plugin Loader Output
**File:** `server/eagle_skill_constants.py`

Each discovered agent/skill becomes a dict:

| Property | Type | Description |
|----------|------|-------------|
| `name` | string | From frontmatter |
| `type` | string | `"agent"` \| `"skill"` |
| `description` | string | |
| `triggers` | array | |
| `tools` | array | |
| `model` | string\|null | |
| `meta` | object | Full parsed YAML frontmatter |
| `body` | string | Markdown body only |
| `content` | string | Full file (frontmatter + body) |

**Exported collections:** `AGENTS`, `SKILLS`, `PLUGIN_CONTENTS`, `SKILL_CONSTANTS`

---

## 5. Reference Data

### 5.1 matrix.json (FAR Compliance Matrix)
**File:** `eagle-plugin/data/matrix.json`

```json
{
  "version": "2026-02-25",
  "rfo_notes": "...",
  "thresholds": [
    { "value": 10000, "label": "...", "short": "...", "triggers": ["..."] }
  ],
  "contract_types": [
    { "id": "ffp", "label": "...", "risk": 5, "category": "fp", "fee_cap": "...", "prereqs": [] }
  ],
  "document_rules": {
    "always": ["sow", "igce"],
    "above_threshold": [
      { "above": 250000, "label": "SAT", "far": "FAR 7.102", "docs": ["acquisition_plan"] }
    ],
    "by_method": { "sole": [...], "negotiated": [...], "idiq": [...] },
    "by_type": {},
    "special_factors": {},
    "approval_chains": {}
  }
}
```

### 5.2 thresholds.json (FAR Dollar Thresholds)
**File:** `eagle-plugin/data/thresholds.json`

```json
{
  "version": "FY2025",
  "last_updated": "2025-...",
  "source": "...",
  "thresholds": {
    "micro_purchase": {
      "general": 10000, "construction": 2000,
      "services_subject_to_sca": 2500, "contingency_operations": 35000
    },
    "simplified_acquisition": {
      "sat": 250000, "commercial_simplified_test": 7500000,
      "commercial_simplified_test_certain": 15000000
    },
    "publicize": { "synopsis_required": 25000, "response_time_days": 15, ... },
    "cost_pricing_data": { "tina_threshold": 2000000 },
    "acquisition_plan": { "new_contract": 250000, "task_delivery_order": 250000 },
    "sole_source_8a": { "services": 4500000, "manufacturing": 4500000 },
    "subcontracting_plan": { "required": 750000, "construction": 1500000 },
    "j_a_approval": {
      "contracting_officer": 750000,
      "competition_advocate": 15000000,
      "head_procuring_activity": 100000000,
      "senior_procurement_executive": "unlimited",
      "agency_head": "unlimited"
    }
  },
  "wage_requirements": {
    "davis_bacon_act": { "applies_above": 2000, "type": "construction" },
    "service_contract_act": { "applies_above": 2500, "type": "services" }
  },
  "small_business_size_standards": { "source": "SBA", "common_examples": {}, "lookup": "..." }
}
```

---

## 6. Pydantic Models (Backend)

**File:** `server/app/models.py`

```python
class SubscriptionTier(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"
    PREMIUM = "premium"

class TierLimits(BaseModel):
    daily_messages: int
    monthly_messages: int
    max_session_duration: int         # minutes
    concurrent_sessions: int
    mcp_server_access: bool

class TenantContext(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    subscription_tier: SubscriptionTier = BASIC

class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None
    package_id: Optional[str] = None
    tenant_context: Optional[TenantContext] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    tenant_id: str
    usage_metrics: Dict[str, Any]

class UsageMetric(BaseModel):
    tenant_id: str
    timestamp: datetime
    metric_type: str
    value: Decimal
    session_id: str
    agent_id: Optional[str] = None

class TenantSession(BaseModel):
    tenant_id: str
    user_id: str
    session_id: str
    subscription_tier: SubscriptionTier
    created_at: datetime
    last_activity: datetime
    message_count: int = 0
    tier_usage_count: int = 0

class SubscriptionUsage(BaseModel):
    tenant_id: str
    subscription_tier: SubscriptionTier
    daily_usage: int = 0
    monthly_usage: int = 0
    active_sessions: int = 0
    last_reset_date: datetime

class UploadResponse(BaseModel):
    key: str
    filename: str
    size_bytes: int
    content_type: str

class KBReviewRecord(BaseModel):
    review_id: str
    filename: str
    s3_key: str
    status: str          # "pending" | "approved" | "rejected"
    analysis_summary: str
    proposed_diff: List[Dict[str, Any]]
    created_at: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
```

### Subscription Tier Limits

| Tier | Daily | Monthly | Session (min) | Concurrent | MCP |
|------|-------|---------|---------------|------------|-----|
| basic | 50 | 1,000 | 30 | 1 | No |
| advanced | 200 | 5,000 | 120 | 3 | Yes |
| premium | 1,000 | 25,000 | 480 | 10 | Yes |

### Cost Attribution Pricing

| Resource | Rate |
|----------|------|
| Bedrock Haiku Input | $0.00025 / 1K tokens |
| Bedrock Haiku Output | $0.00125 / 1K tokens |
| Weather API | $0.0001 / call |
| Agent Runtime | $0.001 / invocation |

---

## 7. TypeScript Types (Frontend)

### 7.1 Chat Types (`client/types/chat.ts`)

```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  reasoning?: string;
  agent_id?: string;
  agent_name?: string;
}

interface DocumentInfo {
  document_id?: string;
  package_id?: string;
  document_type: string;
  doc_type?: string;
  title: string;
  content?: string;
  file_type?: string;
  content_type?: string;
  is_binary?: boolean;
  download_url?: string | null;
  mode?: 'package' | 'workspace';
  status?: string;
  version?: number;
  word_count?: number;
  generated_at?: string;
  s3_key?: string;
  s3_location?: string;
  preview_mode?: 'docx_blocks' | 'xlsx_grid' | 'text_fallback' | 'none' | null;
  preview_blocks?: DocxPreviewBlock[];
  preview_sheets?: XlsxPreviewSheet[];
}

interface DocxPreviewBlock {
  block_id: string;
  kind: 'heading' | 'paragraph' | 'checkbox';
  text: string;
  level?: number | null;
  checked?: boolean | null;
}

interface XlsxPreviewCell {
  cell_ref: string; row: number; col: number;
  value: string; display_value: string;
  editable: boolean; is_formula?: boolean;
}
```

### 7.2 Stream Event Types (`client/types/stream.ts`)

```typescript
type StreamEventType =
  | 'text' | 'reasoning' | 'tool_use' | 'tool_result'
  | 'agent_status' | 'elicitation' | 'metadata'
  | 'complete' | 'error' | 'handoff' | 'user_input' | 'form_submit';

interface StreamEvent {
  type: StreamEventType;
  agent_id: string;
  agent_name: string;
  timestamp: string;
  content?: string;
  reasoning?: string;
  tool_use?: ToolUse;
  tool_result?: ToolResult;
  elicitation?: Elicitation;
  metadata?: Record<string, any>;
}

interface ToolUse {
  name: string;
  input: Record<string, any>;
  tool_use_id?: string;
  execution_target?: 'client' | 'server';
}
```

### 7.3 Schema Enums (`client/types/schema.ts`)

```typescript
type UserRole = 'co' | 'cor' | 'developer' | 'admin' | 'analyst';

type WorkflowStatus = 'draft' | 'in_progress' | 'pending_review'
  | 'approved' | 'rejected' | 'completed' | 'cancelled' | 'review';

type AcquisitionType = 'micro_purchase' | 'simplified' | 'negotiated';
type UrgencyLevel = 'standard' | 'urgent' | 'critical';
type DocumentStatus = 'not_started' | 'in_progress' | 'draft' | 'final' | 'approved';
type ChecklistStepStatus = 'pending' | 'in_progress' | 'completed' | 'skipped';
type SubmissionSource = 'user' | 'ai_generated' | 'imported';
type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'modified';
type CitationSourceType = 'document' | 'url' | 'far_clause' | 'policy' | 'market_data';
type FeedbackType = 'helpful' | 'inaccurate' | 'incomplete' | 'too_verbose';

type DocumentType = 'sow' | 'igce' | 'market_research' | 'acquisition_plan'
  | 'justification' | 'funding_doc' | 'eval_criteria' | 'security_checklist'
  | 'section_508' | 'cor_certification' | 'contract_type_justification'
  | 'd_f' | 'qasp' | 'source_selection_plan' | 'subcontracting_plan'
  | 'sb_review' | 'purchase_request' | 'human_subjects';
```

### 7.4 Admin Types (`client/types/admin.ts`)

```typescript
interface PluginEntity {
  entity_type: string; name: string; content: string;
  content_type: string; metadata: Record<string, unknown>;
  version: number; is_active: boolean;
  created_at: string; updated_at: string;
}

interface Workspace {
  workspace_id: string; tenant_id: string; user_id: string;
  name: string; description: string; is_active: boolean;
  is_default: boolean; visibility: string; override_count: number;
  created_at: string; updated_at: string;
}

interface CustomSkill {
  skill_id: string; tenant_id: string; owner_user_id: string;
  name: string; display_name: string; description: string;
  prompt_body: string; triggers: string[]; tools: string[];
  model?: string; status: 'draft' | 'review' | 'active' | 'disabled';
  visibility: string; version: number;
  created_at: string; updated_at: string; published_at?: string;
}
```

### 7.5 Conversation Types (`client/types/conversation.ts`)

```typescript
interface AgentSession {
  id: string; userId: string; agentId: AgentType;
  messages: AgentMessage[]; toolResults: ToolResult[];
  createdAt: string; updatedAt: string; messageCount: number;
}

interface SharedContext {
  currentWorkflow?: { id: string; title: string; status: string; acquisitionType?: string };
  recentDocuments?: { id: string; title: string; type: string }[];
  userPreferences?: Record<string, unknown>;
  recentInsights?: AgentInsight[];
}

interface UserConversationStore {
  userId: string;
  sessions: Record<AgentType, AgentSession | null>;
  sharedContext: SharedContext;
  lastUpdated: string;
}
```

---

## 8. API Request/Response Schemas

### 8.1 Chat Endpoints

**POST `/api/chat`** (REST)
```
Request:  { message: str, session_id?: str, package_id?: str }
Response: { response: str, session_id: str, usage: {}, model: str,
            tools_called: [], response_time_ms: int, cost_usd?: float }
```

**POST `/api/chat/stream`** (SSE) — see Section 9

### 8.2 Session Endpoints

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| GET | `/api/sessions` | — | `{ sessions: [], count: int }` |
| POST | `/api/sessions` | `{ title?: str }` | Session object |
| GET | `/api/sessions/{id}` | — | Session + message_count |
| PATCH | `/api/sessions/{id}` | `{ title?, status?, metadata? }` | Updated session |
| DELETE | `/api/sessions/{id}` | — | `{ status: "deleted" }` |
| GET | `/api/sessions/{id}/messages` | — | `{ messages: [] }` |

### 8.3 Document Endpoints

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| GET | `/api/documents` | — | `{ documents: [] }` |
| GET | `/api/documents/{key}` | — | Metadata + preview |
| PUT | `/api/documents/{key}` | `{ content, change_source }` | Updated doc |
| POST | `/api/documents/docx-edit/{key}` | `{ preview_blocks, preview_mode, change_source }` | Updated doc |
| POST | `/api/documents/xlsx-edit/{key}` | `{ cell_edits, change_source }` | Updated doc |
| POST | `/api/documents/upload` | multipart file | `{ key, filename, size_bytes, content_type }` |
| GET | `/api/documents/presign` | query: `key` | Presigned S3 URL |
| POST | `/api/documents/export` | `{ content, title, format }` | Streamed file |

### 8.4 Package Endpoints

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| GET | `/api/packages` | — | Package list |
| POST | `/api/packages` | Package fields | Created package |
| GET | `/api/packages/{id}/documents/{docType}` | — | Document |
| PUT | `/api/packages/{id}/documents/{docType}` | Content | Updated doc |
| POST | `/api/packages/{id}/export/zip` | — | ZIP stream |

### 8.5 Template Endpoints

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| GET | `/api/templates` | query: `doc_type?` | Template list |
| GET | `/api/templates/{docType}` | — | Single template |
| POST | `/api/templates/{docType}` | `{ doc_type, user_id, template_body, display_name, is_default }` | Created |
| DELETE | `/api/templates/{docType}` | — | Deleted |
| GET | `/api/templates/s3` | query: `phase?, refresh?` | S3 templates + phase counts |
| GET | `/api/templates/s3/preview` | query: `s3_key` | `{ type, content/url, filename }` |
| POST | `/api/templates/s3/copy` | `{ s3_key, package_id }` | Document entry |

### 8.6 Feedback Endpoints

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| POST | `/api/feedback` | `{ feedback_text, feedback_type, session_id?, page, last_message_id?, conversation_snapshot? }` | `{ feedback_id }` |
| POST | `/api/feedback/message` | `{ session_id, message_id, feedback_type, comment? }` | Confirmation |

### 8.7 Admin Endpoints

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/admin/dashboard` | Active users, sessions, tokens, costs |
| GET | `/api/admin/users` | User list + usage metrics |
| GET | `/api/admin/kb-reviews` | KB review records |
| GET | `/api/admin/plugin/status` | Active agents, skills, plugin metadata |
| GET | `/api/admin/traces` | Langfuse trace history |
| GET | `/api/admin/costs` | Cost analysis |
| GET | `/api/health` | Service health + feature flags |

---

## 9. SSE Event Protocol

**File:** `server/app/stream_protocol.py`

### Event Types

| Type | Purpose | Payload |
|------|---------|---------|
| `text` | Token stream | `content: string` |
| `reasoning` | Chain-of-thought | `reasoning: string` |
| `tool_use` | Agent invokes tool | `tool_use: { name, input, tool_use_id }` |
| `tool_result` | Tool returns | `tool_result: { name, result }` |
| `agent_status` | Progress update | `metadata: { status, detail }` |
| `elicitation` | Agent asks user | `elicitation: { question, fields? }` |
| `metadata` | State update | `metadata: { ... }` |
| `handoff` | Agent delegation | `metadata: { target_agent, reason }` |
| `complete` | Stream finished | `metadata: { duration_ms, tools_called, tool_timings, tool_failures }` |
| `error` | Error occurred | `content: string` |

### Wire Format

```
data: {"type":"text","agent_id":"eagle","agent_name":"EAGLE","content":"Hello","timestamp":"2026-..."}

data: {"type":"tool_use","agent_id":"supervisor","agent_name":"Supervisor","tool_use":{"name":"search_far","input":{"query":"..."},"tool_use_id":"..."},"timestamp":"..."}

data: {"type":"complete","agent_id":"eagle","agent_name":"EAGLE","metadata":{"duration_ms":2500,"tools_called":["search_far"],"tool_timings":[{"tool_name":"search_far","duration_ms":1200}],"tool_failures":[]},"timestamp":"..."}

: keepalive  (every 20s)
```

### Frontend Consumer
**File:** `client/hooks/use-agent-stream.ts`

```typescript
interface UseAgentStreamOptions {
  onMessage?: (message: Message) => void;
  onEvent?: (event: StreamEvent) => void;
  onComplete?: (info?: StreamCompleteInfo) => void;
  onError?: (error: string) => void;
  onDocumentGenerated?: (doc: DocumentInfo) => void;
  onToolUse?: (event: ToolUseEvent) => void;
  onToolResult?: (toolName: string, result: {...}) => void;
  onAgentStatus?: (status: string, detail?: string) => void;
  sessionId?: string;
  packageId?: string;
}
```

---

## 10. Naming Conventions

### 10.1 Artifact Naming
**Pattern:** `{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.{ext}`

| Type | Destination | Example |
|------|-------------|---------|
| `plan` | `.claude/specs/` | `20260217-143000-plan-sdk-signing-v1.md` |
| `pbi` | `.claude/specs/` | `20260217-143000-pbi-frontend-dark-mode-v1.md` |
| `eval` | `server/tests/` | `20260217-160000-eval-sdk-patterns-v1.md` |
| `arch` | `docs/architecture/diagrams/excalidraw/` | `20260222-150000-arch-streaming-v1.excalidraw.md` |
| `report` | `docs/development/` | `20260222-160000-report-cost-v1.md` |

### 10.2 DynamoDB Key Prefixes

| Prefix | Entity | Scope |
|--------|--------|-------|
| `SESSION#` | Conversations | Per tenant+user |
| `MSG#` | Messages | Per session |
| `USAGE#` | Token usage | Per tenant |
| `COST#` | Cost metrics | Per tenant |
| `SUB#` | Subscription | Per tenant |
| `DOCUMENT#` | Versioned docs | Per tenant |
| `PACKAGE#` | Acq packages | Per tenant |
| `APPROVAL#` | Approval chains | Per tenant |
| `WORKSPACE#` | Prompt envs | Per tenant+user |
| `TEMPLATE#` | Custom templates | Per tenant |
| `PLUGIN#` | Runtime plugins | Global |
| `SKILL#` | Custom skills | Per tenant |
| `FEEDBACK#` | User feedback | Per tenant |
| `AUDIT#` | Event log | Per tenant |
| `TRACE#` | Telemetry | Per tenant |
| `AGG#` | Daily rollups | Per tenant |
| `TENANT#` | GSI prefix | Cross-entity |

### 10.3 Session ID Format
`{tenant_id}-{tier}-{user_id}-{session_id}`

### 10.4 Message ID Format
`{timestamp_ms}-{md5_hash8}`

### 10.5 Frontend Type Conventions

| Convention | Examples |
|------------|---------|
| Enum types | `type UserRole = 'co' \| 'cor' \| ...` |
| Status types | `WorkflowStatus`, `DocumentStatus`, `ChecklistStepStatus` |
| Interfaces | `ChatMessage`, `StreamEvent`, `DocumentInfo` |
| Hooks | `useAgentStream`, `useAuth`, `useSession` |

---

## 11. Compliance Matrix

### 11.1 Entity → Store → Key Pattern

| Entity | Store File | PK Pattern | SK Pattern | GSIs Used |
|--------|-----------|------------|------------|-----------|
| Session | `session_store.py` | `SESSION#{tid}#{uid}` | `SESSION#{sid}` | GSI1 |
| Message | `session_store.py` | `SESSION#{tid}#{uid}` | `MSG#{sid}#{mid}` | — |
| Usage | `session_store.py` | `USAGE#{tid}` | `USAGE#{date}#{sid}#{ts}` | — |
| Cost | `session_store.py` | `COST#{tid}` | `COST#{date}#{ts}` | — |
| Subscription | `session_store.py` | `SUB#{tid}` | `SUB#{tier}#current` | — |
| Document | `document_store.py` | `DOCUMENT#{tid}` | `DOCUMENT#{pkg}#{type}#{ver}` | GSI1 |
| Package | `package_store.py` | `PACKAGE#{tid}` | `PACKAGE#{pid}` | GSI1 |
| Approval | `approval_store.py` | `APPROVAL#{tid}` | `APPROVAL#{pid}#{step}` | — |
| Workspace | `workspace_store.py` | `WORKSPACE#{tid}#{uid}` | `WORKSPACE#{wid}` | GSI1 |
| Template | `template_store.py` | `TEMPLATE#{tid}` | `TEMPLATE#{type}#{uid}` | GSI1 |
| Plugin | `plugin_store.py` | `PLUGIN#{etype}` | `PLUGIN#{name}` | — |
| Skill | `skill_store.py` | `SKILL#{tid}` | `SKILL#{sid}` | GSI2 |
| Feedback | `feedback_store.py` | `FEEDBACK#{tid}` | `FEEDBACK#{ts}#{fid}` | GSI1 |
| Audit | `audit_store.py` | `AUDIT#{tid}` | `AUDIT#{ts}#{etype}#{ename}` | — |
| Trace | `dynamodb_trace_store.py` | `TRACE#{tid}` | `TRACE#{date}#{trid}` | GSI1 |
| Aggregate | `session_store.py` | `AGG#{tid}` | `DAILY#{date}` | — |

### 11.2 Backend Model → Frontend Type

| Backend (Python) | Frontend (TypeScript) | File |
|------------------|-----------------------|------|
| `ChatMessage` | `ChatMessage` | `types/chat.ts` |
| `ChatResponse` | (inline in hook) | `hooks/use-agent-stream.ts` |
| `StreamEvent` | `StreamEvent` | `types/stream.ts` |
| `SubscriptionTier` | (inline in auth) | `contexts/auth-context.tsx` |
| `TenantContext` | (inline in API call) | `app/api/invoke/route.ts` |
| `DocumentInfo` (tool result) | `DocumentInfo` | `types/chat.ts` |
| `PluginEntity` (admin) | `PluginEntity` | `types/admin.ts` |
| `Workspace` (admin) | `Workspace` | `types/admin.ts` |
| `CustomSkill` (admin) | `CustomSkill` | `types/admin.ts` |

### 11.3 Template System → API → DynamoDB Flow

```
eagle-plugin/data/templates/*.md          ← Canonical markdown templates
eagle-plugin/data/template-metadata/*.json ← Parsed section/placeholder metadata
                        ↓
server/eagle_skill_constants.py           ← Auto-discovery loader
server/app/template_registry.py           ← S3 filename + placeholder mapping
server/app/template_schema.py             ← Section/field parsing
                        ↓
server/app/template_service.py            ← Generation pipeline
  → S3 fetch → DOCX/XLSX population → completeness check
  → fallback: markdown generation
                        ↓
server/app/template_store.py              ← DynamoDB TEMPLATE# CRUD
  → Resolution: user → tenant → global → plugin
                        ↓
client/app/api/templates/                 ← Next.js proxy routes
```

### 11.4 Data TTL Policy

| Entity | TTL |
|--------|-----|
| Sessions | 30 days |
| Traces | 30 days |
| Feedback | 7 years |
| Audit | 7 years |
| Plugins/Skills | 60s in-memory cache (no DynamoDB TTL) |

---

*End of schema inventory report.*
