# CLAUDE.md — Option B: "EAGLE Mission Control"
# Domain-first: acquisition workflows powered by TAC methodology

## EAGLE — Enterprise Acquisition Gateway for Leveraged Execution

Multi-tenant AI platform for government acquisition. Agents handle intake, compliance,
document generation, and review. Humans handle strategy and approval.

This repo is developed agentically. You orchestrate — agents build. (TAC #1)

---

## Ground Rules

1. **Never type application code.** Use experts to plan and build. (TAC #1)
2. **One expert per domain.** Frontend expert doesn't touch CDK. (TAC #6)
3. **Template repeating work.** If you've solved it twice, it's a command. (TAC #3)
4. **Validate everything.** Backend: `ruff` + `pytest`. Frontend: `tsc` + `playwright`. Infra: `cdk synth`. (TAC #5)
5. **Specs before code.** Plans go to `.claude/specs/` with explicit validation commands. (TAC #3)
6. **eagle-plugin/ is the source of truth** for agent and skill definitions. Edit there, not in server code.

---

## Stack at a Glance

| Layer | Tech | Location | Dev Command |
|-------|------|----------|-------------|
| Frontend | Next.js 14, React 18, Tailwind, TypeScript | `client/` | `npm run dev` |
| Backend | FastAPI, Python 3.11, Pydantic | `server/` | `uvicorn app.main:app --reload --port 8000` |
| Infrastructure | CDK 2.x (TypeScript), ECS Fargate | `infrastructure/cdk-eagle/` | `npx cdk synth` |
| Agents | Claude SDK + Bedrock Agent Core | `eagle-plugin/` | N/A (runtime) |
| Database | DynamoDB (single-table design) | `server/app/session_store.py` | AWS Console |
| Auth | Cognito (JWT, tenant claims) | `server/app/cognito_auth.py` | AWS Console |
| CI/CD | GitHub Actions (OIDC → ECS) | `.github/workflows/` | Push to main |
| Tests | Playwright (E2E), pytest (backend) | `client/tests/`, `server/tests/` | See validation |

---

## EAGLE Agent Architecture

```
User → Cognito JWT (tenant_id, tier) → FastAPI → SDK Agentic Service
                                                        │
                                          ┌─────────────┴─────────────┐
                                          │       Supervisor          │
                                          │  (intent + orchestration) │
                                          └─────────┬─────────────────┘
                               ┌────────────────────┼────────────────────┐
                    ┌──────────┴──────────┐  ┌──────┴───────┐  ┌────────┴────────┐
                    │  Specialist Agents  │  │    Skills     │  │  Tool Access    │
                    │  (7 subagents)      │  │  (5 skills)   │  │  (tier-gated)   │
                    └─────────────────────┘  └──────────────┘  └─────────────────┘
```

### Agents (eagle-plugin/agents/)
| Agent | Role | Triggers |
|-------|------|----------|
| **Supervisor** | Orchestrator + intent detection | All queries |
| Legal Counsel | Contract & regulatory analysis | Legal questions |
| Market Intelligence | Market research & pricing | Market data requests |
| Tech Translator | Technical spec validation | Tech review needs |
| Public Interest | Public benefit assessment | Impact analysis |
| Policy Supervisor | Policy compliance oversight | Policy questions |
| Policy Librarian | FAR/DFAR knowledge retrieval | Regulation lookup |
| Policy Analyst | Regulatory analysis | Analysis requests |

### Skills (eagle-plugin/skills/)
| Skill | Purpose | Output |
|-------|---------|--------|
| `oa-intake` | Acquisition intake workflow | Structured intake data |
| `document-generator` | SOW, IGCE, AP, J&A creation | Draft documents |
| `compliance` | FAR/DFAR compliance guidance | Compliance report |
| `knowledge-retrieval` | Policy & precedent search | Relevant precedents |
| `tech-review` | Technical specification validation | Review findings |

---

## Multi-Tenancy Contract

These invariants must hold across ALL code changes:

| Rule | Implementation |
|------|----------------|
| Tenant isolation | Session IDs: `{tenant_id}-{tier}-{user_id}-{session_id}` |
| Feature gating | Subscription tiers: basic (50/day) / advanced (200/day) / premium (1000/day) |
| Cost tracking | Every Bedrock invocation → `COST#{tenant}` in DynamoDB |
| Auth claims | JWT contains: `custom:tenant_id`, `custom:subscription_tier`, `cognito:groups` |
| Data partitioning | DynamoDB PK/SK prefixes: `SESSION#`, `MSG#`, `USAGE#`, `COST#`, `SUB#` |

---

## Development Experts

Nine domain experts with accumulated knowledge. Use them — don't go solo.

### Full-Stack Development
```bash
/experts:frontend:plan "Add document preview modal"     # Next.js, React, Tailwind
/experts:backend:plan "Add batch export endpoint"        # FastAPI, Pydantic, DynamoDB
/experts:claude-sdk:plan "Add new skill to supervisor"   # Agent SDK, tool routing
```

### Infrastructure & Ops
```bash
/experts:aws:plan "Add WAF to ALB"                       # CDK, IAM, ECS
/experts:deployment:plan "Add staging environment"        # Docker, GitHub Actions
/experts:cloudwatch:plan "Add latency P99 alarm"          # Dashboards, metrics
/experts:eval:plan "Add agent accuracy eval"              # Eval framework, traces
```

### Workflow & Methodology
```bash
/experts:tac:plan "Design workflow for feature X"         # TAC methodology
/experts:git:plan "Set up release branching"             # Git workflows
```

### Expert Execution Patterns
```bash
# Quick question (no code changes)
/experts:backend:question "How does session_store handle pagination?"

# Plan + Build + Self-Improve (full TAC cycle)
/experts:frontend:plan_build_improve "Implement dark mode toggle"

# Just update expertise after manual changes
/experts:aws:self-improve
```

---

## Key Files by Concern

### Backend Critical Path
| File | Responsibility |
|------|----------------|
| `server/app/main.py` | FastAPI routes, middleware, CORS |
| `server/app/sdk_agentic_service.py` | Claude SDK agent orchestration (PRIMARY) |
| `server/app/agentic_service.py` | Legacy prompt-injection orchestration |
| `server/app/session_store.py` | DynamoDB single-table CRUD |
| `server/app/cognito_auth.py` | JWT → tenant context extraction |
| `server/app/cost_attribution.py` | Per-tenant cost calculation |
| `server/app/models.py` | Pydantic schemas |
| `server/eagle_skill_constants.py` | Auto-discovery loader for agents/skills |

### Frontend Critical Path
| File | Responsibility |
|------|----------------|
| `client/app/layout.tsx` | Root layout, providers |
| `client/app/chat/page.tsx` | Main chat interface |
| `client/app/admin/` | Admin dashboard pages |
| `client/hooks/use-agent-stream.ts` | SSE streaming hook |
| `client/contexts/auth-context.tsx` | Auth state management |
| `client/types/` | Shared TypeScript types |

### Infrastructure Critical Path
| File | Responsibility |
|------|----------------|
| `infrastructure/cdk-eagle/bin/eagle.ts` | CDK app entry, stack instantiation |
| `infrastructure/cdk-eagle/lib/core-stack.ts` | VPC, Cognito, IAM, S3, DynamoDB |
| `infrastructure/cdk-eagle/lib/compute-stack.ts` | ECS Fargate, ECR, ALB |
| `infrastructure/cdk-eagle/lib/cicd-stack.ts` | GitHub OIDC + deploy role |
| `infrastructure/cdk-eagle/config/environments.ts` | Per-env configuration |

---

## Validation Chain (TAC #5)

```bash
# 1. Backend (Python)
cd server && ruff check app/ && python -m pytest tests/ -v

# 2. Frontend (TypeScript)
cd client && npx tsc --noEmit && npx playwright test

# 3. Infrastructure (CDK)
cd infrastructure/cdk-eagle && npm run build && npx cdk synth --quiet

# 4. Integration (Docker)
docker compose -f deployment/docker-compose.dev.yml up --build

# 5. Post-deploy (CloudWatch)
/experts:eval:question "Check latest eval dashboard metrics"
```

Every PR must pass steps 1-3. Step 4 for integration changes. Step 5 post-deploy.

---

## File Traceability

All generated artifacts are prefixed with a timestamp (`yyyymmdd-hhmmss`) for traceability.
Old files are never overwritten — re-running a plan creates a new timestamped version.

| Artifact | Destination | Example |
|----------|-------------|---------|
| Expert plans | `.claude/specs/` | `20260217-143000-backend-batch-export.md` |
| Expert plan_build_improve | `.claude/specs/` | `20260217-143000-frontend-pbi-dark-mode.md` |
| Context docs | `.claude/context/` | `20260217-150000-cognito-research.md` |
| Eval results | `server/tests/` | `20260217-160000-eval-accuracy.md` |
| Meeting notes | `docs/development/meeting-transcripts/` | `20260217-170000-sprint-review.md` |

**Expert plan output flow**:
```
/experts:backend:plan "Add batch export"
  → writes: .claude/specs/20260217-143000-backend-batch-export.md

/experts:frontend:plan_build_improve "Dark mode toggle"
  → writes plan: .claude/specs/20260217-150000-frontend-pbi-dark-mode.md
  → builds from plan
  → self-improves expertise
```

## Specs Directory

All plans live in `.claude/specs/` with timestamp prefixes. Create via `/experts:{domain}:plan "task"`.

Existing specs cover: CDK architecture, CloudWatch enrichment, Lightsail deployment,
frontend document viewer, smart chat renaming, resource cleanup, and 15+ more.

---

## Context Engineering (R&D)

**Reduce**: This CLAUDE.md < 200 lines (production). No inline documentation walls.
Agent/skill definitions live in `eagle-plugin/`, not duplicated here.

**Delegate**: Use experts for domain knowledge. Use `docs/` for deep reference.
Use `eagle-plugin/` as the single source of truth for agent behavior.

---

## Daily Workflow

```bash
# Start of work — understand what changed
git log --oneline -10
/experts:git:question "Any open PRs?"

# Plan the task
/experts:{domain}:plan "description of what needs to happen"

# Execute with validation
/experts:{domain}:plan_build_improve "the same task"

# Verify
ruff check server/app/ && cd client && npx tsc --noEmit
```
