# CLAUDE.md — Option A: "The Enterprise Agent Platform"
# Multi-tenant Bedrock Agent Core with TAC-driven development

## Identity

**EAGLE** — Multi-Tenant Amazon Bedrock Agent Core Application.
Government acquisition workflow platform: intake → compliance → document generation → review.
Developed exclusively through agentic workflows. You plan, review, and orchestrate — never type code.

---

## TAC Directives

### #1 Stop Coding
You are an agentic orchestrator, not a typist. Use `/experts:{domain}:plan` to plan,
`/experts:{domain}:plan_build_improve` to execute. Direct code editing is a last resort.

### #3 Template Your Engineering
Solved a problem? Template it. Check `.claude/commands/experts/` before starting any task.
If no expert exists for a recurring domain, create one following the ACT-LEARN-REUSE pattern.

### #5 Always Add Feedback Loops
Every change validates through: `ruff` (Python) → `tsc --noEmit` (TypeScript) → `pytest` (backend) → `playwright test` (E2E).
No PR ships without passing the full validation chain.

### #6 One Agent, One Prompt, One Purpose
Each expert in `.claude/commands/experts/` owns exactly one domain.
Don't ask the frontend expert about CDK. Don't ask the AWS expert about React hooks.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Client (Next.js 14 / TypeScript / Tailwind)                │
│  App Router: /chat, /chat-advanced, /documents, /admin      │
│  Port: 3000                                                 │
├─────────────────────────────────────────────────────────────┤
│  Server (FastAPI / Python 3.11+)                            │
│  Orchestration: sdk_agentic_service.py (Claude SDK)         │
│  Auth: Cognito JWT → tenant_id + subscription_tier          │
│  Storage: DynamoDB single-table (SESSION#, MSG#, COST#)     │
│  Port: 8000                                                 │
├─────────────────────────────────────────────────────────────┤
│  Infrastructure (CDK TypeScript)                            │
│  Stacks: core → compute → cicd → eval                      │
│  Services: ECS Fargate, Cognito, DynamoDB, S3, CloudWatch   │
├─────────────────────────────────────────────────────────────┤
│  EAGLE Plugin (eagle-plugin/)                               │
│  Supervisor → 7 Subagents → 5 Skills                       │
│  Domain: FAR/DFAR compliance, SOW/IGCE/AP generation        │
└─────────────────────────────────────────────────────────────┘
```

---

## File Organization

```
sample-multi-tenant-agent-core-app/
├── CLAUDE.md                 ← Agentic layer config (this file, < 200 lines)
├── client/                   ← Next.js frontend
│   ├── app/                  ← Pages (chat, admin, documents, workflows)
│   ├── components/           ← React components (agents, chat, forms, ui)
│   ├── hooks/                ← Custom hooks (agent-stream, expertise, mcp)
│   ├── lib/                  ← Utilities (conversation-store, template-hydration)
│   ├── types/                ← TypeScript definitions
│   └── tests/                ← Playwright E2E specs
├── server/                   ← FastAPI backend
│   ├── app/                  ← Application modules
│   │   ├── main.py           ← Entry point & route definitions
│   │   ├── sdk_agentic_service.py  ← Claude SDK orchestration (PRIMARY)
│   │   ├── session_store.py  ← DynamoDB single-table access
│   │   ├── cognito_auth.py   ← JWT extraction & validation
│   │   ├── cost_attribution.py    ← Per-tenant cost tracking
│   │   └── models.py         ← Pydantic models
│   └── tests/                ← Backend tests + eval suite
├── infrastructure/
│   └── cdk-eagle/            ← PRIMARY CDK stacks (TypeScript)
│       ├── lib/              ← core, compute, cicd, eval stacks
│       └── config/           ← Per-environment settings
├── eagle-plugin/             ← Agent/skill definitions (YAML frontmatter + markdown)
│   ├── agents/               ← 8 agents (supervisor + 7 specialists)
│   ├── skills/               ← 5 skills (intake, docs, compliance, retrieval, review)
│   └── plugin.json           ← Plugin manifest
├── deployment/               ← Docker + deploy scripts
├── docs/                     ← Architecture docs, meeting notes, plans
└── .claude/                  ← Agentic layer
    ├── commands/experts/     ← 9 domain experts (ACT-LEARN-REUSE)
    ├── skills/               ← Claude IDE skills
    └── specs/                ← Implementation specifications
```

---

## Expert System (ACT-LEARN-REUSE)

Each expert accumulates domain knowledge. Never edit expertise files manually — run `self-improve`.

| Expert | Domain | When to Use |
|--------|--------|-------------|
| `/experts:frontend:*` | Next.js, React, Tailwind, Playwright | UI changes, component work |
| `/experts:backend:*` | FastAPI, Pydantic, DynamoDB, auth | API routes, services |
| `/experts:aws:*` | CDK stacks, IAM, ECS, Cognito | Infrastructure changes |
| `/experts:claude-sdk:*` | Agent SDK, tool definitions, streaming | Agent orchestration |
| `/experts:deployment:*` | Docker, GitHub Actions, ECS deploy | CI/CD, releases |
| `/experts:eval:*` | CloudWatch, dashboards, alarms, evals | Observability, testing |
| `/experts:cloudwatch:*` | Metrics, logs, enriched events | Monitoring |
| `/experts:git:*` | Branching, PRs, workflow | Version control |
| `/experts:tac:*` | TAC methodology, ADW design | Meta-agentic planning |

### Expert Lifecycle
```
/experts:{domain}:question           → Query accumulated expertise
/experts:{domain}:plan "task"        → Domain-aware implementation plan
/experts:{domain}:plan_build_improve → Full cycle: plan → build → self-improve
/experts:{domain}:self-improve       → Validate expertise against codebase
```

---

## Multi-Tenancy Rules

When modifying tenant-aware code:
- **Session IDs** follow format: `{tenant_id}-{tier}-{user_id}-{session_id}`
- **DynamoDB keys** use single-table design: `SESSION#`, `MSG#`, `USAGE#`, `COST#`, `SUB#`
- **Cognito claims**: `custom:tenant_id`, `custom:subscription_tier`, `cognito:groups`
- **Subscription tiers** gate features: basic (50/day), advanced (200/day), premium (1000/day)
- **Cost attribution** must be tracked per-tenant AND per-user

---

## EAGLE Plugin Agent Hierarchy

```
Supervisor (orchestrator + intent detection)
├── Legal Counsel         — Contract/regulatory analysis
├── Market Intelligence   — Market research & pricing
├── Tech Translator       — Technical spec validation
├── Public Interest       — Public benefit assessment
├── Policy Supervisor     — Policy compliance oversight
├── Policy Librarian      — FAR/DFAR knowledge retrieval
└── Policy Analyst        — Regulatory analysis
```

Skills: `oa-intake`, `document-generator`, `compliance`, `knowledge-retrieval`, `tech-review`

When modifying agents/skills, edit the source in `eagle-plugin/` — that is the single source of truth.

---

## Validation Strategy (TAC #5)

```bash
# Backend
cd server && ruff check app/ && python -m pytest tests/ -v

# Frontend
cd client && npx tsc --noEmit && npx playwright test

# Infrastructure
cd infrastructure/cdk-eagle && npm run build && npx cdk synth --quiet

# Full stack (local)
docker compose -f deployment/docker-compose.dev.yml up --build
```

### Before Every PR
1. Run the appropriate expert's `plan_build_improve` workflow
2. Verify all validation commands pass
3. Check CloudWatch eval dashboard after deploy (`/experts:eval:question`)

---

## File Traceability (Core Principle)

All generated artifacts are prefixed with a timestamp (`yyyymmdd-hhmmss`) for traceability.
This is non-negotiable — it enables chronological auditing, prevents collisions, and
lets you trace any decision back to when and why it was made.

| Artifact | Destination | Naming Convention |
|----------|-------------|-------------------|
| Expert plans | `.claude/specs/` | `yyyymmdd-hhmmss-{domain}-{slug}.md` |
| Expert plan_build_improve | `.claude/specs/` | `yyyymmdd-hhmmss-{domain}-pbi-{slug}.md` |
| Context / research | `.claude/context/` | `yyyymmdd-hhmmss-{topic}.md` |
| Eval results | `server/tests/` | `yyyymmdd-hhmmss-eval-{name}.md` |
| Meeting notes | `docs/development/meeting-transcripts/` | `yyyymmdd-hhmmss-{subject}.md` |

**Rules**:
- Old plans are never overwritten. Re-running a plan creates a new timestamped file.
- Every `/experts:{domain}:plan` outputs to `.claude/specs/` with the timestamp prefix.
- Every `/experts:{domain}:plan_build_improve` also writes its plan phase to `.claude/specs/`.
- The domain name is included in the filename for quick filtering (e.g., `20260217-143000-backend-batch-export.md`).

## Specs & Plans

All implementation plans go to `.claude/specs/` and are prefixed with a timestamp
(`yyyymmdd-hhmmss`) for traceability. Key existing specs:
- `aws-comprehensive-cdk.md` — Full CDK architecture
- `cloudwatch-enriched-events.md` — Observability enrichment
- `lightsail-deployment-plan.md` — Alternative deploy target
- `frontend-document-viewer.md` — Document UI spec
- `smart-chat-renaming.md` — Chat UX improvement

New specs: `/experts:{domain}:plan "description"` → outputs to `.claude/specs/yyyymmdd-hhmmss-{slug}.md`

---

## Quick Reference

```bash
# Plan any task with domain expertise
/experts:backend:plan "Add new API endpoint for X"
/experts:frontend:plan "Build admin panel for Y"
/experts:aws:plan "Add CloudWatch alarm for Z"

# Execute with feedback loops
/experts:backend:plan_build_improve "Implement the endpoint"

# Check what experts know
/experts:claude-sdk:question "How does skill routing work?"

# Local development
cd server && uvicorn app.main:app --reload --port 8000
cd client && npm run dev
```
