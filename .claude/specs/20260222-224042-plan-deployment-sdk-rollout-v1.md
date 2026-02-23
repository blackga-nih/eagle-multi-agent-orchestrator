# Deployment Plan: Staged Rollout — sdk_agentic_service Migration

**Date**: 2026-02-22T22:40:42
**Type**: Staged deployment — orchestration layer swap (`stream_chat` → `sdk_query`)
**Status**: Plan (not yet implemented)
**Author**: experts:deployment:plan
**Precursors**:
- `.claude/specs/20260222-223455-plan-claude-sdk-sdk-migration-v1.md`
- `.claude/specs/20260222-223657-plan-backend-sdk-wiring-v1.md`

---

## Executive Summary

This plan governs the deployment of the `sdk_agentic_service` migration across the
dev → staging → prod pipeline. The code change is a wiring swap only (~104 lines);
the SSE streaming contract is unchanged. Because there are only three environments
(no separate canary cluster), the rollout uses a **clean cutover strategy per
environment** (not a runtime feature flag) with hard validation gates between each
stage. `agentic_service.py` is kept; only the import wiring changes.

---

## Decision: Clean Cutover vs Runtime Feature Flag

### Recommendation: Clean Cutover per Environment

A runtime feature flag (`USE_SDK_ORCHESTRATION=true` checked in `streaming_routes.py`)
is **not recommended** for this migration. Reasoning:

| Factor | Feature Flag | Clean Cutover |
|--------|-------------|---------------|
| Code complexity | Adds permanent branch in hot path; must be removed later | Zero added branches |
| Rollback speed | Instant (flip env var, restart) | ~5 min ECS rolling update |
| Consistency | Risk of split traffic in multi-instance staging (2 tasks) | All tasks atomically on same version |
| SSE contract | No change either way | No change either way |
| Blast radius | Lower per-request but harder to reason about | Per-deploy — atomic and auditable |
| Cleanup debt | Flag must be removed in a follow-up PR | Nothing to clean up |

**Why clean cutover is safe here**:
1. `sdk_agentic_service.sdk_query()` is already fully implemented and has been tested
   in isolation (eval test 28). This is not an experimental path.
2. The SSE contract (TEXT/TOOL_USE/TOOL_RESULT/COMPLETE) is identical. Frontend
   changes are not required and rollback does not require a frontend redeploy.
3. `agentic_service.stream_chat` is preserved as a fallback. If rollback is needed,
   it is a single-step ECS redeploy to the previous ECR image tag — no code change needed.
4. The pipeline has three distinct environments (dev → staging → prod), each acting as
   a progressive validation gate. This is the correct canary mechanism for a pipeline
   of this scale — separate environments gate promotion rather than runtime traffic splits.

**When a feature flag would be the right choice**:
- A single production environment with no staging analog.
- Traffic-split canary at the ALB level (weighted target groups, not present here).
- The new path changes the user-visible response format.
- A/B testing is required.

None of these apply. Use clean cutover.

---

## Environment Variable Audit

### Confirmed: `DEV_MODE=false` in ECS Task Definition (CDK)

From `infrastructure/cdk-eagle/lib/compute-stack.ts` line 76:
```typescript
environment: {
  ...
  DEV_MODE: 'false',
  ...
}
```

`DEV_MODE=false` is hardcoded in CDK for the ECS task definition. It is **not
an injected secret** and does not come from GitHub Actions env vars or secrets.
The value `'false'` will be set in every environment that deploys via CDK —
dev, staging, and prod all inherit this same compute-stack definition.

**Risk assessment**:
- `DEV_MODE=true` is set in `deployment/docker-compose.dev.yml` (line 11) — local
  development only, never used by ECS.
- `deployment/scripts/deploy-lightsail.sh` line 138 explicitly sets `"DEV_MODE": "false"`.
- The GitHub Actions `deploy.yml` workflow does not pass `DEV_MODE` to the Docker build
  or ECS task definition. CDK controls it exclusively.
- **Conclusion**: There is no current mechanism by which `DEV_MODE=true` can reach
  staging or prod via the CI/CD pipeline. The risk exists only if someone manually
  edits `compute-stack.ts` or overrides ECS env vars in the console.

