# EAGLE Operations & Architecture — Onboarding Reference

**Audience:** Alvy (and any new team member)
**Date:** 2026-03-24
**Branch:** main
**Commit:** d1cc0ec

---

## Executive Summary

This memo covers the five operational pillars of EAGLE that aren't obvious from the code alone: Teams webhook notifications, Langfuse observability, the deployment pipeline (dev vs QA, L1-L6 validation), AWS service topology with storage locations, and the report formatting system. Each section includes key files, how-to-access instructions, and recommended enhancements.

---

## Table of Contents

1. [Teams Webhooks & Notifications](#1-teams-webhooks--notifications)
2. [Langfuse Observability](#2-langfuse-observability)
3. [Deployment Pipeline](#3-deployment-pipeline)
4. [AWS Services & Storage Map](#4-aws-services--storage-map)
5. [Report Formatting & Access](#5-report-formatting--access)
6. [Appendix: Key Files Quick Reference](#6-appendix-key-files-quick-reference)
7. [Potential Enhancements](#7-potential-enhancements)

---

## 1. Teams Webhooks & Notifications

### How It Works

EAGLE sends real-time notifications to a Microsoft Teams channel via an **Azure Logic App webhook**. All notifications are fire-and-forget async tasks — they never block the main request flow. If a send fails, it's logged but never crashes the app.

**Webhook target:** Azure Logic App at `prod-52.usgovtexas.logic.azure.us`
**Env var:** `TEAMS_WEBHOOK_URL` (set in ECS task definition and GitHub Actions secrets)
**Card format:** Microsoft Adaptive Card v1.4, wrapped in Power Automate envelope

### The 8 Notification Types

| # | Notification | What Triggers It | What It Means | Card Color | Rate Limit |
|---|---|---|---|---|---|
| 1 | **Feedback** | User presses Ctrl+J in chat UI | Someone submitted feedback (bug, suggestion, praise, etc.) | Blue (accent) | 30/min |
| 2 | **Service Started** | ECS Fargate container boots | A deployment succeeded — new backend container is live and healthy | Green (good) | 5/min |
| 3 | **Deploy Report** | GitHub Actions pipeline completes | Full pipeline summary: lint, tests, CDK, eval, deploy status per component | Green/Red/Yellow | Per-run |
| 4 | **Eval Report** | MVP1 eval suite finishes | Test results: tier 1/2/3 pass/fail counts with Langfuse + CloudWatch links | Green/Red | 2/min |
| 5 | **Morning Report** | Weekday cron at 13:00 UTC | Git commit summary from past 24h: authors, messages, files changed | Blue (accent) | Per-run |
| 6 | **Daily Summary** | Daily at 13:00 UTC (background scheduler) | Aggregate stats: total requests, tokens, cost (USD), active users, feedback breakdown | Default | 2/min |
| 7 | **Error Alert** | Any HTTP 5xx response | Server error with status code, endpoint, error type/message, traceback | Red (attention) | 10/min |
| 8 | **Suspicious Activity** | HTTP 404s, auth anomalies | Potential probe or misconfiguration: event type, detail, tenant, user | Yellow (warning) | 5/min |

### Decoding Teams Messages

- **"EAGLE dev | Service Started"** = A new ECS task registered healthy after deployment. This only fires on ECS (skipped in local dev). If you see this, the deploy succeeded.
- **"EAGLE dev | Eval Report -- All Pass"** = The 42-test eval suite passed. Links in the card go directly to Langfuse traces and CloudWatch logs.
- **"EAGLE dev | Deploy Report"** = End-to-end pipeline summary. Shows L1-L6 validation results, MVP1 eval pass/fail, and deploy status for infra/backend/frontend. Green header = all good. Red = something failed.
- **Feedback cards** = A real user submitted feedback via Ctrl+J. Shows their tier (basic/advanced/premium), tenant, page, session ID, and the feedback text (truncated to 500 chars).

### Key Files

| File | Purpose |
|---|---|
| `server/app/teams_notifier.py` | Core dispatch: `notify_feedback()`, `notify_startup()`, `send_daily_summary()`, `send_eval_report()`, `notify_suspicious()` |
| `server/app/teams_cards.py` | 8 Adaptive Card builder functions (one per notification type) |
| `server/app/error_webhook.py` | Error + suspicious activity webhook handler with rate limiting |
| `server/app/daily_scheduler.py` | Background scheduler that fires daily summary at configured hour |
| `scripts/deploy_report.py` | Called by GitHub Actions at end of pipeline to send deploy report card |
| `scripts/morning_report.py` | Called by `morning-report.yml` workflow to send commit summary |
| `client/components/feedback/feedback-modal.tsx` | Frontend feedback modal (Ctrl+J trigger) |

### Env Vars

```
TEAMS_WEBHOOK_URL=<Azure Logic App URL>
TEAMS_WEBHOOK_ENABLED=true          # Default: true
TEAMS_WEBHOOK_TIMEOUT=5.0           # Seconds
TEAMS_DAILY_SUMMARY_HOUR=13         # UTC (8-9am ET)
TEAMS_DAILY_SUMMARY_ENABLED=true
ERROR_WEBHOOK_URL=<same or separate webhook>
ERROR_WEBHOOK_ENABLED=true
ERROR_WEBHOOK_RATE_LIMIT=10         # Per minute
ERROR_WEBHOOK_INCLUDE_TRACEBACK=true
ERROR_WEBHOOK_MIN_STATUS=500
ERROR_WEBHOOK_EXCLUDE_PATHS=/api/health
```

---

## 2. Langfuse Observability

### What Is Langfuse

Langfuse is an LLM-specific observability platform. Every chat interaction in EAGLE produces a **trace** in Langfuse showing the full agent execution: which models were called, what tools ran, how many tokens were used, and what it cost.

### Dashboard Access

**URL:** `https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f`

From there you can:
- Browse all traces (filter by environment, user, session)
- See token usage and cost per trace
- View the hierarchical observation tree (AGENT > SPAN > GENERATION > TOOL)
- Analyze latency and error patterns

### How Tracing Works

```
POST /api/chat/stream
    |
    v
Strands Agent (BedrockModel)
    |-- OpenTelemetry auto-instrumentation (built into Strands SDK)
    |-- OTLPSpanExporter -> Langfuse OTEL endpoint
    |
    v
Langfuse Cloud (us.cloud.langfuse.com)
    |
    TRACE (one per chat turn)
      +-- AGENT "invoke_agent" (root span)
          +-- SPAN "execute_event_loop_cycle" (per reasoning loop)
              +-- GENERATION "chat" (Bedrock ConverseStream call)
              |     Token counts, cost, model ID
              +-- TOOL "query_contract_matrix" (tool execution)
```

### Custom Attributes on Every Trace

| Attribute | Example | Purpose |
|---|---|---|
| `eagle.tenant_id` | `nci-oar` | Multi-tenant isolation |
| `eagle.user_id` | `john.doe@nih.gov` | User identification |
| `eagle.tier` | `advanced` | Subscription tier |
| `eagle.session_id` | `nci-oar-advanced-jdoe-abc123` | Conversation session |
| `eagle.phase` | `intake` | Workflow phase |
| `eagle.env` | `dev` / `live` / `local` | Environment |
| `eagle.eval` | `true` | Whether this is an eval test run |

### Error Auto-Classification

When a streaming error occurs, EAGLE auto-tags the Langfuse trace with an error category:

| Pattern | Tag | Severity |
|---|---|---|
| Token expired, refresh failed | `error:sso-expired` | `infra` |
| ThrottlingException, rate limit | `error:throttled` | `infra` |
| ECONNREFUSED, fetch failed | `error:network-error` | `infra` |
| AccessDeniedException | `error:access-denied` | `infra` |
| ModelNotReadyException | `error:model-cold-start` | `infra` |
| ValidationException | `error:validation-error` | `app` |

Filter in Langfuse dashboard by tag (e.g., `error:sso-expired`) to see all affected traces.

### Environment Status

| Environment | Langfuse Active? | How Configured |
|---|---|---|
| **Local dev** | OFF by default | Must add keys to `server/.env` manually |
| **Dev (ECS)** | ON | CDK compute-stack injects env vars |
| **QA (ECS)** | ON | Same CDK config (inherits DEV_CONFIG) |
| **Prod (ECS)** | ON | Same CDK config |
| **CI/CD (GitHub Actions)** | ON | GitHub Secrets injected during eval tests |

**To enable locally**, add to `server/.env`:
```
LANGFUSE_PUBLIC_KEY=pk-lf-47021a72-2b4e-4c38-8421-6ab06aef0f5c
LANGFUSE_SECRET_KEY=sk-lf-dbad2023-eede-420c-82e6-2ddec00fb7bb
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PROJECT_ID=cmmsqvi2406aead071t0zhl7f
```

**Note:** All environments currently share the same Langfuse project and credentials. Use the `eagle.env` attribute to filter.

### Admin Traces Page

The EAGLE admin dashboard has a built-in traces page at `/admin/traces`:
- Filter by environment (local/dev/live/prod/eval)
- Search by session ID or user ID
- View duration, token counts, cost, observation hierarchy
- Click "View in Langfuse" to open the trace in the Langfuse dashboard

**Frontend:** `client/app/admin/traces/page.tsx`
**Backend API:** `GET /api/admin/traces`, `GET /api/admin/traces/{trace_id}`, `GET /api/admin/traces/summary`

### Key Files

| File | Purpose |
|---|---|
| `server/app/strands_agentic_service.py` | OTEL exporter setup (`_ensure_langfuse_exporter()`), trace attribute builder |
| `server/app/telemetry/langfuse_client.py` | REST API client, error classification, trace querying/tagging |
| `server/app/streaming_routes.py` | Calls `notify_trace_error()` on stream failures |
| `client/app/admin/traces/page.tsx` | Frontend traces dashboard |
| `infrastructure/cdk-eagle/config/environments.ts` | Langfuse keys for each environment |
| `infrastructure/cdk-eagle/lib/compute-stack.ts` | ECS env var injection |
| `docs/langfuse-trace-aggregation-guide.md` | Trace hierarchy specification |

---

## 3. Deployment Pipeline

### Branch Strategy

```
main branch
  |
  |-- push --> AUTO-DEPLOY to DEV (full validation if significant changes)
  |
  |-- workflow_dispatch (manual) --> DEPLOY to QA (always mini mode)
```

- **DEV:** Every push to `main` triggers the deploy pipeline. If the changes touch significant paths (server/app, tests, eagle-plugin, client/components, etc.), it runs **full mode** (all test levels). Otherwise, **mini mode** (lint + deploy).
- **QA:** Requires manual `workflow_dispatch` from GitHub Actions UI. Always runs **mini mode** — it assumes the code was already tested on DEV.

### Deploy Modes

| Mode | What Runs | When Used |
|---|---|---|
| **auto** (default) | Detects changed paths, picks full or mini | Push to main |
| **full** | L1 → L2 → L4 → L5 → L6 → deploy | Significant changes detected |
| **mini** | L1 only → deploy | Minor changes, or QA dispatch |

### Validation Ladder (L1-L6)

| Level | Name | What It Validates | Command | When It Runs |
|---|---|---|---|---|
| **L1** | Lint | Python syntax + TypeScript types | `ruff check app/` + `npx tsc --noEmit` | Always (all modes) |
| **L2** | Unit Tests | SDK patterns, skill validation, AWS tools | `python -m pytest tests/ -v` (excludes eval) | Full mode only |
| **L3** | E2E | Frontend user workflows (Playwright) | `npx playwright test` | Manual only (not in CI yet) |
| **L4** | CDK Synth | Infrastructure compiles correctly | `npx cdk synth --quiet` | Full mode only |
| **L5** | Integration | Backend starts and responds to health check | `curl http://127.0.0.1:8000/api/health` | After L2 + L4 pass |
| **L6** | Eval | Live Bedrock agent tests (42 total) | `python tests/test_strands_eval.py --tests 1-42` | After L5 passes |

**Minimum validation by change type:**

| Change Type | Required Levels |
|---|---|
| Backend logic | L1 + L2 |
| Frontend UI | L1 + L3 |
| CDK / infrastructure | L1 + L4 |
| Production deploy | L1-L6 + docker compose |

### MVP1 Eval Suite (L6)

The eval suite has **42 tests** split into categories:

| Tests | Category | What They Test |
|---|---|---|
| 1-8 | SDK Patterns | Session create/resume, traces, subagent orchestration, cost tracking, tier gating |
| 9-15 | Specialist Skills | OA intake, legal, market research, tech, public interest, doc gen, supervisor routing |
| 16-20 | AWS Tools | S3 ops, DynamoDB, CloudWatch, document generation |
| 21-27 | UC Workflows | Micro-purchase, option exercise, contract mod, close-out, scoring |
| 28 | Plugin System | Skill-tool orchestration |
| 29-31 | Compliance | FAR query, vehicle suggestions, requirements search |
| 32-34 | Admin | Manager skill, workspace store, CRUD |
| **35-42** | **UC E2E (MVP1 gate)** | **New acquisition, GSA schedule, sole source, IGCE, tech-to-contract, E2E** |

**Tests 35-42 are the MVP1 go/no-go gate.** All 8 must pass before a build is considered production-ready.

**Models used:**
- CI/CD eval: Claude 3.5 Haiku (cost-optimized for gate validation)
- Production: Claude Sonnet 4.6 (full capability)

**Run locally:** `/mvp1-eval` skill runs the same test suite on your machine.

### CDK Stacks (6 total)

| Stack | What It Creates |
|---|---|
| **EagleCoreStack** | VPC import, Cognito user pool, IAM app role, imports existing S3 + DynamoDB |
| **EagleCiCdStack** | GitHub Actions OIDC provider, deploy role |
| **EagleStorageStack** | Document S3 bucket, metadata DynamoDB table, metadata extraction Lambda |
| **EagleComputeStack** | ECS cluster, ECR repos, Fargate services (backend + frontend), ALB |
| **EagleEvalStack** | Eval artifacts S3 bucket, CloudWatch dashboard, SNS alert topics |
| **EagleBackupStack** | AWS Backup plans for DynamoDB + S3 (7/30-day retention) |

**Deploy command (GitHub Actions):**
```bash
cd infrastructure/cdk-eagle
npx cdk deploy EagleCoreStack EagleCiCdStack EagleStorageStack EagleEvalStack EagleBackupStack \
  --exclusively --require-approval never --outputs-file outputs.json
```

### Container Deploy Flow

```
1. Docker build (Dockerfile.backend / Dockerfile.frontend)
2. Push to ECR: {account}.dkr.ecr.us-east-1.amazonaws.com/eagle-backend-{env}:{git_sha}
3. Register new ECS task definition (inject image URI + env vars)
4. aws ecs update-service --force-new-deployment
5. aws ecs wait services-stable (blocks until healthy)
6. Teams "Service Started" notification fires
```

### Pipeline Timeline

| Phase | Duration | Notes |
|---|---|---|
| L1 Lint | ~2 min | Always runs |
| L2 Unit Tests | ~5 min | Parallel with L4 |
| L4 CDK Synth | ~3 min | Parallel with L2 |
| L5 Integration | ~3 min | After L2 + L4 |
| L6 Eval | ~15 min | 34 general + 8 MVP1 tests |
| Deploy infra | ~5-10 min | CDK deploy |
| Deploy containers | ~5 min each | Backend + frontend |
| ECS stability | ~2-5 min | Per service |
| **Total (full)** | **~30-45 min** | |
| **Total (mini/QA)** | **~15 min** | Lint + deploy only |

### Key Files

| File | Purpose |
|---|---|
| `.github/workflows/deploy.yml` | Primary CI/CD pipeline (29KB) |
| `.github/workflows/eval.yml` | Scheduled nightly eval |
| `.github/workflows/morning-report.yml` | Weekday morning commit report |
| `infrastructure/cdk-eagle/bin/eagle.ts` | CDK stack orchestration + dependencies |
| `deployment/docker/Dockerfile.backend` | Backend container (Python 3.11, port 8000) |
| `deployment/docker/Dockerfile.frontend` | Frontend container (Node 20, port 3000, multi-stage) |
| `deployment/docker-compose.dev.yml` | Local dev environment |
| `server/tests/test_strands_eval.py` | 42-test eval suite |
| `.claude/skills/mvp1-eval/SKILL.md` | Local eval skill definition |

---

## 4. AWS Services & Storage Map

### Services Overview

| Service | Purpose | Key Resource |
|---|---|---|
| **DynamoDB** | All application data (single-table) | Table: `eagle` |
| **S3** | Document storage + eval artifacts | `eagle-documents-695681773636-dev` |
| **ECS Fargate** | Container orchestration | Cluster: `eagle-dev` |
| **ECR** | Container images | `eagle-backend-dev`, `eagle-frontend-dev` |
| **Cognito** | User auth | Pool: `eagle-users-dev` |
| **Bedrock** | LLM inference | Claude Sonnet 4.6, Haiku 4.5, Nova 2 Lite |
| **CloudWatch** | Logs, metrics, alarms | `/eagle/app`, `/eagle/telemetry` |
| **Lambda** | Metadata extraction on doc upload | Triggered by S3 events |
| **ALB** | Traffic routing to ECS | Internal (backend), public (frontend) |
| **AWS Backup** | Scheduled backups | DynamoDB + S3, 7/30-day retention |

### DynamoDB Single-Table Design

Table `eagle` uses a composite primary key (`PK` + `SK`) with all entity types in one table:

| Entity | PK Pattern | SK Pattern | What It Stores |
|---|---|---|---|
| `SESSION` | `SESSION#{tenant}#{user}#{session}` | Various | Chat sessions |
| `MSG` | `MSG#{session_id}` | `MSG#{message_id}#{created_at}` | Conversation messages |
| `FEEDBACK` | `FEEDBACK#{tenant_id}` | `FEEDBACK#{timestamp}#{id}` | User feedback (Ctrl+J) |
| `WORKSPACE` | `WORKSPACE#{tenant}#{user}` | `WORKSPACE#{workspace_id}` | Named workspaces |
| `WSPC` | `WSPC#{tenant}#{user}#{workspace}` | `{entity_type}#{name}` | Workspace overrides |
| `DOCUMENT` | `DOCUMENT#{tenant_id}` | `DOCUMENT#{package}#{doc_type}#{version}` | Generated docs (SOW, IGCE, AP) |
| `PACKAGE` | `PACKAGE#{tenant_id}` | `PACKAGE#{package_id}` | Acquisition packages |
| `APPROVAL` | `APPROVAL#{tenant_id}` | `APPROVAL#{package}#{step}` | FAR-driven approval chains |
| `AUDIT` | `AUDIT#{tenant_id}` | `AUDIT#{timestamp}#{entity}#{name}` | Immutable audit log |
| `USAGE` | `USAGE#{tenant}#{metric}` | `USAGE#{timestamp}#{session}` | Token/cost tracking |
| `COST` | `COST#{tenant_id}` | `COST#{timestamp}` | Cost attribution |
| `SUB` | `SUB#{tenant_id}` | `SUB#{tier}` | Subscription limits |
| `TEMPLATE` | `TEMPLATE#{tenant_id}` | `TEMPLATE#{template_id}` | Document templates |
| `PLUGIN` | `PLUGIN#{entity_name}` | `PLUGIN#{content_type}#{name}` | Agent/skill definitions |
| `PROMPT` | `PROMPT#{tenant_id}` or `PROMPT#global` | `PROMPT#{agent_name}` | Prompt overrides |

**GSI1:** Tenant-level listing (PK=`GSI1PK`, SK=`GSI1SK`)
**GSI2:** Tier queries and skill listing (PK=`GSI2PK`, SK=`GSI2SK`)
**TTL:** `ttl` attribute (7 years for feedback/audit)

### S3 Storage — Where Things Are Saved

#### Document Bucket: `eagle-documents-695681773636-dev`

**Generated documents (SOW, IGCE, AP):**
```
eagle/{tenant_id}/packages/{package_id}/{doc_type}/v{version}/{filename}.docx
```
Example:
```
eagle/nci-oar/packages/pkg-001/sow/v1/Statement_of_Work.docx
eagle/nci-oar/packages/pkg-001/igce/v2/Cost_Estimate.xlsx
```

**Workspace user documents:**
```
eagle/{tenant_id}/{user_id}/documents/{filename}
```

**Configuration:**
- Versioning: Enabled
- Lifecycle: Noncurrent versions → IA after 90 days, expire after 365 days
- Encryption: S3-managed (SSE-S3)
- Public access: Fully blocked

#### Eval Artifacts Bucket: `eagle-eval-artifacts-695681773636-dev`

```
eval/results/{run_id}.json          # Test results JSON
eval/videos/{timestamp}/            # Playwright video captures
```
Lifecycle: 365-day expiration.

### Where Feedback Is Saved

**Feedback is stored in DynamoDB only, NOT in S3.**

```
PK:  FEEDBACK#{tenant_id}
SK:  FEEDBACK#{ISO_timestamp}#{feedback_id}

Fields:
- feedback_id (UUID)
- user_id, tenant_id, tier
- feedback_type: bug | suggestion | praise | incorrect_info | general
- feedback_text (full text)
- conversation_snapshot (full conversation context)
- cloudwatch_logs (associated log URL)
- page (where in the UI it was submitted)
- session_id, last_message_id
- TTL: 7 years
```

Message-level feedback (thumbs up/down) uses a separate SK pattern:
```
SK: MSG_FEEDBACK#{session_id}#{message_id}
```

### Where Workspace Documents Are Saved

Workspaces are stored across two layers:

1. **DynamoDB metadata** — workspace definitions (name, description, active status) and overrides (WSPC entities for agents, skills, templates, config)
2. **S3 binary files** — any uploaded workspace documents at `eagle/{tenant_id}/{user_id}/documents/`

Workspace override resolution follows a 4-layer priority chain:
1. WSPC# (workspace override) — highest
2. PROMPT#{tenant_id} (tenant admin override)
3. PROMPT#global (platform admin override)
4. PLUGIN# (canonical plugin definitions) — lowest

### Document Metadata Extraction

When a document is uploaded to S3, a Lambda function automatically:
1. Reads the document
2. Invokes Bedrock Claude Sonnet 4.6 to extract metadata
3. Stores enriched metadata in the `eagle-document-metadata-dev` DynamoDB table
4. Logs to CloudWatch `/eagle/lambda/metadata-extraction-dev`

### Cognito Authentication

- **User Pool:** `eagle-users-dev` (email-based sign-in)
- **Custom attributes:** `tenant_id`, `subscription_tier`
- **Token validity:** Access 1h, ID 1h, Refresh 30d
- **Auth flows:** UserPassword, UserSRP, AdminUserPassword

### Bedrock Models

| Model | ID | Purpose |
|---|---|---|
| Claude Sonnet 4.6 | `us.anthropic.claude-sonnet-4-6` | Primary LLM (agent orchestration) |
| Claude Haiku 4.5 | `anthropic.claude-haiku-4-5-20251001-v1:0` | Title generation |
| Nova 2 Lite | `amazon.nova-2-lite-v1:0` | Web grounding / search |

### CloudWatch Log Groups

| Log Group | What It Captures | Retention |
|---|---|---|
| `/eagle/app` | Application-level logs | 3 months |
| `/eagle/ecs/backend-dev` | Backend container stdout/stderr | 1 month |
| `/eagle/ecs/frontend-dev` | Frontend container stdout/stderr | 1 month |
| `/eagle/telemetry` | Custom telemetry events (trace.started, tool.completed, etc.) | Unbounded |
| `/eagle/test-runs` | Eval suite test results | Imported |
| `/eagle/lambda/metadata-extraction-dev` | Lambda metadata extractor logs | 1 month |

### Subscription Tiers

| Feature | Basic | Advanced | Premium |
|---|---|---|---|
| Daily messages | 100 | 1,000 | Unlimited |
| Monthly messages | 3,000 | 30,000 | Unlimited |
| Concurrent sessions | 1 | 5 | Unlimited |
| MCP server access | No | Yes | Yes |

### Key Files

| File | Purpose |
|---|---|
| `infrastructure/cdk-eagle/config/environments.ts` | All env config: account, VPC, bucket names, Langfuse keys |
| `infrastructure/cdk-eagle/lib/core-stack.ts` | VPC, Cognito, IAM, imports DynamoDB + S3 |
| `infrastructure/cdk-eagle/lib/storage-stack.ts` | Document S3 bucket, metadata table, Lambda |
| `infrastructure/cdk-eagle/lib/compute-stack.ts` | ECS, ECR, ALB, env var injection |
| `infrastructure/cdk-eagle/lib/eval-stack.ts` | Eval artifacts bucket, CloudWatch dashboard |
| `server/app/feedback_store.py` | Feedback DynamoDB CRUD |
| `server/app/document_store.py` | Document versioning + S3 key management |
| `server/app/document_service.py` | Document generation + S3 upload + presigned URLs |
| `server/app/document_key_utils.py` | S3 key parsing utilities |
| `server/app/workspace_store.py` | Workspace CRUD + 4-layer resolution chain |
| `server/app/session_store.py` | Session DynamoDB CRUD |
| `server/app/cost_attribution.py` | Token usage + cost calculations |

---

## 5. Report Formatting & Access

### Report Types

| Type | Format | Generated By | Destination |
|---|---|---|---|
| **Eval Report** | Markdown + HTML + JSON | `server/tests/generate_eval_report.py` | `test-reports/{YYYYMMDD-HHMMSS}/` |
| **Deploy Report** | Adaptive Card (JSON) | `scripts/deploy_report.py` | Teams channel |
| **Morning Report** | Adaptive Card (JSON) | `scripts/morning_report.py` | Teams channel |
| **Daily Summary** | Adaptive Card (JSON) | `server/app/daily_scheduler.py` | Teams channel |
| **Code Review** | Markdown | `/review` command | `review_reports/` |
| **Analysis Reports** | Markdown (Scribe-formatted) | `/scribe` command | `docs/development/` |
| **Document Exports** | DOCX / PDF / Markdown | `server/app/document_export.py` | S3 + download |

### How to Access Reports

**Eval reports (local filesystem):**
```
test-reports/
  20260319-182120/
    eval-report.md           # Markdown summary
    eval-report.html         # Interactive HTML (dark theme, embedded screenshots)
    summary.json             # Structured metadata (pass/fail counts, durations)
    01-tier1-unit.txt        # Raw pytest output
    02-tier2-integration.txt # Raw pytest output
    screenshots/             # Playwright E2E captures
```

**Eval reports (DynamoDB):**
```python
from server.app.test_result_store import list_test_runs, get_test_run_results
runs = list_test_runs(limit=20)  # Newest first
results = get_test_run_results("run-2026-03-19T17-48-29-996772Z")
```
TTL: 90 days.

**Eval reports (S3):**
```
s3://eagle-eval-artifacts-695681773636-dev/eval/results/{run_id}.json
s3://eagle-eval-artifacts-695681773636-dev/eval/videos/{timestamp}/
```

**Eval reports (CloudWatch):**
Log group `/eagle/test-runs/`, metric namespace `EAGLE/Eval`.

**Teams cards:**
Check the Teams channel directly. Cards are fire-and-forget with no local persistence.

**Analysis reports (docs/):**
```
docs/development/
  20260320-200000-report-eagle-schema-inventory-v1.md
  20260309-120000-report-divergence-audit-v1.md
  20260302-140000-report-claude-sdk-vs-strands-v1.md
  20260226-111151-report-branch-merge-analysis-v1.md (in .claude/specs/)
```

### Scribe Standardization

The `/scribe` command auto-detects report type and applies canonical formatting:

**Naming:** `{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.{ext}`
- Scans destination dir for highest `vN`, writes `v{N+1}`
- Never overwrites

**Rules applied:**
- Executive summary (2-3 sentences)
- Tables over lists (3+ items become tables)
- Code references as `file:line_number`
- No filler language
- Metadata footer with timestamp and format type

### Current Formatting Assessment

The user rates current report formatting at **"Level C"** — functional but inconsistent. Areas to improve:

- **Eval HTML reports** — Dark theme with embedded screenshots works well, but stat grid could be more informative
- **Teams Adaptive Cards** — Functional but could use richer formatting (trend indicators, sparklines)
- **Analysis reports** — Quality varies depending on whether `/scribe` was used
- **Deploy reports** — L1-L6 ladder is clear, but MVP1 results could show more detail per use case
- **Document exports** — DOCX with NCI branding is solid, but "DRAFT" watermark is hardcoded

---

## 6. Appendix: Key Files Quick Reference

### Must-Review Files for Alvy

| # | File | What To Look For |
|---|---|---|
| 1 | `server/app/teams_notifier.py` | All `notify_*()` functions — see how each notification triggers |
| 2 | `server/app/teams_cards.py` | 8 card builder functions — see the format of each Teams message |
| 3 | `server/app/error_webhook.py` | Error + suspicious activity webhook with rate limiting |
| 4 | `server/app/telemetry/langfuse_client.py` | Langfuse REST client + 12-pattern error classifier |
| 5 | `server/app/strands_agentic_service.py` | OTEL exporter setup + trace attribute builder |
| 6 | `.github/workflows/deploy.yml` | Full CI/CD pipeline — L1-L6, deploy modes, container push |
| 7 | `infrastructure/cdk-eagle/config/environments.ts` | All env config (account IDs, bucket names, Langfuse keys) |
| 8 | `infrastructure/cdk-eagle/lib/compute-stack.ts` | ECS task definition + env var injection |
| 9 | `server/app/feedback_store.py` | Feedback DynamoDB schema + conversation snapshot capture |
| 10 | `server/app/document_store.py` | Document versioning + S3 key structure |
| 11 | `server/app/workspace_store.py` | Workspace entities + 4-layer resolution chain |
| 12 | `server/tests/generate_eval_report.py` | Report generator (MD + HTML + JSON output) |
| 13 | `scripts/deploy_report.py` | Deploy report → Teams card sender |
| 14 | `scripts/morning_report.py` | Morning commit summary → Teams |
| 15 | `docs/langfuse-trace-aggregation-guide.md` | Trace hierarchy specification |
| 16 | `test-reports/20260319-182120/eval-report.md` | Example eval report (sample output) |

---

## 7. Potential Enhancements

### Teams Notifications

| Enhancement | Current State | Proposed |
|---|---|---|
| Thread-reply support | Each notification is standalone | Group related alerts (e.g., all errors from one deploy) |
| Notification audit trail | Fire-and-forget, no persistence | Store sent notifications in DynamoDB for history |
| Channel routing | All notifications go to one channel | Route feedback, errors, deploys to separate channels |
| Notification preferences | All-or-nothing via env var | Per-notification-type enable/disable |

### Langfuse Observability

| Enhancement | Current State | Proposed |
|---|---|---|
| Local dev by default | OFF — must manually add keys | Add keys to `.env.example` so local sessions are traced |
| Per-environment projects | All envs share one project | Separate Langfuse projects to isolate dev noise from prod |
| Cost alerting | Manual dashboard checking | Alert when daily spend exceeds threshold |
| Prompt management | Prompts in code/DynamoDB | Use Langfuse prompt versioning for A/B testing |

### Deployment Pipeline

| Enhancement | Current State | Proposed |
|---|---|---|
| E2E in CI | L3 is manual only | Add Playwright E2E to GitHub Actions pipeline |
| Rollback automation | Manual (re-deploy previous task def) | One-click rollback via workflow_dispatch |
| Canary deploys | Full cut-over | Route 10% traffic to new version, validate, then 100% |
| Prod approval gate | Only QA has manual dispatch | Add required approval step before prod deploy |

### Report Formatting

| Enhancement | Current State | Proposed |
|---|---|---|
| Report index | Reports scattered across dirs | Central manifest listing all reports with type, date, status |
| Side-by-side comparison | No diffing between runs | Compare two eval reports (before/after a change) |
| XLSX export | Only DOCX/PDF/Markdown | Add Excel for data-heavy reports (cost analysis, usage) |
| Configurable watermark | "DRAFT" hardcoded on all exports | Parameter to set/remove watermark |
| Richer Teams cards | Flat fact lists | Add trend arrows, sparklines, color-coded pass rates |

### Storage & Data

| Enhancement | Current State | Proposed |
|---|---|---|
| Feedback export | Query-only via DynamoDB | Export feedback as CSV/JSON for analysis |
| Document lifecycle | Manual version management | Auto-archive superseded versions after 90 days |
| Cross-tenant analytics | Per-tenant queries only | Aggregated dashboard across all tenants |
| S3 document search | Browse by key path only | Full-text search via OpenSearch or metadata index |

---

*Scribe | 2026-03-24T12:00:00Z | Format: markdown | Type: report*
