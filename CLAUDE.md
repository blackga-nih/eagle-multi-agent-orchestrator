## EAGLE

Multi-tenant Bedrock Agent Core app. Government acquisition domain.
Next.js + FastAPI + CDK + Claude SDK. Developed through TAC methodology.

---

## Constraints

- Specs → `.claude/specs/` (all plans written here with validation commands)
- Agent/skill source of truth → `eagle-plugin/` (not server code)
- Subscription tiers gate features: basic / advanced / premium
- Session ID format: `{tenant_id}-{tier}-{user_id}-{session_id}`
- DynamoDB single-table: `SESSION#`, `MSG#`, `USAGE#`, `COST#`, `SUB#`

## File Traceability

Every generated artifact follows the canonical naming pattern:

```
{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.{ext}
```

| Component | Rule |
|-----------|------|
| `YYYYMMDD-HHMMSS` | Timestamp at generation time. Never omitted. |
| `{type}` | Document type prefix from the Type Registry below. |
| `{slug}` | Kebab-case title, max 5 words, no stop words (the/a/and/of/for). |
| `v{N}` | Version integer starting at `v1`. Increment when regenerating the same type+slug. |
| `{ext}` | `.md` · `.ppt.md` (Marp) · `.excalidraw.md` |

**Type Registry**:

| Type prefix | Content | Destination | Example |
|-------------|---------|-------------|---------|
| `plan` | Expert plans, specs | `.claude/specs/` | `20260217-143000-plan-claude-sdk-signing-v1.md` |
| `pbi` | Plan-build-improve cycles | `.claude/specs/` | `20260217-143000-pbi-frontend-dark-mode-v1.md` |
| `context` | Research, spike notes | `.claude/context/` | `20260217-150000-context-kms-signing-v1.md` |
| `eval` | Eval run results | `server/tests/` | `20260217-160000-eval-sdk-patterns-v1.md` |
| `meeting` | Meeting notes | `docs/development/meeting-transcripts/` | `20260217-170000-meeting-sprint-planning-v1.md` |
| `code-review` | Code review presentations | `docs/development/` | `20260222-143000-code-review-eagle-full-v1.md` |
| `arch` | Architecture reports | `docs/architecture/` | `20260222-150000-arch-eagle-streaming-v1.excalidraw.md` |
| `report` | Generic analysis | `docs/development/` | `20260222-160000-report-cost-attribution-v1.md` |

**Versioning rule**: Before writing, scan the destination directory for files matching
`*-{type}-{slug}-v*.{ext}`. Take the highest `N` found and write `v{N+1}`. If no match, write `v1`.
Old files are never overwritten — every run appends to the chronological audit trail.

**Slug rules**: lowercase · kebab-case · max 5 words · strip stop words (a/an/the/and/or/of/in/to/for/with)

**Scribe is the enforcer** — run `/scribe` to format any report and have the convention applied automatically.
See `.claude/commands/scribe.md` for the full spec.

---

## Primitive Map

> "If you've done it twice, template it. If it needs domain knowledge, make it an expert." — TAC #3

| Signal | Primitive | Location |
|--------|-----------|----------|
| Frontend task | `/experts:frontend:plan` | `.claude/commands/experts/frontend/` |
| Backend task | `/experts:backend:plan` | `.claude/commands/experts/backend/` |
| CDK / AWS task | `/experts:aws:plan` | `.claude/commands/experts/aws/` |
| Agent orchestration | `/experts:claude-sdk:plan` | `.claude/commands/experts/claude-sdk/` |
| Deploy / CI-CD | `/experts:deployment:plan` | `.claude/commands/experts/deployment/` |
| Monitoring | `/experts:cloudwatch:plan` | `.claude/commands/experts/cloudwatch/` |
| Eval / testing | `/experts:eval:plan` | `.claude/commands/experts/eval/` |
| Git workflow | `/experts:git:plan` | `.claude/commands/experts/git/` |
| TAC methodology | `/experts:tac:plan` | `.claude/commands/experts/tac/` |

### Composition Examples
```bash
# Simple: single expert
/experts:backend:plan "Add health check endpoint"

# Composed: expert plans, then executes with self-improvement
/experts:frontend:plan_build_improve "Add dark mode to admin dashboard"

# Cross-domain: chain experts
/experts:claude-sdk:plan "Add document-signing skill"
# → then: /experts:backend:plan "Wire skill to streaming route"
# → then: /experts:frontend:plan "Add signing UI to document viewer"
# → then: /experts:aws:plan "Add KMS key for document signing"
```

---

## Layer Reference

### Frontend (`client/`)

| Concern | Key Files |
|---------|-----------|
| Pages | `app/chat/`, `app/admin/`, `app/documents/`, `app/workflows/` |
| Components | `components/chat/`, `components/agents/`, `components/forms/`, `components/ui/` |
| State | `contexts/auth-context.tsx`, `contexts/session-context.tsx` |
| Hooks | `hooks/use-agent-stream.ts`, `hooks/use-expertise.ts`, `hooks/use-mcp-client.ts` |
| Types | `types/chat.ts`, `types/conversation.ts`, `types/expertise.ts`, `types/mcp.ts` |
| Tests | `tests/*.spec.ts` (Playwright E2E) |
| Templates | `public/templates/` (SOW, IGCE, AP, Market Research) |

**Patterns**: App Router, React Context for state, custom hooks for data fetching,
Zod for form validation, Tailwind for styling, Lucide for icons.

**Validate**: `npx tsc --noEmit && npx playwright test`

---

### Backend (`server/`)