### Recommended CI Assertion

Despite the current safety, a CI assertion should be added as a defence-in-depth
measure. Add a step in the `deploy.yml` `deploy-infra` job, after CDK deploy and
before extracting outputs:

```yaml
- name: Assert DEV_MODE is false in ECS task definition
  run: |
    TASK_DEF=$(aws ecs describe-task-definition \
      --task-definition eagle-backend-${{ env.STAGE }} \
      --query "taskDefinition.containerDefinitions[0].environment" \
      --output json)
    DEV_MODE_VAL=$(echo "$TASK_DEF" | \
      python3 -c "import json,sys; envs=json.load(sys.stdin); \
      print(next((e['value'] for e in envs if e['name']=='DEV_MODE'), 'not_set'))")
    echo "DEV_MODE=$DEV_MODE_VAL"
    if [ "$DEV_MODE_VAL" != "false" ]; then
      echo "ERROR: DEV_MODE is '$DEV_MODE_VAL' — must be 'false' for non-dev environments"
      exit 1
    fi
    echo "PASS: DEV_MODE=false confirmed"
```

**Trigger**: Run this assertion in the `deploy-infra` job for all environments.
For a future multi-environment workflow (separate staging/prod jobs), gate the
staging and prod jobs on this assertion explicitly.

---

## Gate Sequence

```
[dev] → dev validation gates → [staging] → staging smoke gates → [prod] → prod verification
```

### Stage 0: Pre-Flight (before any deploy)

Run on the dev machine / feature branch before pushing to main:

- [ ] `ruff check app/` — 0 errors
- [ ] `python -m pytest tests/ -v -k "not test_28"` — all green
- [ ] `python -c "from agentic_service import execute_tool; print('OK')"` — no ImportError
- [ ] `grep -n "stream_chat" server/app/main.py server/app/streaming_routes.py` — empty output
- [ ] `just eval-quick 28` — PASS (sdk_query skill→subagent E2E)
- [ ] `just eval-aws` — PASS (tests 16–20: S3/DDB/CW/docgen)
- [ ] `just smoke` — 22 passed (local Docker stack)

All 7 gates must pass before committing. A failure at Stage 0 means the code is not
ready to deploy; fix in the feature branch.

---

### Stage 1: Dev Environment

**Trigger**: Merge PR to `main` → GitHub Actions `deploy.yml` fires automatically.

**What deploys**:
- CDK diff (no compute-stack changes expected for this migration)
- New backend Docker image with `sdk_query` as the active orchestration path
- ECS service update: `eagle-backend-dev` rolling deployment

**Deployment Checklist — Dev**:

- [ ] GitHub Actions `deploy.yml` completes green (all 4 jobs: deploy-infra, deploy-backend, deploy-frontend, verify)
- [ ] ECS backend service reaches `runningCount=desiredCount` (wait for `services-stable`)
- [ ] Backend health check passes: `curl -sf http://{BACKEND_URL}/api/health | jq .`
- [ ] DEV_MODE assertion: task definition shows `DEV_MODE=false`
- [ ] CloudWatch log group `/eagle/ecs/backend-dev` shows no `ImportError` or `AttributeError` on startup
- [ ] Run `just eval-quick 28` against dev environment — PASS
- [ ] Run `just smoke` against dev environment — 22 passed
- [ ] Check CloudWatch for SDK hook events (`/eagle/ecs/backend-dev`): look for `SubagentStart`, `PostToolUse` log entries
- [ ] Manually trigger one chat message via frontend and verify SSE response streams correctly

**Hold time**: 30 minutes of monitoring after successful smoke test before promoting to staging.

---

### Stage 2: Staging Environment

**Trigger**: Manual `workflow_dispatch` with `STAGE=staging` input (or a separate
staging workflow — see "Workflow Recommendation" below).

**Prerequisite**: Stage 1 gate checklist fully checked.

**What deploys**:
- CDK deploy with `STAGING_CONFIG` (2 NAT gateways, `desiredCount=2`, `maxCount=6`)
- Backend image (same SHA as dev — no rebuild) pushed to `eagle-backend-staging` ECR
- ECS service update: `eagle-backend-staging` rolling deployment (2 tasks)

**Deployment Checklist — Staging**:

