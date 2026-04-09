# EAGLE — Infrastructure & Services

This doc is the single source of truth for **what EAGLE runs on**: AWS services, third-party integrations, model providers, env vars, tables, buckets, ports, and log groups. If a service is mentioned anywhere in the README or code, it should be listed here with a config pointer.

Paired with [`README.md`](../README.md) (user-facing overview) and [`docs/codebase-structure.md`](./codebase-structure.md) (file layout).

---

## 1. AWS services

| Service | Resource(s) | Configured in | Notes |
|---|---|---|---|
| **ECS Fargate** | backend task def, frontend task def, cluster, services | [`infrastructure/cdk-eagle/lib/compute-stack.ts`](../infrastructure/cdk-eagle/lib/compute-stack.ts) | Rolling updates via `just deploy` or GitHub Actions |
| **ALB** | internal ALB + target groups per service | [`compute-stack.ts`](../infrastructure/cdk-eagle/lib/compute-stack.ts) | QA uses external ALB + subnets |
| **ECR** | `eagle-backend-{env}`, `eagle-frontend-{env}` | [`cicd-stack.ts`](../infrastructure/cdk-eagle/lib/cicd-stack.ts) | Retain on stack delete |
| **Cognito** | user pool + app client, JWT with `tenant_id`, `subscription_tier` | [`core-stack.ts`](../infrastructure/cdk-eagle/lib/core-stack.ts), [`server/app/cognito_auth.py`](../server/app/cognito_auth.py) | Frontend auth flow in [`client/app/login/page.tsx`](../client/app/login/page.tsx) |
| **DynamoDB** | `eagle` single-table (GSI1, GSI2, TTL), `eagle-document-metadata-{env}` | [`core-stack.ts`](../infrastructure/cdk-eagle/lib/core-stack.ts), [`storage-stack.ts`](../infrastructure/cdk-eagle/lib/storage-stack.ts), [`server/app/db_client.py`](../server/app/db_client.py) | See [Data model](#3-dynamodb-single-table) |
| **S3** | `eagle-documents-{acct}-{env}`, `eagle-eval-artifacts-{acct}-{env}`, imports `nci-documents` | [`storage-stack.ts`](../infrastructure/cdk-eagle/lib/storage-stack.ts), [`eval-stack.ts`](../infrastructure/cdk-eagle/lib/eval-stack.ts) | Versioning on document bucket; 365-day lifecycle on eval bucket |
| **Lambda** | document metadata extractor (S3 trigger → Bedrock Converse → metadata cache) | [`storage-stack.ts`](../infrastructure/cdk-eagle/lib/storage-stack.ts), [`infrastructure/cdk-eagle/scripts/bundle-lambda.py`](../infrastructure/cdk-eagle/scripts/bundle-lambda.py) | Cross-platform bundler |
| **Bedrock** | Claude Sonnet 4.6, Sonnet 4.5, Sonnet 4.0, Haiku 4.5, Nova Pro | [`server/app/strands_agentic_service.py`](../server/app/strands_agentic_service.py), [`server/app/bedrock_service.py`](../server/app/bedrock_service.py) | 4-model circuit breaker; see [Model fallback](#5-model-providers--circuit-breaker) |
| **CloudWatch Logs** | `/eagle/ecs/backend-{env}`, `/eagle/ecs/frontend-{env}`, `/eagle/app`, `/eagle/telemetry`, `/eagle/test-runs` | [`eval-stack.ts`](../infrastructure/cdk-eagle/lib/eval-stack.ts), [`server/app/telemetry/cloudwatch_emitter.py`](../server/app/telemetry/cloudwatch_emitter.py) | Structured JSON logs |
| **CloudWatch Metrics + Alarms** | eval pass rate, cost thresholds, 5xx alarms | [`eval-stack.ts`](../infrastructure/cdk-eagle/lib/eval-stack.ts) | Dashboards + SNS notifications |
| **SNS** | `eagle-eval-alerts` topic | [`eval-stack.ts`](../infrastructure/cdk-eagle/lib/eval-stack.ts) | Emails + Teams via webhook proxy |
| **VPC** | imported `vpc-09def43fcabfa4df6` (NCI networking) | [`core-stack.ts`](../infrastructure/cdk-eagle/lib/core-stack.ts), [`infrastructure/cdk-eagle/config/environments.ts`](../infrastructure/cdk-eagle/config/environments.ts) | Dev: 1 NAT · Staging: 2 · Prod: 3 |
| **IAM** | ECS task role, Lambda exec role, GitHub OIDC deploy role, Bedrock-scoped policies | [`core-stack.ts`](../infrastructure/cdk-eagle/lib/core-stack.ts), [`cicd-stack.ts`](../infrastructure/cdk-eagle/lib/cicd-stack.ts) | No static IAM keys in secrets |
| **SSM Session Manager** | EC2 devbox access (`just devbox-*`) | Justfile `devbox-*` recipes | Used as standard deploy runner |
| **AWS Backup** | hourly DynamoDB snapshots, daily S3 | [`backup-stack.ts`](../infrastructure/cdk-eagle/lib/backup-stack.ts) | Added [`d56f85a`](https://github.com/CBIIT/sm_eagle/commit/d56f85a) |

---

## 2. CDK stacks (6 total)

All live under [`infrastructure/cdk-eagle/lib/`](../infrastructure/cdk-eagle/lib/). Deploy order is enforced via stack dependencies.

| Stack | File | Creates |
|---|---|---|
| **EagleCoreStack** | [`core-stack.ts`](../infrastructure/cdk-eagle/lib/core-stack.ts) | VPC import, Cognito user pool + client, IAM app role, `eagle` DynamoDB table (+ GSIs, TTL) |
| **EagleStorageStack** | [`storage-stack.ts`](../infrastructure/cdk-eagle/lib/storage-stack.ts) | `eagle-documents-{env}` bucket (versioned), `eagle-document-metadata-{env}` table, metadata-extraction Lambda |
| **EagleComputeStack** | [`compute-stack.ts`](../infrastructure/cdk-eagle/lib/compute-stack.ts) | ECR repos, ECS cluster, Fargate task defs, internal ALBs, target groups, security groups, auto-scaling |
| **EagleCiCdStack** | [`cicd-stack.ts`](../infrastructure/cdk-eagle/lib/cicd-stack.ts) | GitHub OIDC provider, `eagle-github-actions-{env}` deploy role |
| **EagleEvalStack** | [`eval-stack.ts`](../infrastructure/cdk-eagle/lib/eval-stack.ts) | `eagle-eval-artifacts-{env}` bucket, CloudWatch log groups + alarms + dashboard, SNS topic |
| **EagleBackupStack** | [`backup-stack.ts`](../infrastructure/cdk-eagle/lib/backup-stack.ts) | AWS Backup plan (DynamoDB hourly, S3 daily) |

Env config: [`infrastructure/cdk-eagle/config/environments.ts`](../infrastructure/cdk-eagle/config/environments.ts) — dev, qa, staging, prod.

---

## 3. DynamoDB single-table

Table: `eagle` (or env-suffixed). See [`server/app/session_store.py`](../server/app/session_store.py), [`server/app/package_store.py`](../server/app/package_store.py), and the other `*_store.py` modules for entity-specific access patterns.

| Entity | PK | SK | Source module |
|---|---|---|---|
| Session | `SESSION#{tenant}#{user}` | `SESSION#{session_id}` | [`session_store.py`](../server/app/session_store.py) |
| Message | `SESSION#{tenant}#{user}` | `MSG#{session_id}#{ts}` | [`session_store.py`](../server/app/session_store.py) |
| Usage | `USAGE#{tenant}` | `USAGE#{date}#{session}#{ts}` | [`cost_attribution.py`](../server/app/cost_attribution.py) |
| Cost | `COST#{tenant}` | `COST#{date}#{ts}` | [`cost_attribution.py`](../server/app/cost_attribution.py) |
| Subscription | `SUB#{tenant}` | `SUB#{tier}#current` | [`subscription_service.py`](../server/app/subscription_service.py) |
| Package | `PACKAGE#{tenant}` | `PKG#{package_id}` | [`package_store.py`](../server/app/package_store.py) |
| Template | `TEMPLATE#{tenant}` | `TEMPLATE#{template_id}` | [`template_store.py`](../server/app/template_store.py) |
| User document | `USER_DOCS#{tenant}` | `DOC#{doc_id}` | [`user_document_store.py`](../server/app/user_document_store.py) |
| Feedback | `FEEDBACK#{tenant}` | `FB#{ts}` | [`feedback_store.py`](../server/app/feedback_store.py) |
| Audit | `AUDIT#{tenant}` | `AUDIT#{ts}` | [`audit_store.py`](../server/app/audit_store.py) |
| Changelog | `CHANGELOG#{doc_id}` | `CL#{ts}` | [`changelog_store.py`](../server/app/changelog_store.py) |
| Export | `EXPORT#{tenant}` | `EXP#{ts}` | [`export_store.py`](../server/app/export_store.py) |
| Test result | `TEST_RESULT#{run_id}` | `TR#{ts}` | [`test_result_store.py`](../server/app/test_result_store.py) |
| Reasoning | `REASONING#{session}` | `R#{ts}` | [`reasoning_store.py`](../server/app/reasoning_store.py) |
| Approval | `APPROVAL#{tenant}` | `APP#{approval_id}` | [`approval_store.py`](../server/app/approval_store.py) |
| Config | `CONFIG#{tenant}` | `CFG#{key}` | [`config_store.py`](../server/app/config_store.py) |

Full store list: 19 `*_store.py` modules in [`server/app/`](../server/app/).

---

## 4. S3 buckets

| Bucket | Purpose | Lifecycle | Source |
|---|---|---|---|
| `eagle-documents-{acct}-{env}` | User-uploaded + AI-generated documents, sidecar `.content.md` | Versioned, no expiration | [`storage-stack.ts`](../infrastructure/cdk-eagle/lib/storage-stack.ts) |
| `eagle-document-metadata-{env}` (DDB, not S3) | Cached Bedrock-extracted metadata | — | [`storage-stack.ts`](../infrastructure/cdk-eagle/lib/storage-stack.ts) |
| `eagle-eval-artifacts-{acct}-{env}` | Eval results, screenshots, HTML reports, e2e-judge outputs | 365-day expiration | [`eval-stack.ts`](../infrastructure/cdk-eagle/lib/eval-stack.ts) |
| `nci-documents` (imported) | NCI knowledge base corpus | Managed externally | [`core-stack.ts`](../infrastructure/cdk-eagle/lib/core-stack.ts) |

---

## 5. Model providers & circuit breaker

Primary: **AWS Bedrock** via Strands Agents SDK `BedrockModel` (boto3-native).

Circuit breaker lives in [`server/app/strands_agentic_service.py`](../server/app/strands_agentic_service.py) (`ModelCircuitBreaker`):

- **States:** `CLOSED` (healthy) → `OPEN` (2 consecutive failures) → `HALF_OPEN` (recovery after 120s)
- **Chain:** `claude-sonnet-4-6` → `claude-sonnet-4-5` → `claude-sonnet-4-0` → `claude-haiku-4-5` → Nova Pro fallback
- **TTFT timeout:** 45s per model before automatic Haiku fallback ([`0eec536`](https://github.com/CBIIT/sm_eagle/commit/0eec536))
- **Prompt caching:** enabled for all models via Strands SDK ([`90c44a5`](https://github.com/CBIIT/sm_eagle/commit/90c44a5))
- **TTFT probe:** nightly `test_ttft_probe.py` validates all 4 models ([`36a947c`](https://github.com/CBIIT/sm_eagle/commit/36a947c))

Fallback: **Anthropic direct API** (`claude-sonnet-4-6`, `claude-haiku-4-5`) via [`server/app/bedrock_service.py`](../server/app/bedrock_service.py) when Bedrock is unavailable.

Env override: `EAGLE_BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0` (used in CI and eval to save cost).

---

## 6. Third-party services

| Service | What it does | Where it's wired | Config |
|---|---|---|---|
| **Langfuse** | OTEL trace ingestion, observability, admin trace viewer, eval scoring, error classification | [`server/app/telemetry/langfuse_client.py`](../server/app/telemetry/langfuse_client.py), [`server/app/strands_agentic_service.py`](../server/app/strands_agentic_service.py) (exporter + parent span wrap) | `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_PROJECT_ID` |
| **JIRA** (NCI `tracker.nci.nih.gov`) | Feedback → ticket pipeline, commit linking, QA eval test IDs | [`server/app/jira_client.py`](../server/app/jira_client.py), [`.github/workflows/jira-commits-sync.yml`](../.github/workflows/jira-commits-sync.yml) | `JIRA_BASE_URL`, `JIRA_API_TOKEN`, `JIRA_USER` |
| **Microsoft Teams** | Webhook notifications: deploy reports, daily digest, triage alerts, feedback cards | [`server/app/teams_notifier.py`](../server/app/teams_notifier.py), [`server/app/teams_cards.py`](../server/app/teams_cards.py) | `TEAMS_TRIAGE_WEBHOOK_URL`, `TEAMS_DEPLOY_WEBHOOK_URL` |
| **GitHub Actions** | CI/CD, nightly triage, PR review bot, Jira sync | [`.github/workflows/`](../.github/workflows/) | OIDC federation (no static keys) |
| **Anthropic API** | Direct Claude fallback when Bedrock down | [`server/app/bedrock_service.py`](../server/app/bedrock_service.py) | `ANTHROPIC_API_KEY` |
| **Power Automate** | Feedback approval webhooks | [`server/app/routers/feedback_actions.py`](../server/app/routers/feedback_actions.py) | Workflow URL |

### Langfuse details

- **Host:** [`https://us.cloud.langfuse.com`](https://us.cloud.langfuse.com)
- **Dev project ID:** `cmmsqvi2406aead071t0zhl7f` → [project dashboard](https://us.cloud.langfuse.com/project/cmmsqvi2406aead071t0zhl7f)
- **ARTI secondary project ID:** `cmmtw4vjq026kad07iu2y1nuc` → [project dashboard](https://us.cloud.langfuse.com/project/cmmtw4vjq026kad07iu2y1nuc)
- **Admin traces UI:** [`client/app/admin/traces/page.tsx`](../client/app/admin/traces/page.tsx) — pulls via [`server/app/routers/admin.py`](../server/app/routers/admin.py) `/api/admin/traces` endpoint
- **Trace nesting fix:** [`875294f`](https://github.com/CBIIT/sm_eagle/commit/875294f) wraps Strands agent calls in explicit parent spans (works around Strands OTel context detach)
- **Error classification:** [`langfuse_client.py`](../server/app/telemetry/langfuse_client.py) `classify_error()` tags by severity (infra / config / app) — ported from `nci-webtools-ctri-arti/gateway/langfuse.js`
- **Eval assertion helper:** [`server/tests/eval_helpers.py`](../server/tests/eval_helpers.py) `LangfuseTraceValidator` — used by `test_strands_eval.py` to assert trace presence + properties
- **Triage integration:** [`.github/workflows/nightly-triage.yml`](../.github/workflows/nightly-triage.yml) queries Langfuse via REST for 24h errors, cross-references CloudWatch + DynamoDB feedback, generates [`docs/development/*-report-triage-*.md`](./development/)

---

## 7. Env vars

Canonical source: [`infrastructure/cdk-eagle/config/environments.ts`](../infrastructure/cdk-eagle/config/environments.ts) (wired into ECS task definitions) + `server/.env` (local dev).

> **Note:** [`/.env.example`](../.env.example) is currently **missing Langfuse vars** — they must be added manually or set in your local `server/.env`. This is tracked as an open cleanup item.

### Required for local dev
```bash
AWS_REGION=us-east-1
AWS_PROFILE=eagle                  # for SSO (run `aws sso login --profile eagle` first)
EAGLE_SESSIONS_TABLE=eagle
S3_BUCKET=eagle-documents-695681773636-dev
COGNITO_USER_POOL_ID=...
COGNITO_CLIENT_ID=...
ANTHROPIC_API_KEY=sk-ant-...       # fallback when Bedrock unavailable
DEV_MODE=true                      # local only — bypasses Cognito
```

### Required for Langfuse (must be in `server/.env`)
```bash
LANGFUSE_HOST=https://us.cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PROJECT_ID=cmmsqvi2406aead071t0zhl7f

# Optional ARTI secondary project
LANGFUSE_ARTI_HOST=https://us.cloud.langfuse.com
LANGFUSE_ARTI_PUBLIC_KEY=pk-lf-...
LANGFUSE_ARTI_SECRET_KEY=sk-lf-...
LANGFUSE_ARTI_PROJECT_ID=cmmtw4vjq026kad07iu2y1nuc
```

### Optional / environment-specific
```bash
EAGLE_BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0   # override default Sonnet 4.6
EAGLE_ENVIRONMENT=dev              # dev|qa|staging|prod
EAGLE_BACKEND_URL=https://...      # frontend → backend URL for SSR
JIRA_BASE_URL=https://tracker.nci.nih.gov
JIRA_API_TOKEN=...
TEAMS_TRIAGE_WEBHOOK_URL=https://...
```

---

## 8. Ports

| Process | Port | Binding |
|---|---|---|
| FastAPI backend | 8000 | `localhost:8000` local · ALB → ECS cloud |
| Next.js frontend | 3000 | `localhost:3000` local · ALB → ECS cloud |
| Playwright dev | 9323 | Local Playwright report server |

---

## 9. CloudWatch log groups

| Log group | Source | Stream pattern |
|---|---|---|
| `/eagle/ecs/backend-{env}` | Backend FastAPI container (stdout) | `ecs/backend/{task-id}` |
| `/eagle/ecs/frontend-{env}` | Frontend Next.js container (stdout) | `ecs/frontend/{task-id}` |
| `/eagle/app` | Application events: e2e-judge, eval runs, admin ops | One stream per event category |
| `/eagle/telemetry` | Tool timing, conversation scoring, cost events | One stream per session |
| `/eagle/test-runs` | Eval suite stdout / publisher metrics | One stream per run |

Structured emitter: [`server/app/telemetry/cloudwatch_emitter.py`](../server/app/telemetry/cloudwatch_emitter.py).

---

## 10. GitHub Actions workflows

All under [`.github/workflows/`](../.github/workflows/).

| Workflow | Trigger | Purpose |
|---|---|---|
| [`deploy.yml`](../.github/workflows/deploy.yml) | push `main` / manual | OIDC auth → CDK deploy → Docker build → ECR → ECS rolling update → health verify |
| [`eval.yml`](../.github/workflows/eval.yml) | manual | Run Tier 1–4 eval suite, publish to CloudWatch + S3 |
| [`nightly-triage.yml`](../.github/workflows/nightly-triage.yml) | schedule 09:00 UTC (1 AM PST) | Run `/triage full` for dev + qa, cross-reference Langfuse + CloudWatch + DDB feedback, commit report + fix plan |
| [`feedback-approved.yml`](../.github/workflows/feedback-approved.yml) | manual dispatch | Approve user feedback → JIRA issue |
| [`triage-approved.yml`](../.github/workflows/triage-approved.yml) | manual dispatch | Approve triage fix plan → GitHub issues |
| [`morning-report.yml`](../.github/workflows/morning-report.yml) | schedule 09:00 UTC | Daily stats digest (users, documents, feedback) |
| [`jira-commits-sync.yml`](../.github/workflows/jira-commits-sync.yml) | push | Link commits to JIRA tickets |
| [`jira-commits-sync-agentic.yml`](../.github/workflows/jira-commits-sync-agentic.yml) | push | Agentic Claude-driven variant |
| [`claude-code-assistant.yml`](../.github/workflows/claude-code-assistant.yml) | PR comment `@claude` | PR review + Q&A bot |
| [`pr-diagram-linker.yml`](../.github/workflows/pr-diagram-linker.yml) | PR | Link Excalidraw diagrams referenced in PRs |

Authentication: **GitHub OIDC federation** via `DEPLOY_ROLE_ARN` secret → `EagleCiCdStack` role. Zero static IAM keys.

---

## 11. Environment tiers

| Setting | Dev | QA | Staging | Prod |
|---|---|---|---|---|
| Backend CPU / Mem | 512 / 1024 | 512 / 1024 | 512 / 1024 | 1024 / 2048 |
| Frontend CPU / Mem | 256 / 512 | 256 / 512 | 256 / 512 | 512 / 1024 |
| Desired / Max tasks | 1 / 4 | 1 / 2 | 2 / 6 | 2 / 10 |
| AZs / NAT Gateways | 2 / 1 | 2 / 1 | 2 / 2 | 3 / 3 |
| DynamoDB | On-demand | On-demand | On-demand | On-demand + PITR |
| Bedrock model | Haiku 4.5 (default for cost) | Haiku 4.5 | Sonnet 4.6 | Sonnet 4.6 |

Source: [`infrastructure/cdk-eagle/config/environments.ts`](../infrastructure/cdk-eagle/config/environments.ts).

---

## 12. Subscription tiers (feature gating)

Gated in [`server/app/subscription_service.py`](../server/app/subscription_service.py).

| Feature | Basic | Advanced | Premium |
|---|---|---|---|
| Daily messages | 50 | 200 | 1,000 |
| Monthly messages | 1,000 | 5,000 | 25,000 |
| Concurrent sessions | 1 | 3 | 10 |
| Session duration | 30 min | 60 min | 240 min |
| Skills available | `oa-intake`, `knowledge-retrieval` | + `compliance`, `tech-review`, `ingest-document` | all (`document-generator`, `admin-manager`, `admin-diagnostics`) |

---

## 13. Cost drivers

Billed per tenant via [`server/app/cost_attribution.py`](../server/app/cost_attribution.py) (input/output token tracking from Bedrock Converse responses):

| Service | Pricing model | Notes |
|---|---|---|
| Bedrock Claude | per input/output token | Cached reads discounted; tracked per tenant/user |
| DynamoDB | on-demand (pay-per-request) | ~99% of hot reads from GSIs |
| ECS Fargate | per vCPU-second + GB-second | Auto-scales on CPU |
| S3 | Standard + requests | Versioning adds to storage; eval bucket has 365-day expiration |
| CloudWatch Logs | per GB ingested + stored | Structured emitter keeps payloads small |
| Cognito | free first 50k MAU | |
| Lambda | first 1M req/mo free | Metadata extractor fires only on S3 upload |
| Langfuse | managed SaaS (free tier) | US region, not part of AWS bill |