| Concern | Key Files |
|---------|-----------|
| Entry point | `app/main.py` (FastAPI routes, CORS, middleware) |
| Orchestration | `app/sdk_agentic_service.py` (Claude SDK — PRIMARY) |
| Legacy orch | `app/agentic_service.py` (prompt injection — DEPRECATED) |
| Auth | `app/cognito_auth.py` (JWT → tenant context) |
| Storage | `app/session_store.py` (DynamoDB single-table CRUD) |
| Costs | `app/cost_attribution.py` + `app/admin_cost_service.py` |
| Models | `app/models.py` (Pydantic schemas) |
| Streaming | `app/stream_protocol.py` + `app/streaming_routes.py` |
| Doc export | `app/document_export.py` (PDF/Word) |
| Skill loader | `eagle_skill_constants.py` (auto-discovery) |
| Tests | `tests/test_agent_sdk.py`, `tests/test_eagle_sdk_eval.py` |

**Patterns**: Pydantic models for all data, DynamoDB single-table with PK/SK prefixes,
SSE streaming for agent responses, Cognito JWT for multi-tenant auth.

**Validate**: `ruff check app/ && python -m pytest tests/ -v`

---

### Infrastructure (`infrastructure/cdk-eagle/`)

| Stack | Responsibility |
|-------|----------------|
| `core-stack.ts` | VPC, Cognito user pool, IAM roles, S3 buckets, DynamoDB tables |
| `compute-stack.ts` | ECS Fargate services, ECR repos, ALB, target groups |
| `cicd-stack.ts` | GitHub OIDC provider, deploy IAM role |
| `eval-stack.ts` | CloudWatch dashboards, alarms, eval metrics |
| `config/environments.ts` | Per-env settings (CPU, memory, domain, etc.) |

**Environments**: dev (512/1024 MiB) → staging → prod (1024/2048 MiB)

**Validate**: `npm run build && npx cdk synth --quiet`

---

### EAGLE Plugin (`eagle-plugin/`)

Single source of truth for all agent and skill definitions.

```
eagle-plugin/
├── plugin.json              ← Manifest (agent list, skill list)
├── agents/
│   ├── supervisor/agent.md  ← Orchestrator (YAML frontmatter + system prompt)
│   ├── legal-counsel/
│   ├── market-intelligence/
│   ├── tech-translator/
│   ├── public-interest/
│   ├── policy-supervisor/
│   ├── policy-librarian/
│   └── policy-analyst/
├── skills/
│   ├── oa-intake/SKILL.md
│   ├── document-generator/SKILL.md
│   ├── compliance/SKILL.md
│   ├── knowledge-retrieval/SKILL.md
│   └── tech-review/SKILL.md
└── commands/                ← Plugin-specific commands
```

**Format**: Each agent/skill has YAML frontmatter (name, type, triggers, tools) + markdown body.
**Rule**: Modify agents/skills HERE, not in `server/app/`. The server auto-loads from plugin.

---

## Expert System (ACT-LEARN-REUSE)

```
.claude/commands/experts/{domain}/
├── expertise.md|yaml     ← Accumulated mental model (never edit manually)
├── question.md           ← Query the expert (REUSE)
├── plan.md               ← Domain-aware planning (REUSE)
├── plan_build_improve.md ← Full cycle: plan → build → self-improve (ACT → LEARN → REUSE)
└── self-improve.md       ← Validate & update expertise (LEARN)
```

**9 Active Domains**: frontend, backend, aws, claude-sdk, deployment, cloudwatch, eval, git, tac

### When to Create a New Expert
- You've asked the same domain question 3+ times
- A domain has non-obvious patterns that agents keep getting wrong
- You need accumulated knowledge across sessions (not just one-off context)

### Expert Golden Rules
1. Never edit expertise files manually — run `/experts:{domain}:self-improve`
2. Run self-improve after significant changes to that domain's code
3. Each expert validates its knowledge against the actual codebase, not assumptions

---

## Validation Ladder (TAC #5)

```
Level 1 — Lint          ruff check (Python) / tsc --noEmit (TypeScript)
Level 2 — Unit          pytest tests/ (backend) / vitest (if added)
Level 3 — E2E           playwright test (frontend flows)
Level 4 — Infra         cdk synth --quiet (CDK compiles)
Level 5 — Integration   docker compose up --build (full stack)
Level 6 — Eval          CloudWatch dashboard post-deploy metrics
```

| Change Type | Minimum Level |
|-------------|---------------|
| Typo / copy fix | Level 1 |
| Backend logic | Level 1 + 2 |
| Frontend UI | Level 1 + 3 |
| CDK change | Level 1 + 4 |
| Cross-stack feature | Level 1-5 |
| Production deploy | Level 1-6 |

---

## Context Engineering (R&D)

### Reduce
- CLAUDE.md stays under 200 lines (production cut)
- Don't duplicate `eagle-plugin/` content — reference it
- Don't inline architecture diagrams — point to `docs/architecture/`
- Each expert loads its context on invocation, not always-on

### Delegate
- Domain questions → `/experts:{domain}:question`
- Architecture reference → `docs/` directory
- Agent/skill definitions → `eagle-plugin/` (auto-loaded by server)
- Implementation specs → `.claude/specs/`
- Meeting context → `docs/development/meeting-transcripts/`

---

## Maturity Tracker

| Workflow | Current Level | Target |
|----------|---------------|--------|
| Frontend features | In-Loop | Out-Loop |
| Backend endpoints | Out-Loop | Out-Loop |
| CDK changes | In-Loop | Out-Loop |
| Agent skill additions | In-Loop | Out-Loop |
| Bug fixes | Out-Loop | Zero-Touch |
| Eval runs | Out-Loop | Zero-Touch |

**Graduation path**: In-Loop (3+ successes) → Template as command → Add validation → Out-Loop ADW → Zero-Touch