- [ ] `STAGE=staging` passed correctly — verify CDK outputs show `eagle-backend-staging`
- [ ] Both ECS tasks reach RUNNING state (`runningCount=2`)
- [ ] DEV_MODE assertion passes on both tasks
- [ ] Backend health check on staging internal ALB: `GET /api/health` returns 200
- [ ] Smoke test against staging URL — 22 passed
- [ ] Run `just eval-quick 28` against staging — PASS
- [ ] Run `just eval-aws` against staging — PASS (tests 16–20)
- [ ] Verify CloudWatch eval dashboard (`EAGLE-Eval-Dashboard-staging`) shows pass rate >= 80%
- [ ] SNS alarm `eagle-eval-pass-rate-staging` NOT triggered
- [ ] Check CloudWatch `EAGLE/Eval` namespace: `PassRate` metric emitted
- [ ] Load test: fire 10 concurrent chat requests; verify no 5xx responses and no stream hangs

**Hold time**: 1 hour after successful eval suite before promoting to prod.

---

### Stage 3: Production

**Trigger**: Manual approval — run `workflow_dispatch` with `STAGE=prod` only after
Stage 2 hold time has elapsed and all staging gates are checked.

**What deploys**:
- CDK deploy with `PROD_CONFIG` (3 AZs, 3 NAT GW, 1024 CPU / 2048 MiB, `desiredCount=2`, `maxCount=10`)
- Backend image (same SHA as dev and staging — no rebuild)
- ECS service update: `eagle-backend-prod` rolling deployment (`minHealthyPercent=100` already set in CDK)

**Deployment Checklist — Prod**:

- [ ] Scheduled during a low-traffic window
- [ ] Notify stakeholders: "SDK orchestration migration deploying to prod in 5 minutes"
- [ ] CDK diff shows no unexpected changes (compute-stack env vars only)
- [ ] DEV_MODE assertion passes
- [ ] Both prod ECS tasks reach RUNNING state
- [ ] Backend health check on prod internal ALB: `GET /api/health` returns 200
- [ ] Frontend URL responds 200
- [ ] Manual end-to-end chat test: send one acquisition query, verify streaming response
- [ ] CloudWatch `/eagle/ecs/backend-prod` log group: no errors in first 10 minutes
- [ ] CloudWatch `EAGLE-Eval-Dashboard-prod`: pass rate >= 80% after first eval run
- [ ] Monitor ECS `CPUUtilization` and `MemoryUtilization` for 15 minutes — no anomalous spike
- [ ] Confirm no CloudWatch alarm `eagle-eval-pass-rate-prod` triggered

**Post-deploy action**: Pin the successful ECR image SHA as the prod baseline tag:
```bash
aws ecr put-image \
  --repository-name eagle-backend-prod \
  --image-tag prod-baseline-$(date +%Y%m%d) \
  --image-manifest "$(aws ecr batch-get-image \
    --repository-name eagle-backend-prod \
    --image-ids imageTag=${{ github.sha }} \
    --query 'images[0].imageManifest' --output text)"
```

---

## Rollback Runbook

### Decision Criteria: When to Roll Back

Roll back immediately if ANY of the following are observed:

| Signal | Threshold | Source |
|--------|-----------|--------|
| ECS task crash-looping | `stoppingCount > 0` and not draining | ECS console / CW alarm |
| Backend health check failing | 3 consecutive failures | ALB target group |
| SSE stream hangs | Chat message shows no response after 30s | Manual test / Playwright |
| 5xx error rate spike | > 1% of requests | ALB access logs / CW |
| CloudWatch eval pass rate | < 80% within first 30 minutes | `EAGLE-Eval-Dashboard` |
| `ImportError: cannot import name sdk_query` | Any occurrence | CW logs |
| `AttributeError` on `AssistantMessage.content` | Any occurrence | CW logs |

### Rollback Path: ECS Redeploy to Previous Image

The fastest rollback does not require a code change. ECS maintains the previous
task definition revision. Redeploy to the last known-good image SHA.

**Step 1 — Identify the previous good image SHA**:
```bash
# List recent images in ECR (newest first)
aws ecr describe-images \
  --repository-name eagle-backend-${STAGE} \
  --query "sort_by(imageDetails, &imagePushedAt)[-5:].imageTags" \
  --output table
```

