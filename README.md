# EAGLE — Enhanced Acquisition Guidance & Lifecycle Engine

![CI](https://github.com/CBIIT/sm_eagle/actions/workflows/deploy.yml/badge.svg)
![Nightly Triage](https://github.com/CBIIT/sm_eagle/actions/workflows/nightly-triage.yml/badge.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js 15](https://img.shields.io/badge/Next.js-15-black.svg)
![Strands Agents SDK](https://img.shields.io/badge/Strands_Agents-SDK-orange.svg)
![License: NCI Internal](https://img.shields.io/badge/license-NCI_Internal-lightgrey.svg)

A multi-tenant AI acquisition assistant for the **NCI Office of Acquisitions**. EAGLE helps contracting officers navigate the federal procurement lifecycle — intake, FAR/DFARS guidance, compliance matrix routing, and document generation (SOW, IGCE, AP, J&A, SON). Built on the **Strands Agents SDK** with a supervisor + specialist subagent architecture, served through **Amazon Bedrock** (Claude Sonnet 4.6 / Haiku 4.5), fronted by a **Next.js** chat UI with SSE streaming, and observable end-to-end via **Langfuse**.

> **Quick links:** [Architecture](#architecture) · [Quick Start](#quick-start) · [Eval & Observability](#evaluation--observability) · [Infrastructure](docs/infra.md) · [Weekly Changelog](docs/development/weekly-changelog.md) · [Codebase Structure](docs/codebase-structure.md)

---

## Table of Contents

- [What EAGLE is](#what-eagle-is)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Common Commands](#common-commands)
- [Validation Ladder](#validation-ladder)
- [Evaluation & Observability](#evaluation--observability)
  - [Langfuse](#langfuse)
  - [Eval suite (142 tests)](#eval-suite-142-tests)
  - [Baseline-questions skill](#baseline-questions-skill)
  - [MVP1 eval 4-tier ladder](#mvp1-eval-4-tier-ladder)
  - [E2E judge (vision-based QA)](#e2e-judge-vision-based-qa)
  - [Nightly triage](#nightly-triage)
- [Weekly Changelog Highlights](#weekly-changelog-highlights)
- [CI/CD Pipeline](#cicd-pipeline)
- [API Reference](#api-reference)
- [Authentication & Multi-Tenancy](#authentication--multi-tenancy)
- [Data Model](#data-model)
- [Contributing](#contributing)

---

## What EAGLE is

EAGLE (Enhanced Acquisition Guidance & Lifecycle Engine) uses a **supervisor + subagent** architecture powered by the **Strands Agents SDK** over `BedrockModel`. The supervisor routes each turn to the right specialist based on intent, and each specialist receives a fresh per-call context window for cleaner multi-step workflows.

**Key design choices:**
- **Single orchestration path:** [`server/app/strands_agentic_service.py`](server/app/strands_agentic_service.py) is the only active service. The legacy `agentic_service.py` and `sdk_agentic_service.py` were deleted in [`ed61255`](https://github.com/CBIIT/sm_eagle/commit/ed61255) (-5,500 lines).
- **Plugin as source of truth:** All agent prompts + skills live in [`eagle-plugin/`](eagle-plugin/) and are auto-discovered at startup via YAML frontmatter. Never edit agent content in `server/app/`.
- **KB-first cascade enforced:** Supervisor must consult the knowledge base + compliance matrix before falling back to web search. This was [a 79% violation rate before it was hard-enforced](https://github.com/CBIIT/sm_eagle/commit/c51a346) based on Langfuse trace analysis.
- **Model resilience:** 4-model circuit breaker (Sonnet 4.6 → 4.5 → 4.0 → Haiku 4.5 → Nova Pro) with 45s TTFT timeout and automatic fallback. See [`ModelCircuitBreaker`](server/app/strands_agentic_service.py) and [`docs/infra.md §5`](docs/infra.md#5-model-providers--circuit-breaker).
- **Everything observable:** Every agent turn, tool call, and cost is traced to Langfuse; errors are auto-classified; nightly triage job cross-references Langfuse + CloudWatch + DynamoDB feedback.

<details>
<summary><strong>Important disclaimers</strong></summary>

This is an active, internal NCI application — not a reference sample. When deploying to production:
- Run comprehensive security review + penetration testing
- Enable [Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html) for content filtering, denied topics, PII redaction, and contextual grounding
- Review AWS's [Responsible AI practices](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/responsible-ai.html) before exposing automated AWS operations to end users
- Validate tenant isolation boundaries in the DynamoDB access layer ([`server/app/session_store.py`](server/app/session_store.py))
</details>

---

## Architecture

```
┌──────────────────────────────────────── AWS Cloud ────────────────────────────────────────┐
│                                                                                              │
│  ┌────────┐     ┌────────────────────────┐    SSE / REST   ┌─────────────────────────────┐  │
│  │ Users  │─────│   Next.js Frontend     │◀───────────────▶│    FastAPI Backend          │  │
│  └───┬────┘     │   App Router · TS      │                 │   streaming_routes.py       │  │
│      │ JWT     │   (ECS Fargate)        │                 │   strands_agentic_service.py│  │
│      │         └────────────────────────┘                 └──────────────┬──────────────┘  │
│      │                                                                   │                 │
│  ┌───▼────────┐                                                          │ Strands SDK     │
│  │  Cognito   │                                                          ▼                 │
│  │  tenant_id │                                              ┌─────────────────────┐       │
│  │  user_id   │                                              │  Supervisor Agent   │       │
│  │  tier      │                                              └──────────┬──────────┘       │
│  └────────────┘                                                         │                  │
│                                    ┌────────┬─────────┬─────────┬───────┼─────────┬──────┐ │
│                                    ▼        ▼         ▼         ▼       ▼         ▼      ▼ │
│                                 legal-  market-    tech-     public-  policy-*  oa-   doc- │
│                                 counsel intel      translator interest (3x)    intake gen  │
│                                                                                              │
│                                         ▼  Amazon Bedrock                                   │
│                                   Claude Sonnet 4.6 / Haiku 4.5                              │
│                                                                                              │
│  ┌───────────────────────────┐   ┌─────────────────────────┐   ┌───────────────────────┐    │
│  │        DynamoDB           │   │          S3             │   │       Langfuse        │    │
│  │  SESSION# · MSG# · USAGE# │   │  eagle-documents-*      │   │  OTEL exporter        │    │
│  │  PACKAGE# · TEMPLATE#     │   │  eagle-eval-artifacts-* │   │  us.cloud.langfuse.com│    │
│  │  FEEDBACK# · AUDIT# · ... │   │  nci-documents (import) │   │  trace + error class  │    │
│  └───────────────────────────┘   └─────────────────────────┘   └───────────────────────┘    │
│                                                                                              │
│   CloudWatch Logs/Metrics · SNS alerts · Nightly triage · Feedback→JIRA→Teams pipeline      │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

> **Interactive diagrams** — see [`docs/architecture/diagrams/excalidraw/`](docs/architecture/diagrams/excalidraw/) (AWS arch, CDK stacks, GitHub Actions deploy, validation workflow) and [`docs/architecture/diagrams/mermaid/`](docs/architecture/diagrams/mermaid/) (UC01 happy path, UC02 micro-purchase, UC04 contract modification, full skill chain, etc.).

### Request flow

1. **User → Cognito → JWT** carries `tenant_id`, `user_id`, `subscription_tier`
2. **Frontend → `/api/chat/stream`** (SSE) — proxied by Next.js, terminated at FastAPI backend
3. **FastAPI → Strands `sdk_query_streaming()`** — wraps the call in a Langfuse parent span, routes to the supervisor agent
4. **Supervisor → specialist subagent** via `@tool` dispatch with a fresh context window (one of 7 specialists + document-generator)
5. **Specialist → Bedrock** via `BedrockModel` (circuit breaker picks best healthy model)
6. **Streamed response** → `MultiAgentStreamWriter` → SSE events (`text`, `tool_use`, `tool_result`, `agent_status`, `state_update`, `complete`, `error`) → [`use-agent-stream.ts`](client/hooks/use-agent-stream.ts) hook on the frontend
7. **Session + cost + reasoning** persisted to DynamoDB; trace mirrored to Langfuse

### EAGLE plugin contents

Loaded from [`eagle-plugin/`](eagle-plugin/) at startup via [`server/eagle_skill_constants.py`](server/eagle_skill_constants.py). Contents verified from [`plugin.json`](eagle-plugin/plugin.json):

| Type | Count | Names |
|---|---|---|
| **Supervisor** | 1 | `supervisor` — intent detection + routing |
| **Specialist agents** | 7 | `legal-counsel`, `market-intelligence`, `tech-translator`, `public-interest`, `policy-supervisor`, `policy-librarian`, `policy-analyst` |
| **Skills** | 8 | `oa-intake`, `document-generator`, `compliance`, `knowledge-retrieval`, `tech-review`, `ingest-document`, `admin-manager`, `admin-diagnostics` |
| **Data artifacts** | 4 | `far-database.json`, `thresholds.json`, `contract-vehicles.json`, `matrix.json` |

Full infrastructure, services, tables, buckets, env vars, and model chain lives in **[`docs/infra.md`](docs/infra.md)**.

---

## Project Structure

```
.
├── README.md                  ← you are here
├── CLAUDE.md                  ← agent-facing repo guide
├── Justfile                   ← canonical task runner (~80 recipes)
├── client/                    ← Next.js 15 frontend (App Router, TS, Tailwind)
│   ├── app/                   ← 25 pages incl. 15 /admin sub-pages
│   ├── components/            ← 75 components (chat-simple, admin, packages, …)
│   ├── hooks/use-agent-stream.ts  ← SSE consumer
│   └── lib/
├── server/                    ← FastAPI + Strands SDK backend
│   ├── app/
│   │   ├── main.py
│   │   ├── strands_agentic_service.py   ← active orchestration (only one)
│   │   ├── streaming_routes.py          ← SSE endpoint
│   │   ├── routers/                     ← 18 FastAPI routers
│   │   ├── tools/                       ← 17 Strands tool modules
│   │   ├── telemetry/                   ← 12 telemetry modules (incl. Langfuse)
│   │   ├── *_store.py                   ← 19 DDB entity stores
│   │   └── cost_attribution.py
│   └── tests/                 ← 94 test files, 1,121 collected tests + eval suite
├── eagle-plugin/              ← agent/skill source of truth
│   ├── plugin.json
│   ├── agents/                ← 8 agents (supervisor + 7 specialists)
│   ├── skills/                ← 8 skills w/ YAML frontmatter
│   └── data/                  ← FAR db, thresholds, vehicles, matrix
├── infrastructure/cdk-eagle/  ← 6 CDK stacks (Core, Storage, Compute, CiCd, Eval, Backup)
│   ├── lib/                   ← stack definitions
│   ├── config/environments.ts ← dev/qa/staging/prod config
│   └── scripts/bundle-lambda.py
├── deployment/                ← Dockerfile.backend, Dockerfile.frontend, docker-compose.dev.yml
├── docs/
│   ├── infra.md               ← services + AWS + env vars (canonical)
│   ├── codebase-structure.md
│   ├── architecture/          ← Excalidraw + Mermaid diagrams
│   ├── development/
│   │   ├── weekly-changelog.md          ← full week-by-week history
│   │   ├── ro-vs-eagle-search-comparison.md
│   │   └── *-report-triage-*.md         ← nightly triage outputs
│   ├── deployment/            ← production validation checklist
│   └── setup/                 ← local-development, ec2-runner, cdk-bootstrap
├── .claude/
│   ├── skills/baseline-questions/       ← baseline eval runner (Q1–Q14)
│   ├── skills/mvp1-eval/                ← 4-tier eval ladder
│   ├── skills/e2e-judge/                ← Playwright + Bedrock vision QA
│   └── skills/triage/                   ← unified diagnostic skill
└── .github/workflows/         ← deploy, nightly-triage, eval, feedback-approved, jira-sync
```

---

## Quick Start

### Prerequisites

- **Python 3.11+** (3.12 tested), **Node.js 20+**, **Docker**
- **[just](https://github.com/casey/just)** task runner — `cargo install just` or `brew install just`
- **AWS CLI** with profile `eagle` (NCI SSO, `NCIAWSPowerUserAccess`)
- **AWS SSO login** before starting the backend (the Bedrock startup probes will trip the circuit breaker without creds):
  ```bash
  aws sso login --profile eagle
  ```

### Local development

```bash
# Install Python + Node deps (one-time)
cd server && pip install -r requirements.txt && cd ..
cd client && npm install && cd ..

# Option A: full Docker Compose stack
just dev                     # or: just dev-up-sso eagle

# Option B: run services individually (hot reload)
just dev-backend             # FastAPI at http://localhost:8000
just dev-frontend            # Next.js at http://localhost:3000

# Option C: both foreground locally (kills stale processes)
just dev-local-sso eagle
```

**Required environment variables** — see [`docs/infra.md §7`](docs/infra.md#7-env-vars) for the complete list. Minimum for local:

```bash
# server/.env
AWS_REGION=us-east-1
AWS_PROFILE=eagle
EAGLE_SESSIONS_TABLE=eagle
S3_BUCKET=eagle-documents-695681773636-dev
ANTHROPIC_API_KEY=sk-ant-...   # fallback
DEV_MODE=true                  # local only — bypasses Cognito

# Langfuse (required for traces — NOT in .env.example, add manually)
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PROJECT_ID=cmmsqvi2406aead071t0zhl7f
```

> **⚠️ Known gap:** `.env.example` at the repo root currently **does not include the Langfuse vars**. Copy them from a colleague's `server/.env` or the Langfuse project settings until this is fixed.

### Standard deployment (GitHub Actions)

Push to `main` → [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) runs:
1. OIDC auth to AWS (via `DEPLOY_ROLE_ARN` secret → `EagleCiCdStack` role)
2. `cdk deploy --all` (all 6 stacks)
3. Docker build + ECR push (backend + frontend)
4. ECS rolling update + health verify (`/api/health` + `/`)

Full CI/CD details in [§CI/CD Pipeline](#cicd-pipeline).

### Manual deploy from the EC2 devbox

```bash
# From your laptop, SSM into the devbox (no SSH keys):
just devbox-start              # if stopped
aws ssm start-session --target i-0390c06d166d18926 --profile eagle --region us-east-1

# On the devbox:
cd /home/eagle/eagle
just deploy                    # build → ECR push → ECS rolling update → wait
just check-aws                 # verify 8 resources healthy
```

---

## Common Commands

All routed through [`Justfile`](Justfile). Run `just --list` to see every recipe.

```bash
# ─── Development ──────────────────────────────────────────────
just dev                   # Docker Compose (foreground)
just dev-up-sso eagle      # Docker Compose detached + SSO creds
just dev-local             # Local uvicorn + Next.js (kills stale)
just dev-backend           # Backend only (port 8000)
just dev-frontend          # Frontend only (port 3000)

# ─── Lint / format ────────────────────────────────────────────
just lint                  # ruff (py) + tsc (ts)
just lint-py               # python -m ruff check app/
just lint-ts               # npx tsc --noEmit
just format                # ruff format + prettier
just format-check          # verify formatted

# ─── Tests ────────────────────────────────────────────────────
just test                  # backend pytest (excludes test_strands_eval.py)
just test-e2e              # Playwright against Fargate (headless)
just test-e2e-ui           # Playwright headed
just smoke                 # base: nav + home (~14s)
just smoke mid             # all pages (~22s)
just smoke full            # all pages + chat (~27s)
just smoke-prod            # mid against Fargate ALB

# ─── Eval suite ───────────────────────────────────────────────
just eval                  # full eval driver (test_strands_eval.py, haiku 4.5)
just eval-quick 1,2        # specific tests
just eval-aws              # AWS tool tests only (16-20)

# ─── Build / deploy ───────────────────────────────────────────
just build                 # Docker build backend + frontend
just deploy                # full: build → ECR → ECS rolling → wait
just deploy-backend        # backend only
just deploy-frontend       # frontend only
just deploy-qa             # to QA environment
just ship                  # lint + CDK synth gate + deploy + smoke-prod verify

# ─── Infrastructure ───────────────────────────────────────────
just cdk-synth             # compile CDK (L4 gate)
just cdk-diff              # preview changes
just cdk-deploy            # deploy all 6 stacks
just cdk-deploy-storage    # storage stack only

# ─── Operations ───────────────────────────────────────────────
just check-aws             # verify AWS connectivity (8 resources)
just check-sso             # verify SSO login
just aws-login eagle       # aws sso login --profile eagle
just devbox-start / stop   # EC2 devbox power
just devbox-health         # health check from inside VPC
just devbox-logs           # tail ECS logs
just devbox-ship           # deploy from devbox (standard path)

# ─── Composite gates ──────────────────────────────────────────
just ci                    # L1 + L2 + L4 + L6 eval-aws
just validate              # L1–L5: full local gate
just validate-full         # L1–L6: + full eval suite
```

> **Windows note:** the `ruff` binary may not be on PATH. Use `python -m ruff check app/` (what `just lint-py` does internally) or install ruff into a venv with `Scripts/` on PATH.

---

## Validation Ladder

Every change type has a minimum required gate. All runnable via `just`.

| Level | Gate | Command | When |
|---|---|---|---|
| **L1 — Lint** | `python -m ruff check app/` + `tsc --noEmit` | `just lint` | Every change |
| **L2 — Unit** | `pytest server/tests/` (excludes eval driver) | `just test` | Backend logic |
| **L3 — E2E smoke** | Playwright against local stack | `just smoke mid` | Frontend / UI |
| **L4 — Infra** | `cdk synth --quiet` | `just cdk-synth` | CDK changes |
| **L5 — Integration** | Docker Compose + smoke | `just validate` | Before any PR |
| **L6 — Eval** | 142-test [`test_strands_eval.py`](server/tests/test_strands_eval.py) | `just eval` | Before merge to main |

| Change type | Minimum |
|---|---|
| Typo / copy | L1 |
| Backend logic | L1 + L2 |
| Frontend UI | L1 + L3 |
| CDK change | L1 + L4 |
| Cross-stack feature | L1–L5 |
| Merge to main | L1–L6 |

> **Note about `pytest server/tests/`:** [`test_strands_eval.py`](server/tests/test_strands_eval.py) parses CLI args at module import time, so a plain `pytest server/tests/` will abort collection. `just test` correctly adds `--ignore=tests/test_strands_eval.py`; run eval via `just eval` separately.

---

## Evaluation & Observability

EAGLE has five layered quality tools: **Langfuse traces**, the **142-test Strands eval**, the **baseline-questions** skill, the **MVP1 4-tier ladder**, and the **E2E judge** for visual QA. Plus nightly triage that cross-references everything.

### Langfuse

Primary observability backend — every agent turn, subagent handoff, tool call, and cost is a span.

- **Host:** [`https://us.cloud.langfuse.com`](https://us.cloud.langfuse.com)
- **Dev project:** [`cmmsqvi2406aead071t0zhl7f`](https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f)
- **ARTI secondary project:** [`cmmtw4vjq026kad07iu2y1nuc`](https://us.cloud.langfuse.com/project/cmmtw4vjq026kad07iu2y1nuc)
- **In-app admin viewer:** [`client/app/admin/traces/page.tsx`](client/app/admin/traces/page.tsx) — navigate to `/admin/traces` in EAGLE (admin tier only), shows live trace summaries with cost, duration, error classification, and deep links to the Langfuse UI
- **Admin diagnostic command:** the `/admin` slash command in the chat queries Langfuse traces directly ([`0909667`](https://github.com/CBIIT/sm_eagle/commit/0909667))

**Langfuse integration source files:**

| File | Role |
|---|---|
| [`server/app/telemetry/langfuse_client.py`](server/app/telemetry/langfuse_client.py) | REST client: `list_traces`, `get_trace`, `list_observations`, `tag_trace_error`, `classify_error` (severity = infra / config / app) |
| [`server/app/strands_agentic_service.py`](server/app/strands_agentic_service.py) | OTEL exporter setup + parent-span wrap fix for Strands context detach ([`875294f`](https://github.com/CBIIT/sm_eagle/commit/875294f)) |
| [`server/app/routers/admin.py`](server/app/routers/admin.py) | `/api/admin/traces` endpoint consumed by the frontend |
| [`server/app/telemetry/conversation_scorer.py`](server/app/telemetry/conversation_scorer.py) | LLM-as-judge conversation quality scoring (feeds Langfuse scores) |
| [`server/tests/eval_helpers.py`](server/tests/eval_helpers.py) | `LangfuseTraceValidator` — eval suite assertion helper |
| [`.github/workflows/nightly-triage.yml`](.github/workflows/nightly-triage.yml) | Queries Langfuse REST for 24h error window |

**Trace + user identity:** Cognito username is used as the Langfuse `userId` ([`1f948d3`](https://github.com/CBIIT/sm_eagle/commit/1f948d3)) so every trace is filterable by operator.

**Error classification** ([`61506d8`](https://github.com/CBIIT/sm_eagle/commit/61506d8)) tags each failed trace with one of: `infra` (Bedrock timeout, 5xx, circuit breaker), `config` (missing env var, bad credential), or `app` (logic bug, assertion fail). The nightly triage workflow uses this to prioritize P0/P1/P2 fixes.

### Eval suite (142 tests)

**File:** [`server/tests/test_strands_eval.py`](server/tests/test_strands_eval.py) — the source of truth for agent behavior. **Default model:** `us.anthropic.claude-haiku-4-5-20251001-v1:0` (cost-optimized).

| Range | Category |
|---|---|
| **1–6** | SDK patterns (session creation, resume, context, traces, cost, subagents) |
| **7–15** | Skill validation (OA intake, legal, market, tech, public, doc-gen, supervisor chain) |
| **16–20** | AWS tool integration (S3, DynamoDB, CloudWatch, doc gen, CW E2E) |
| **21–27** | MVP2/3 UC workflows (micro-purchase, option exercise, contract mod, CO review, closeout, shutdown, score consolidation) |
| **28** | Strands skill → tool orchestration |
| **29–42** | Admin/store validation + MVP1 UC coverage |
| **43–55** | Skill behavior + trace/observability |
| **56–72** | Tool sanity + UC end-to-end |
| **73–98** | Document generation, context/prompt integrity, persistence, Langfuse assertions |
| **99–107** | Full package + exports (ZIP/DOCX/PDF) + versioning |
| **108–128** | Guardrails + content validation |
| **129–137** | Multi-turn UC flows |
| **138–142** | Jira QA validation (EAGLE-70 / 72 / 73 / 74 / 76) |

```bash
just eval                      # full suite (Haiku)
just eval-quick 1,2            # specific tests
just eval-aws                  # AWS tool tests (16-20)

# Run the driver directly with args:
python server/tests/test_strands_eval.py --tests 1,2,5 --model claude-sonnet-4-6
```

> **Heads-up:** `test_strands_eval.py` calls `argparse.parse_args()` at module import time (line 136). That means `pytest server/tests/ --collect-only` over the whole tree will exit 2. Always run eval via `just eval*` or invoke the file directly with args.

### Baseline-questions skill

**Location:** [`.claude/skills/baseline-questions/`](.claude/skills/baseline-questions/). Runs all 14 baseline acquisition questions from [`Use Case List.xlsx`](Use%20Case%20List.xlsx) against the running backend, judges responses, and generates an HTML comparison report against prior versions.

- **Runner:** [`.claude/skills/baseline-questions/scripts/run_baseline.py`](.claude/skills/baseline-questions/scripts/run_baseline.py)
- **Report generator:** [`.claude/skills/baseline-questions/scripts/generate_report.py`](.claude/skills/baseline-questions/scripts/generate_report.py)
- **Questions source:** column D of the "Baseline questions" sheet in `Use Case List.xlsx`
- **Latest scores:** V9 = **250/260** across 13 questions ([`fc71160`](https://github.com/CBIIT/sm_eagle/commit/fc71160)); V6 = **19.5/20 avg** with no regressions ([`8d5016f`](https://github.com/CBIIT/sm_eagle/commit/8d5016f))
- **Q14** specifically tests the Zeiss brand-name justification / GSA scenario ([`e02e403`](https://github.com/CBIIT/sm_eagle/commit/e02e403))

```bash
# From repo root, with backend running at localhost:8000:
python .claude/skills/baseline-questions/scripts/run_baseline.py --version v10
python .claude/skills/baseline-questions/scripts/run_baseline.py --version v10 --questions 13,14
python .claude/skills/baseline-questions/scripts/run_baseline.py --version v10 --judge-only
```

### MVP1 eval 4-tier ladder

**Location:** [`.claude/skills/mvp1-eval/`](.claude/skills/mvp1-eval/). The ladder gates at each tier:

| Tier | Category | Purpose | ~Time |
|---|---|---|---|
| **Tier 1** | Fast unit pytest (compliance_matrix, KB flow, package flow) | Regression detection | ~30s |
| **Tier 2** | Live Strands + Bedrock integration | Service integration | ~5m |
| **Tier 3** | Full 142-test `test_strands_eval.py` | Full agentic stack | ~30m |
| **Tier 4a** | Playwright structural specs (nav, home, admin, documents) | UI integrity | ~2m |
| **Tier 4-live** | Streaming + tool UI flows | Real-time UX | ~5m |
| **Tier 4b** | E2E judge (screenshot + Bedrock vision) | UI quality + correctness | ~10m |

Repo-specific config in [`.claude/skills/mvp1-eval/config.json`](.claude/skills/mvp1-eval/config.json) — binds AWS account, S3 bucket, Langfuse project IDs, and tier test paths to the `sm_eagle` repo key.

### E2E judge (vision-based QA)

**Location:** [`.claude/skills/e2e-judge/`](.claude/skills/e2e-judge/). LLM-as-judge screenshot validation.

- **Orchestrator:** [`server/tests/e2e_judge_orchestrator.py`](server/tests/e2e_judge_orchestrator.py)
- **Journey definitions:** [`server/tests/e2e_judge_journeys.py`](server/tests/e2e_judge_journeys.py) (login, home, chat, admin, packages)
- **Pipeline:** Playwright captures screenshots → `VisionJudge` (Bedrock Sonnet converse) evaluates → SHA-256 cache skips unchanged shots → JSON + Markdown reports
- **Vision model:** `E2E_JUDGE_MODEL` env var (default Sonnet); **app-under-test model:** `STRANDS_MODEL_ID` (default Haiku 4.5)

```bash
cd server
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eagle-alb.us-east-1.elb.amazonaws.com \
  --journeys all \
  --upload-s3
```

### Nightly triage

**Workflow:** [`.github/workflows/nightly-triage.yml`](.github/workflows/nightly-triage.yml) — runs at **09:00 UTC (1 AM PST)** daily, or on manual dispatch. Added in [`08f904d`](https://github.com/CBIIT/sm_eagle/commit/08f904d).

**Process:**
1. Configure AWS OIDC creds (no profile needed in CI)
2. Query Langfuse REST API for the 24h error window (dev + qa)
3. Cross-reference CloudWatch logs + DynamoDB feedback entries
4. Run Claude Code CLI with the `/triage full` skill
5. Generate a diagnostic report with P0/P1/P2 issues + a fix plan
6. Commit `docs/development/*-report-triage-{env}-*.md` + `.claude/specs/*-plan-triage-{env}-*.md` to main
7. Post a Teams adaptive card summary

**Triage skill** lives at [`.claude/skills/triage/`](.claude/skills/triage/) and can also be run manually:

```bash
# Full report (writes spec file)
/triage <session-id> --env dev --window 24h full

# Light (console only)
/triage <session-id> --env qa --window 4h light
```

Recent triage reports live in [`docs/development/`](docs/development/) — look for files matching `*-report-triage-*.md`.

---

## Weekly Changelog Highlights

The full week-by-week history (10 weeks, 607 commits, 2026-01-30 → 2026-04-08) lives in **[`docs/development/weekly-changelog.md`](docs/development/weekly-changelog.md)**. Highlights only here:

<details>
<summary><strong>Click to expand weekly summary</strong></summary>

- **Week of Jan 26** — [`b4dd25d`](https://github.com/CBIIT/sm_eagle/commit/b4dd25d) Initial commit from multi-tenant sample
- **Weeks of Feb 2 + Feb 9** — document viewer (EAGLE-26), SDK skill → subagent orchestration ([`8f92348`](https://github.com/CBIIT/sm_eagle/commit/8f92348)), PDF/Word export utilities, skill scenario diagrams
- **Week of Feb 16** — **CDK stacks land** (Core/Compute/CiCd in [`5accad1`](https://github.com/CBIIT/sm_eagle/commit/5accad1)), DynamoDB unified `eagle` table ([`2fa9d12`](https://github.com/CBIIT/sm_eagle/commit/2fa9d12)), Justfile + Playwright smoke ([`7cba8bc`](https://github.com/CBIIT/sm_eagle/commit/7cba8bc)), home page redesign, storage stack
- **Week of Feb 23** — **Strands Agents SDK POC** ([`48395e9`](https://github.com/CBIIT/sm_eagle/commit/48395e9)), EC2 runner as standard deploy ([`8121b0c`](https://github.com/CBIIT/sm_eagle/commit/8121b0c)), session persistence (EAGLE-44), real-time SSE (EAGLE-48), contract requirements matrix, bowser E2E validation skills
- **Week of Mar 2** — **Strands migration complete** ([`3e8ebc1`](https://github.com/CBIIT/sm_eagle/commit/3e8ebc1)), `query_compliance_matrix` deterministic decision tree ([`823a8e4`](https://github.com/CBIIT/sm_eagle/commit/823a8e4)), full tool observability ([`fda8a17`](https://github.com/CBIIT/sm_eagle/commit/fda8a17)), migrate to Strands `stream_async()` ([`74616de`](https://github.com/CBIIT/sm_eagle/commit/74616de)), Bedrock Sonnet 4.6 default, branded DOCX/PDF export, AWS Backup plan, user feedback pipeline (Ctrl+J)
- **Week of Mar 9** — **Native DOCX/XLSX preview + AI editing** ([`1b6a0be`](https://github.com/CBIIT/sm_eagle/commit/1b6a0be)), document change log ([`da47c7a`](https://github.com/CBIIT/sm_eagle/commit/da47c7a))
- **Week of Mar 16** — **Langfuse OTEL tracing + admin dashboard** ([`cf4b8d2`](https://github.com/CBIIT/sm_eagle/commit/cf4b8d2), [`c7196fc`](https://github.com/CBIIT/sm_eagle/commit/c7196fc)), Langfuse error classification ([`61506d8`](https://github.com/CBIIT/sm_eagle/commit/61506d8)), Bedrock prompt caching enabled ([`6aa9b45`](https://github.com/CBIIT/sm_eagle/commit/6aa9b45)), Cognito username → Langfuse user identity ([`1f948d3`](https://github.com/CBIIT/sm_eagle/commit/1f948d3)), refactor Phase 0–2 (DDB singleton, config, date utils), tool timing telemetry, 7 MVP1 UC eval tests
- **Week of Mar 23** — **30 new eval tests** (99–128) ([`51e1613`](https://github.com/CBIIT/sm_eagle/commit/51e1613)), **QA environment** ([`48e9593`](https://github.com/CBIIT/sm_eagle/commit/48e9593)), **`/triage` unified diagnostic skill** ([`f957de3`](https://github.com/CBIIT/sm_eagle/commit/f957de3)), **nightly triage GitHub Actions workflow** ([`08f904d`](https://github.com/CBIIT/sm_eagle/commit/08f904d)), **Langfuse parent-span wrap fix** ([`875294f`](https://github.com/CBIIT/sm_eagle/commit/875294f)), **enforce KB-first research cascade** ([`c51a346`](https://github.com/CBIIT/sm_eagle/commit/c51a346)), KB + compliance before web search ([`07b518c`](https://github.com/CBIIT/sm_eagle/commit/07b518c)), AI template standardization ([`2fb7261`](https://github.com/CBIIT/sm_eagle/commit/2fb7261)), conversation compaction ([`aa66290`](https://github.com/CBIIT/sm_eagle/commit/aa66290)), **e2e-judge system** ([`9e8855d`](https://github.com/CBIIT/sm_eagle/commit/9e8855d)), contract requirements matrix modal, **Bedrock LLM-backed document generation** ([`65b222a`](https://github.com/CBIIT/sm_eagle/commit/65b222a)), Prettier + ruff format, LICENSE/CONTRIBUTING, AWS ops tools, Jira QA tests
- **Week of Mar 30** — **Model circuit breaker 4-model fallback chain** ([`f088656`](https://github.com/CBIIT/sm_eagle/commit/f088656)), **delete legacy orchestration services (−5,500 lines)** ([`ed61255`](https://github.com/CBIIT/sm_eagle/commit/ed61255)), 45s TTFT timeout + auto Haiku fallback ([`0eec536`](https://github.com/CBIIT/sm_eagle/commit/0eec536)), **Feedback → JIRA → Teams pipeline** ([`fa30f4c`](https://github.com/CBIIT/sm_eagle/commit/fa30f4c)), **eval scoring enrichment** ([`d60bca1`](https://github.com/CBIIT/sm_eagle/commit/d60bca1)), **baseline-questions skill + V4/V5 scripts** ([`199e2d2`](https://github.com/CBIIT/sm_eagle/commit/199e2d2)), **Bedrock PDF parsing** ([`25783a8`](https://github.com/CBIIT/sm_eagle/commit/25783a8)), **IGCE position-based Excel generation** ([`8ce77ab`](https://github.com/CBIIT/sm_eagle/commit/8ce77ab)), TTFT probe test ([`36a947c`](https://github.com/CBIIT/sm_eagle/commit/36a947c)), composite `research` tool ([`7d3e8ac`](https://github.com/CBIIT/sm_eagle/commit/7d3e8ac)), **V6 baseline 19.5/20** ([`8d5016f`](https://github.com/CBIIT/sm_eagle/commit/8d5016f)), **EAGLE-74/77 fixes = 7/7 Jira QA PASS** ([`1bb4c46`](https://github.com/CBIIT/sm_eagle/commit/1bb4c46))
- **Week of Apr 6** — **Bedrock prompt caching for all models** ([`90c44a5`](https://github.com/CBIIT/sm_eagle/commit/90c44a5)), **V9 baseline 250/260 (96%)** ([`fc71160`](https://github.com/CBIIT/sm_eagle/commit/fc71160)), **Sources tab in activity panel** ([`9e0a85d`](https://github.com/CBIIT/sm_eagle/commit/9e0a85d)), **RO vs EAGLE search comparison** ([`docs/development/ro-vs-eagle-search-comparison.md`](docs/development/ro-vs-eagle-search-comparison.md), [`d526674`](https://github.com/CBIIT/sm_eagle/commit/d526674)), `web_search` scoped to .gov ([`f55b800`](https://github.com/CBIIT/sm_eagle/commit/f55b800)), KB filters hard-gate → AI boost hints ([`8d5016f`](https://github.com/CBIIT/sm_eagle/commit/8d5016f)), tabbed document viewer ([`0912fcc`](https://github.com/CBIIT/sm_eagle/commit/0912fcc)), **`/workflows` renamed → `/packages`** ([`d3a1f3d`](https://github.com/CBIIT/sm_eagle/commit/d3a1f3d)), data schema registry ([`a488047`](https://github.com/CBIIT/sm_eagle/commit/a488047)), **delete doc-generation fast path — all doc-gen flows through supervisor** ([`20d8a0b`](https://github.com/CBIIT/sm_eagle/commit/20d8a0b))

</details>

**Themes by color of thread:**

| Theme | First landed | Current state |
|---|---|---|
| Strands Agents SDK | 2026-02-27 POC | Sole orchestration; legacy deleted 2026-03-30 |
| **Langfuse observability** | 2026-03-17 | OTEL exporter, admin viewer, error classification, parent-span fix, eval validators, user identity, nightly triage |
| **Evaluation suite** | 2026-02 | 142 tests, baseline-questions (Q1–Q14), 4-tier MVP1 ladder, e2e-judge vision QA |
| Circuit breaker + model resilience | 2026-03-30 | 4-model chain, 45s TTFT, Nova Pro fallback, nightly probe |
| Compliance matrix | 2026-03-03 | Deterministic decision tree, 8(a)/J&A paths, KB-first cascade enforced |
| Document pipeline | 2026-03-09 | Native Office, Bedrock PDF parse, IGCE position-based, 22 classification categories |
| Nightly triage | 2026-03-24 | Langfuse + CloudWatch + DDB feedback, auto-commits reports |
| Feedback → JIRA → Teams | 2026-03-31 | Ctrl+J modal, FEEDBACK# entity, Teams adaptive cards |
| CDK stacks | 2026-02-16 | 6 stacks total |
| QA environment | 2026-03-23 | Second CDK target with scoped concurrency |

---

## CI/CD Pipeline

Full workflow list in [`docs/infra.md §10`](docs/infra.md#10-github-actions-workflows). Core flow:

[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) — triggered on push to `main` or manual `workflow_dispatch`:

| Job | Steps |
|---|---|
| **deploy-infra** | OIDC auth (no static keys) → `cdk deploy --all` (6 stacks) → extract stack outputs |
| **deploy-backend** | Docker build → ECR push → ECS rolling update → wait-for-stable |
| **deploy-frontend** | Docker build (Cognito build-args from CDK outputs) → ECR push → ECS rolling update |
| **verify** | Health check `/api/health` + `/` |

Auth is **GitHub OIDC federation** via `DEPLOY_ROLE_ARN` → `EagleCiCdStack` role.

```bash
# Trigger the deploy workflow manually
gh workflow run deploy.yml --ref main
gh run watch

# Trigger a full eval run
gh workflow run eval.yml --ref main

# Trigger nightly triage (normally scheduled)
gh workflow run nightly-triage.yml --ref main
```

Local equivalent of the CI gate:
```bash
just ci       # L1 lint + L2 unit + L4 CDK synth + L6 eval-aws
just ship     # lint + CDK synth + deploy + smoke-prod verify
```

---

## API Reference

### Core

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat` | REST chat (non-streaming) |
| POST | `/api/chat/stream` | SSE streaming chat |
| GET | `/api/health` | Health + git SHA |
| GET | `/api/ping` | Lightweight liveness |
| GET | `/api/tools` | List available tools |

### Sessions / packages / documents

| Method | Endpoint | Description |
|---|---|---|
| GET/POST/DELETE | `/api/sessions[/{id}]` | Session CRUD |
| GET | `/api/sessions/{id}/messages` | Session message history |
| GET/POST/DELETE | `/api/packages[/{id}]` | Acquisition package CRUD |
| GET | `/api/packages/{id}/checklist` | Package checklist state |
| GET/POST | `/api/documents[/{id}]` | Document CRUD |
| POST | `/api/documents/{id}/export` | Export as DOCX / PDF / ZIP |
| POST | `/api/feedback` | Submit feedback (Ctrl+J) |

### Admin

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/dashboard` | Dashboard data |
| GET | `/api/admin/users` | List users |
| GET | `/api/admin/cost-report` | Cost report by tenant |
| GET | `/api/admin/traces` | **Langfuse traces** (dev project) |
| GET | `/api/admin/feedback` | Feedback triage queue |
| GET | `/api/admin/tenants/{id}/comprehensive-report` | Full tenant report |
| POST | `/api/admin/add-to-group` | Add user to Cognito group |

Admin UI lives at [`/admin`](client/app/admin/) with 15 sub-pages: agents, analytics, costs, diagrams, eval, expertise, feedback, kb-reviews, skills, subscription, templates, tests, tools, **traces**, users, workspaces.

---

## Authentication & Multi-Tenancy

Cognito JWT tokens carry `tenant_id`, `user_id`, and `subscription_tier`. Session IDs encode tenant context: `{tenant_id}-{tier}-{user_id}-{session_id}`. All DynamoDB data is partitioned by tenant PK.

<details>
<summary>JWT structure + tenant isolation</summary>

```json
{
  "sub": "user-uuid",
  "email": "user@nih.gov",
  "custom:tenant_id": "nci-oa",
  "custom:subscription_tier": "premium",
  "cognito:groups": ["nci-oa-admins"]
}
```

- **DynamoDB partitioning:** All data partitioned by `tenant_id` via PK patterns — see [`docs/infra.md §3`](docs/infra.md#3-dynamodb-single-table)
- **Runtime context:** Tenant info passed as session attributes to the Strands SDK
- **Admin access:** Cognito Groups for tenant-scoped admin privileges
- **Langfuse user identity:** Cognito username is mirrored to Langfuse `userId` ([`1f948d3`](https://github.com/CBIIT/sm_eagle/commit/1f948d3))
</details>

---

## Data Model

DynamoDB single-table design (`eagle`) with **16+ entity types** — full schema + access patterns in [`docs/infra.md §3`](docs/infra.md#3-dynamodb-single-table). Subscription tiers (`basic` / `advanced` / `premium`) gate message limits, concurrent sessions, session duration, and skill availability (see [`docs/infra.md §12`](docs/infra.md#12-subscription-tiers-feature-gating)).

---

## Contributing

- Branch naming, validation requirements, and code style: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Agent-facing repo guide: [`CLAUDE.md`](CLAUDE.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- **Never edit `eagle-plugin/agents/*/agent.md` or `skills/*/SKILL.md` without running the plugin validator** — plugin content is the source of truth.
- **Never edit `.claude/commands/experts/{domain}/expertise.md` manually** — run `/experts:{domain}:self-improve` instead.

---

## Cleanup

```bash
cd infrastructure/cdk-eagle
npx cdk destroy --all

# ECR repos have RETAIN policy — delete manually if needed
aws ecr delete-repository --repository-name eagle-backend-dev --force --profile eagle
aws ecr delete-repository --repository-name eagle-frontend-dev --force --profile eagle
```

---

## References

- **Infrastructure deep-dive:** [`docs/infra.md`](docs/infra.md)
- **Weekly changelog (full):** [`docs/development/weekly-changelog.md`](docs/development/weekly-changelog.md)
- **Codebase structure:** [`docs/codebase-structure.md`](docs/codebase-structure.md)
- **Local dev setup:** [`docs/setup/local-development.md`](docs/setup/local-development.md)
- **EC2 runner deployment:** [`docs/setup/ec2-runner-deployment.md`](docs/setup/ec2-runner-deployment.md)
- **CDK bootstrap:** [`docs/setup/cdk-bootstrap.md`](docs/setup/cdk-bootstrap.md)
- **Production validation:** [`docs/deployment/EAGLE-production-validation-checklist.md`](docs/deployment/EAGLE-production-validation-checklist.md)
- **Architecture diagrams:** [`docs/architecture/diagrams/excalidraw/`](docs/architecture/diagrams/excalidraw/) · [`mermaid/`](docs/architecture/diagrams/mermaid/)
- **RO vs EAGLE search comparison:** [`docs/development/ro-vs-eagle-search-comparison.md`](docs/development/ro-vs-eagle-search-comparison.md)
- **Langfuse dev project:** [us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f](https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f)
- **GitHub:** [CBIIT/sm_eagle](https://github.com/CBIIT/sm_eagle)