**Step 2 — Update ECS service to use previous task definition revision**:
```bash
# Get current and previous task definition revisions
CURRENT_TD=$(aws ecs describe-services \
  --cluster eagle-${STAGE} \
  --services eagle-backend-${STAGE} \
  --query "services[0].taskDefinition" \
  --output text)

# Derive previous revision (current - 1)
PREV_REVISION=$(echo "$CURRENT_TD" | sed 's/:[0-9]*$//'):$(($(echo "$CURRENT_TD" | grep -oE '[0-9]+$') - 1))

echo "Rolling back to: $PREV_REVISION"

aws ecs update-service \
  --cluster eagle-${STAGE} \
  --service eagle-backend-${STAGE} \
  --task-definition "$PREV_REVISION" \
  --force-new-deployment
```

**Step 3 — Wait for rollback to stabilise**:
```bash
aws ecs wait services-stable \
  --cluster eagle-${STAGE} \
  --services eagle-backend-${STAGE}
echo "Rollback stable"
```

**Step 4 — Verify rollback**:
```bash
# Health check
curl -sf "http://${BACKEND_URL}/api/health" | jq .

# Confirm stream_chat is active (grep for old entrypoint reference in logs, or run eval 28 — expect FAIL)
# If rollback succeeded, test 28 will fail (sdk_query not wired) — that is expected and confirms rollback
```

**Step 5 — Notify stakeholders**:
- Announce rollback complete in team channel
- Open incident ticket with: environment, timestamp, symptom observed, CW log link
- Do NOT re-attempt the deployment until root cause is identified

### Rollback Path: Code-Level (if ECS TD rollback is insufficient)

If the task definition rollback does not resolve the issue (e.g., the issue is in
a CDK infrastructure change):

```bash
# Revert the migration commit on main
git revert {migration-commit-sha} --no-edit
git push origin main
# GitHub Actions deploy.yml fires: builds new image from reverted code, redeploys
```

**Expected revert time**: ~8 minutes (Docker build ~2 min + ECS deploy ~5 min + stabilise ~1 min).

### Rollback Time Estimates

| Action | Estimated Time |
|--------|---------------|
| ECS task definition rollback (no rebuild) | 3–5 min |
| `git revert` + CI rebuild + redeploy | 8–12 min |
| Manual ECS `force-new-deployment` (same image) | 3–5 min |

**Target RTO** (Recovery Time Objective) for prod: **< 10 minutes** using ECS TD rollback.

---

## Workflow Recommendation: Multi-Environment Deploy Support

The current `deploy.yml` deploys only `eagle-dev` (cluster and service names are
hardcoded via `env:` block). To support this staged rollout, add `STAGE` as a
`workflow_dispatch` input:

```yaml
on:
  workflow_dispatch:
    inputs:
      stage:
        description: 'Target environment (dev / staging / prod)'
        required: true
        default: 'dev'
        type: choice
        options: [dev, staging, prod]
```

Then parameterise the cluster and service names:
```yaml
env:
  STAGE: ${{ github.event.inputs.stage || 'dev' }}
  CLUSTER_NAME: eagle-${{ github.event.inputs.stage || 'dev' }}
  BACKEND_SERVICE: eagle-backend-${{ github.event.inputs.stage || 'dev' }}
  FRONTEND_SERVICE: eagle-frontend-${{ github.event.inputs.stage || 'dev' }}
```

This is a minimal change to `deploy.yml` — it does not require a new workflow file.
Merges to `main` continue to auto-deploy to `dev`. Staging and prod require
`workflow_dispatch` with the appropriate stage value, enforcing the promotion gate.

---

## DEV_MODE Risk Summary

| Risk Vector | Status | Mitigation |
|-------------|--------|------------|
| `docker-compose.dev.yml` sets `DEV_MODE=true` | Contained — local only, not used by ECS | No action needed; document in README |
| `compute-stack.ts` hardcodes `DEV_MODE: 'false'` | Safe — CDK controls ECS env | Add CI assertion (see above) |
| GitHub Actions `deploy.yml` passes no `DEV_MODE` | Safe — CDK is authoritative | CI assertion confirms post-deploy |
| Console override of ECS task env vars | Possible out-of-band risk | Add CI assertion + alert on manual ECS changes via CW Events |
| Staging inherits `DEV_CONFIG` spread (`...DEV_CONFIG`) | **Risk confirmed** — `STAGING_CONFIG` spreads `DEV_CONFIG`; if `DEV_CONFIG` added `DEV_MODE: 'true'`, it would propagate | Ensure `DEV_MODE` is NEVER added to `EagleConfig` interface or `DEV_CONFIG` |

**Recommended action for `environments.ts`**: Add an explicit comment guard:
```typescript
// WARNING: DEV_MODE is controlled by compute-stack.ts hardcoded string 'false'.
// Do NOT add DEV_MODE to EagleConfig — it would propagate to staging/prod via spread.
```

---

## CI Assertion: Full Implementation

Add this step to `.github/workflows/deploy.yml` in the `deploy-infra` job,
immediately after the `CDK Deploy` step and before `Extract CDK Outputs`:

```yaml
- name: Assert DEV_MODE=false in deployed ECS task definition
  run: |
    STAGE="${{ env.STAGE }}"
    TASK_DEF_ARN=$(aws ecs describe-services \
      --cluster "eagle-${STAGE}" \
      --services "eagle-backend-${STAGE}" \
      --query "services[0].taskDefinition" \
      --output text 2>/dev/null || echo "")
    if [ -z "$TASK_DEF_ARN" ]; then
      echo "INFO: ECS service not found (first deploy or staging/prod not yet created) — skipping DEV_MODE check"
      exit 0
    fi
    TASK_DEF_JSON=$(aws ecs describe-task-definition \
      --task-definition "$TASK_DEF_ARN" \
      --query "taskDefinition.containerDefinitions[0].environment" \
      --output json)
    DEV_MODE_VAL=$(echo "$TASK_DEF_JSON" | \
      python3 -c "
    import json, sys
    envs = json.load(sys.stdin)
    print(next((e['value'] for e in envs if e['name'] == 'DEV_MODE'), 'not_set'))
    ")
    echo "DEV_MODE=$DEV_MODE_VAL (stage=$STAGE)"
    if [ "$DEV_MODE_VAL" != "false" ]; then
      echo "SECURITY ERROR: DEV_MODE is '$DEV_MODE_VAL' in $STAGE — must be 'false'"
      echo "This bypasses Cognito JWT authentication for ALL requests."
      exit 1
    fi
    echo "PASS: DEV_MODE=false confirmed for stage=$STAGE"
```

**Why this assertion matters**:
`DEV_MODE=true` in `cognito_auth.py` bypasses JWT verification and returns a hardcoded
`demo-tenant / demo-user` context for all requests, regardless of the token presented.
If this were active in staging or prod, any unauthenticated client could send requests
as the demo tenant. The assertion makes this impossible to accidentally deploy.

---

## Complete Rollout Checklist (Print and Sign Off)

### Stage 0 — Code Ready (feature branch)
- [ ] `ruff check app/` → 0 errors
- [ ] `pytest tests/ -k "not test_28"` → all green
- [ ] `execute_tool` import check → OK
- [ ] `grep stream_chat server/app/main.py server/app/streaming_routes.py` → empty
- [ ] `just eval-quick 28` → PASS
- [ ] `just eval-aws` → PASS
- [ ] `just smoke` → 22 passed
- [ ] PR reviewed and approved

### Stage 1 — Dev
- [ ] GitHub Actions `deploy.yml` → all jobs green
- [ ] ECS `eagle-backend-dev` stable (runningCount = desiredCount)
- [ ] `/api/health` → 200
- [ ] DEV_MODE assertion → PASS
- [ ] CW logs: no startup errors
- [ ] `just eval-quick 28` against dev → PASS
- [ ] `just smoke` against dev → 22 passed
- [ ] SDK hook events visible in `/eagle/ecs/backend-dev`
- [ ] Manual chat smoke: SSE stream flows correctly
- [ ] **Hold 30 min** ← do not promote until elapsed

### Stage 2 — Staging
- [ ] Staging deploy via `workflow_dispatch` (stage=staging)
- [ ] Both ECS tasks RUNNING (2/2)
- [ ] DEV_MODE assertion → PASS
- [ ] `/api/health` → 200
- [ ] `just smoke` against staging → 22 passed
- [ ] `just eval-quick 28` → PASS
- [ ] `just eval-aws` → PASS
- [ ] CW eval dashboard pass rate >= 80%
- [ ] No SNS alert triggered
- [ ] 10 concurrent chat requests: 0 errors
- [ ] **Hold 1 hour** ← do not promote until elapsed

### Stage 3 — Prod
- [ ] Schedule during low-traffic window
- [ ] Stakeholder notification sent
- [ ] Prod deploy via `workflow_dispatch` (stage=prod)
- [ ] Both ECS tasks RUNNING (2/2)
- [ ] DEV_MODE assertion → PASS
- [ ] `/api/health` → 200
- [ ] Frontend → 200
- [ ] Manual end-to-end chat → streaming response received
- [ ] CW logs: no errors in 10 minutes
- [ ] CW eval pass rate >= 80%
- [ ] No CW alarm triggered
- [ ] CPU/Memory within normal range for 15 min
- [ ] Pin prod-baseline ECR tag
- [ ] **Migration complete — announce to team**

---

## Validation Commands Reference

```bash
# Stage 0 pre-flight (run from repo root)
cd server && ruff check app/
cd server && python -m pytest tests/ -v -k "not test_28"
grep -n "stream_chat" server/app/main.py server/app/streaming_routes.py
just eval-quick 28
just eval-aws
just smoke

# Post-deploy health check (replace URL with actual ALB DNS)
curl -sf "http://{BACKEND_URL}/api/health" | jq .

# ECS service stability check
aws ecs wait services-stable \
  --cluster eagle-{STAGE} \
  --services eagle-backend-{STAGE}

# ECS task status
aws ecs describe-services \
  --cluster eagle-{STAGE} \
  --services eagle-backend-{STAGE} \
  --query "services[].{name:serviceName,running:runningCount,desired:desiredCount}" \
  --output table

# Rollback to previous task definition
PREV_TD=$(aws ecs describe-task-definition \
  --task-definition eagle-backend-{STAGE} \
  --query "taskDefinition.taskDefinitionArn" \
  --output text | sed 's/:[0-9]*$/:/')
PREV_REV=$(( $(aws ecs list-task-definitions \
  --family-prefix eagle-backend-{STAGE} \
  --sort DESC \
  --query "taskDefinitionArns[1]" \
  --output text | grep -oE '[0-9]+$') ))
aws ecs update-service \
  --cluster eagle-{STAGE} \
  --service eagle-backend-{STAGE} \
  --task-definition "eagle-backend-{STAGE}:${PREV_REV}" \
  --force-new-deployment
aws ecs wait services-stable \
  --cluster eagle-{STAGE} \
  --services eagle-backend-{STAGE}
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `sdk_query` yields no `ResultMessage` → SSE stream hangs | Low | High | Fallback COMPLETE emit after generator exhausts (in backend plan); 30s timeout Playwright test catches this |
| ECS task crashes on startup (ImportError in `sdk_agentic_service`) | Low | High | Stage 0 lint + import check catches before deploy; ECS `startPeriod=60s` prevents premature health check failure |
| `DEV_MODE=true` leaked to staging/prod | Very Low (CDK hardcodes `false`) | Critical | CI assertion (see above) + STAGING_CONFIG spread audit |
| Multi-task staging sees stale in-memory session cache | Pre-existing | Medium | Not introduced by this migration; document as known issue |
| Rollback requires re-deploy of frontend (if SSE contract changed) | N/A — contract unchanged | None | SSE contract verified identical by upstream plans; no frontend change needed |
| ECR image tag `latest` overwritten before rollback | Low | Medium | Always tag with `github.sha`; rollback uses specific SHA tag not `latest` |
| `STAGING_CONFIG` spreads `DEV_CONFIG` → new fields inherit dev values | Known | Variable | Audit every new `EagleConfig` field addition; `DEV_MODE` must never be in `EagleConfig` |

---

*Scribe | 2026-02-22T22:40:42 | plan v1 | Format: markdown | Source: experts:deployment:plan*
