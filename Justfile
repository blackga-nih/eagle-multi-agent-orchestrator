# ============================================================
# EAGLE Platform — Unified Task Runner
# Usage: just --list
# ============================================================

set dotenv-load := false
set positional-arguments := true

# ── Constants ───────────────────────────────────────────────
# Override with: EAGLE_ENV=qa just <recipe>
ENV             := env("EAGLE_ENV", "dev")
REGION          := "us-east-1"
CLUSTER         := "eagle-" + ENV
BACKEND_SERVICE := "eagle-backend-" + ENV
FRONTEND_SERVICE := "eagle-frontend-" + ENV
BACKEND_REPO    := "eagle-backend-" + ENV
FRONTEND_REPO   := "eagle-frontend-" + ENV
CDK_DIR         := "infrastructure/cdk-eagle"
COMPOSE_FILE    := "deployment/docker-compose.dev.yml"

# ── First-Time Setup ──────────────────────────────────────

# Full first-time setup: CDK bootstrap → CDK deploy → containers → users → verify
setup: cdk-install _cdk-bootstrap cdk-deploy deploy create-users check-aws
    @echo ""
    @echo "=== Setup complete! ==="
    @echo "Run 'just urls' to see your live application URLs."
    @echo "Test user:  eagle-qa@nih.gov / Eagle2026!"
    @echo "Admins:     10 NIH accounts promoted to nci-admins (premium tier)"

# Create test + admin Cognito users with required tenant attributes
create-users:
    python3 scripts/create_users.py

# ── Development ─────────────────────────────────────────────

# Start backend + frontend via docker compose (foreground, with logs)
# For AWS SSO: run 'just dev-sso' instead, or set AWS_PROFILE before running
dev:
    docker compose -f {{COMPOSE_FILE}} up --build

# Start dev stack with AWS SSO credentials (mounts ~/.aws for SSO support)
# Requires: AWS SSO login completed (aws sso login)
# Usage: just dev-sso [PROFILE_NAME]
#   If PROFILE_NAME is provided, sets AWS_PROFILE; otherwise uses default profile
dev-sso PROFILE="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{{PROFILE}}" ]; then
        export AWS_PROFILE="{{PROFILE}}"
    fi
    # Verify AWS SSO credentials are available
    if ! aws sts get-caller-identity &>/dev/null; then
        echo "⚠️  AWS SSO credentials not found. Run: aws sso login"
        echo "   Or set AWS_PROFILE if using a specific profile"
        exit 1
    fi
    echo "✅ AWS credentials verified"
    docker compose -f {{COMPOSE_FILE}} up --build

# Start stack detached and wait for backend health (ready for smoke tests)
# For AWS SSO: run 'just dev-up-sso' instead
dev-up:
    docker compose -f {{COMPOSE_FILE}} up --build --detach
    python3 scripts/wait_for_backend.py

# Start stack detached with AWS SSO credentials
dev-up-sso PROFILE="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{{PROFILE}}" ]; then
        export AWS_PROFILE="{{PROFILE}}"
    fi
    if ! aws sts get-caller-identity &>/dev/null; then
        echo "⚠️  AWS SSO credentials not found. Run: aws sso login"
        exit 1
    fi
    docker compose -f {{COMPOSE_FILE}} up --build --detach
    python3 scripts/wait_for_backend.py

# Tear down local docker compose stack
dev-down:
    docker compose -f {{COMPOSE_FILE}} down

# Integration smoke tests — verify pages load and backend is reachable
# Requires stack running (just dev-up). Default: base.
#   base  → connectivity: nav + home page (9 tests, headless, ~14s)
#   mid   → all pages: nav, home, admin, documents, workflows (26 tests, headless, ~22s)
#   full  → all pages + basic agent response: adds chat spec (30 tests, headless, ~47s)
smoke LEVEL="base":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{LEVEL}}" in
      base)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          navigation.spec.ts intake.spec.ts \
          --project=chromium --workers=4
        ;;
      mid)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts documents.spec.ts workflows.spec.ts \
          --project=chromium --workers=4
        ;;
      full)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts documents.spec.ts workflows.spec.ts chat.spec.ts \
          --project=chromium --workers=4
        ;;
      *)
        echo "Unknown level '{{LEVEL}}'. Valid: base | mid | full" && exit 1
        ;;
    esac

# Same as smoke base but with a visible browser window (headed, sequential)
smoke-ui:
    cd client && BASE_URL=http://localhost:3000 npx playwright test navigation.spec.ts intake.spec.ts --project=chromium --headed --workers=1

# One-command local smoke: start stack detached, wait for health, run smoke tests
dev-smoke: dev-up smoke

# One-command local smoke with visible browser window
dev-smoke-ui: dev-up smoke-ui

# ─────────────────────────────────────────────────────────────────────────────
# Post-deploy smoke (devbox → deployed ALB)
# ─────────────────────────────────────────────────────────────────────────────
# Validate a deployed dev/qa environment end-to-end via the EC2 devbox inside
# the VPC. POSTs a research-tool query, walks the chat UI with Playwright,
# captures screenshots at key moments, uploads everything to the eval bucket,
# and prints PASS/FAIL with the s3:// artifact prefix.
#
# This is the canonical post-deploy validation pattern — see
# CLAUDE.md > Post-Deploy Smoke. Use it after every meaningful deploy.
#
# Usage:
#   just dev-smoke-deployed                                    # default scenario
#   just dev-smoke-deployed research_source_transparency       # explicit
#   just qa-smoke-deployed research_source_transparency        # qa env
dev-smoke-deployed SCENARIO="research_source_transparency":
    python scripts/_remote_post_deploy_smoke.py --env dev --scenario {{SCENARIO}}

qa-smoke-deployed SCENARIO="research_source_transparency":
    python scripts/_remote_post_deploy_smoke.py --env qa --scenario {{SCENARIO}} --auth

# Run the full triage-validation smoke suite (Q4/Q5/UC2.1 + diagnostics).
# Use after the 8-PR triage stack ships (PRs #169-#177) to confirm:
#   - PR #169 routing: agent_guidance loads + Part-15 misroute fixed
#   - PR #171 UC2.1: workflow asks about quote/508 before generating PR
#   - PR #172 JEFO: response cites all 10 FAR 16.507-6(d)(2) elements
#   - PR #174 matrix: $20M-$90M tier names HCA + Competition Advocate
#   - PR #175 kb_inventory: agent calls the new diagnostic tool
#   - PR #177 filter: protest/J&A docs dropped from micro-purchase results
#
# Stops at first failing scenario by default — pass CONTINUE=1 to run all.
dev-smoke-triage CONTINUE="0":
    #!/usr/bin/env bash
    set -uo pipefail
    fail_count=0
    for sc in research_source_transparency jefo_q4 sbir_q5 uc21_microscope kb_inventory_diagnostic; do
        echo ""
        echo "=========================================="
        echo "SCENARIO: $sc"
        echo "=========================================="
        if ! python scripts/_remote_post_deploy_smoke.py --env dev --scenario "$sc"; then
            fail_count=$((fail_count + 1))
            echo "[FAIL] $sc"
            if [ "{{CONTINUE}}" != "1" ]; then
                echo "Stopping at first failure. Pass CONTINUE=1 to run all."
                exit 1
            fi
        fi
    done
    if [ $fail_count -eq 0 ]; then
        echo ""
        echo "[ALL PASS] 5/5 triage scenarios passed."
    else
        echo ""
        echo "[FAIL] $fail_count scenario(s) failed."
        exit 1
    fi

# Kill stale EAGLE backend/frontend processes on Windows + Unix.
# Handles uvicorn --reload zombie-child pattern that taskkill-by-PID misses.
kill-stale:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== kill-stale: clearing ports 8000, 3000, 3001 ==="
    if command -v taskkill >/dev/null 2>&1; then
        # Pass 1: kill by port PID
        for port in 8000 3000 3001; do
            for pid in $(netstat -ano 2>/dev/null | grep ":${port} " | grep LISTENING | awk '{print $NF}' | sort -u | grep -v '^0$'); do
                echo "  kill (by port $port): PID $pid"
                taskkill /F /T /PID "$pid" 2>/dev/null || true
            done
            # IPv6 listeners netstat can miss
            for pid in $(powershell.exe -NoProfile -Command \
              "(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).OwningProcess" 2>/dev/null | tr -d '\r' | sort -u); do
                [ -n "$pid" ] && [ "$pid" != "0" ] && {
                    echo "  kill (by port $port, ps): PID $pid"
                    taskkill /F /T /PID "$pid" 2>/dev/null || true
                }
            done
        done
        # Pass 2: kill orphaned children by command-line match via WMI.
        # Catches zombie uvicorn workers whose parent already died.
        powershell.exe -NoProfile -Command \
          "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'python' -and \$_.CommandLine -match 'uvicorn.*app\\.main' } | ForEach-Object { Write-Host ('  kill (by cmdline): PID ' + \$_.ProcessId); Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>/dev/null || true
        powershell.exe -NoProfile -Command \
          "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'node.exe' -and \$_.CommandLine -match 'next dev|\\.next' } | ForEach-Object { Write-Host ('  kill (by cmdline): PID ' + \$_.ProcessId); Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>/dev/null || true
    else
        for port in 8000 3000 3001; do
            for pid in $(lsof -ti tcp:${port} 2>/dev/null | sort -u); do
                echo "  kill (by port $port): PID $pid"
                kill "$pid" 2>/dev/null || true
            done
        done
    fi
    # Pass 3: verify ports free, up to 8 seconds
    for port in 8000 3000; do
        for i in 1 2 3 4 5 6 7 8; do
            if command -v taskkill >/dev/null 2>&1; then
                netstat -ano 2>/dev/null | grep ":${port} " | grep -q LISTENING || break
            else
                lsof -ti tcp:${port} >/dev/null 2>&1 || break
            fi
            sleep 1
        done
    done
    if command -v taskkill >/dev/null 2>&1 && netstat -ano 2>/dev/null | grep -q ':8000 .*LISTENING'; then
        echo ""
        echo "  WARNING: port 8000 still held after kill-stale."
        echo "  Likely a Windows kernel-ghost LISTEN entry (PID dead, kernel won't release)."
        echo "  Options:"
        echo "    1) Reboot Windows"
        echo "    2) Admin PowerShell: netsh winsock reset (requires reboot)"
        echo "    3) Use fallback port: just dev-local-8001"
        exit 1
    fi
    echo "  ports free"

# Start backend + frontend locally with hot reload (no docker) — kills stale processes first
dev-local:
    #!/usr/bin/env bash
    set -euo pipefail
    just kill-stale
    # Clear Next.js cache — retry loop because file locks can linger briefly
    for attempt in 1 2 3 4 5; do
        rm -rf client/.next 2>/dev/null || true
        if [ ! -d client/.next ]; then
            echo "  .next cache cleared"
            break
        fi
        echo "  .next still locked, retrying ($attempt/5)..."
        sleep 2
    done
    if [ -d client/.next ]; then
        echo "  WARNING: could not fully delete .next — may see stale cache errors"
        echo "  Try closing terminals/editors accessing client/ and re-run"
    fi
    unset FASTAPI_URL
    export FASTAPI_URL=http://127.0.0.1:8000
    echo "=== Starting backend (port 8000) ==="
    cd server && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --reload-dir ../eagle-plugin &
    BACKEND_PID=$!
    sleep 5
    echo "=== Starting frontend (port 3000) ==="
    cd client && npm run dev &
    FRONTEND_PID=$!
    echo ""
    echo "Backend PID: $BACKEND_PID (http://localhost:8000)"
    echo "Frontend PID: $FRONTEND_PID (http://localhost:3000)"
    echo "Press Ctrl+C to stop both."
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
    wait

# Start backend + frontend locally with hot reload and AWS SSO credentials
# Usage: just dev-local-sso [PROFILE_NAME]
dev-local-sso PROFILE="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{{PROFILE}}" ]; then
        export AWS_PROFILE="{{PROFILE}}"
    fi
    if ! aws sts get-caller-identity &>/dev/null; then
        echo "AWS SSO credentials not found. Run: aws sso login"
        echo "Or pass a profile: just dev-local-sso <profile-name>"
        exit 1
    fi
    just dev-local

# Start FastAPI backend only with hot reload (local) — kills stale processes on port 8000 first
dev-backend:
    #!/usr/bin/env bash
    set -euo pipefail
    just kill-stale
    cd server && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app --reload-dir ../eagle-plugin

# Start Next.js frontend only with hot reload (local) — kills stale processes on port 3000 first
dev-frontend:
    #!/usr/bin/env bash
    set -euo pipefail
    just kill-stale
    # Clear stale .next cache
    for attempt in 1 2 3; do
        rm -rf client/.next 2>/dev/null || true
        [ ! -d client/.next ] && break
        sleep 2
    done
    unset FASTAPI_URL
    cd client && npm run dev

# Fallback when port 8000 is permanently held by a kernel ghost — runs backend on 8001
dev-local-8001:
    #!/usr/bin/env bash
    set -euo pipefail
    # Kill 3000 + 3001 but leave 8000 alone (it's the zombie we're working around)
    if command -v taskkill >/dev/null 2>&1; then
        for port in 3000 3001 8001; do
            for pid in $(netstat -ano 2>/dev/null | grep ":${port} " | grep LISTENING | awk '{print $NF}' | sort -u | grep -v '^0$'); do
                taskkill /F /T /PID "$pid" 2>/dev/null || true
            done
        done
    fi
    export FASTAPI_URL=http://127.0.0.1:8001
    echo "=== Starting backend on port 8001 (8000 fallback) ==="
    cd server && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir app --reload-dir ../eagle-plugin &
    BACKEND_PID=$!
    sleep 5
    echo "=== Starting frontend (port 3000) ==="
    cd client && FASTAPI_URL=http://127.0.0.1:8001 npm run dev &
    FRONTEND_PID=$!
    echo ""
    echo "Backend PID: $BACKEND_PID (http://localhost:8001)"
    echo "Frontend PID: $FRONTEND_PID (http://localhost:3000)"
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
    wait

# ── Format ──────────────────────────────────────────────────

# Format all code (Python + TypeScript)
format: format-py format-ts

# Format Python with ruff
format-py:
    cd server && python -m ruff format app/

# Format TypeScript/JS with Prettier
format-ts:
    cd client && npx prettier --write .

# Check formatting without modifying files (CI-friendly)
format-check:
    cd server && python -m ruff format --check app/
    cd client && npx prettier --check .

# ── Lint ────────────────────────────────────────────────────

# Run all linters (Python + TypeScript)
lint: lint-py lint-ts

# Lint Python with ruff
lint-py:
    cd server && .venv/bin/python -m ruff check app/

# Type-check TypeScript
lint-ts:
    cd client && npx tsc --noEmit

# ── Test ────────────────────────────────────────────────────

# Run backend unit tests
test *ARGS:
    docker compose -f deployment/docker-compose.dev.yml run --rm backend sh -lc "cd /app && pytest tests/ -v {{ARGS}}"

# Run Playwright E2E tests against Fargate (headless)
test-e2e *ARGS:
    python3 -c "import boto3; c=boto3.client('elbv2',region_name='us-east-1'); dns=[lb['DNSName'] for lb in c.describe_load_balancers()['LoadBalancers'] if 'Front' in lb['LoadBalancerName']]; print(f'Testing against: http://{dns[0]}')" && cd client && npx playwright test {{ARGS}}

# Run Playwright E2E tests against Fargate with a visible browser window
test-e2e-ui *ARGS:
    python3 -c "import boto3; c=boto3.client('elbv2',region_name='us-east-1'); dns=[lb['DNSName'] for lb in c.describe_load_balancers()['LoadBalancers'] if 'Front' in lb['LoadBalancerName']]; print(f'Testing against: http://{dns[0]}')" && cd client && npx playwright test {{ARGS}} --headed

# E2E use case tests — complete acquisition workflows through the UI
# Headed + sequential so you can watch each scenario play out.
# Requires running stack with live AI backend (just dev-up).
#   intake  → describe acquisition need → agent returns pathway + document list
#   doc     → request SOW → agent generates document structure
#   far     → ask FAR question → agent returns regulation reference with citation
#   full    → all three use case workflows in sequence
e2e WORKFLOW="full":
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{WORKFLOW}}" in
      intake)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          uc-intake.spec.ts --project=chromium --headed --workers=1
        ;;
      doc)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          uc-document.spec.ts --project=chromium --headed --workers=1
        ;;
      far)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          uc-far-search.spec.ts --project=chromium --headed --workers=1
        ;;
      full)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          uc-intake.spec.ts uc-document.spec.ts uc-far-search.spec.ts \
          --project=chromium --headed --workers=1
        ;;
      *)
        echo "Unknown workflow '{{WORKFLOW}}'. Valid: intake | doc | far | full" && exit 1
        ;;
    esac

# ── Eval Suite ──────────────────────────────────────────────

# Run specific eval tests (REQUIRED — never run all by default, costs $$$)
# Examples:
#   just eval 1,2,3          # three tests
#   just eval 16,17,18,19,20 # AWS subset (or use `just eval-aws`)
#   just eval-all            # explicit full-suite (costs ~$5-10, asks for confirmation)
eval TESTS:
    cd server && python3 -u tests/test_eagle_sdk_eval.py --model haiku --tests {{TESTS}}

# Alias retained for backwards compat — same as `just eval TESTS`
eval-quick TESTS: (eval TESTS)

# Run AWS tool eval tests only (16-20) — fixed small subset, safe to invoke
eval-aws:
    cd server && python3 -u tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20

# Run the FULL eval suite (all tests) — explicit opt-in, costs $$$
# Prints cost warning + 5s pause before running.
# CI: invoked only when deploy.yml workflow_dispatch input run_eval=true.
eval-all:
    @echo "WARNING: Running the FULL eval suite — this hits Bedrock for every test."
    @echo "Estimated cost: \$5-10 per run."
    @echo "Press Ctrl+C in the next 5 seconds to abort..."
    @sleep 5
    cd server && python3 -u tests/test_eagle_sdk_eval.py --model haiku

# ── Docker Build ────────────────────────────────────────────

# Build all containers locally
build:
    docker compose -f {{COMPOSE_FILE}} build

# Build backend image (linux/amd64 for ECS Fargate)
build-backend:
    docker build --platform linux/amd64 -f deployment/docker/Dockerfile.backend -t {{BACKEND_REPO}}:latest .

# Build frontend image (fetches Cognito config from CDK outputs, linux/amd64 for ECS Fargate)
build-frontend:
    python3 -c "\
    import boto3, subprocess, sys; \
    cf = boto3.client('cloudformation', region_name='us-east-1'); \
    stacks = cf.describe_stacks(StackName='EagleCoreStack')['Stacks'][0]['Outputs']; \
    outputs = {o['OutputKey']: o['OutputValue'] for o in stacks}; \
    pool_id = [v for k,v in outputs.items() if 'UserPoolId' in k and 'Client' not in k][0]; \
    client_id = [v for k,v in outputs.items() if 'ClientId' in k][0]; \
    print(f'Building frontend: POOL_ID={pool_id} CLIENT_ID={client_id}'); \
    sys.exit(subprocess.call([ \
      'docker', 'build', '--platform', 'linux/amd64', '-f', 'deployment/docker/Dockerfile.frontend', \
      '--build-arg', f'NEXT_PUBLIC_COGNITO_USER_POOL_ID={pool_id}', \
      '--build-arg', f'NEXT_PUBLIC_COGNITO_CLIENT_ID={client_id}', \
      '--build-arg', 'NEXT_PUBLIC_COGNITO_REGION=us-east-1', \
      '-t', '{{FRONTEND_REPO}}:latest', '.']))"

# ── Deploy (ECR Push + ECS Update) ─────────────────────────

# Full deploy: build both images, push to ECR, update ECS, wait
deploy: _ecr-login build-backend build-frontend _push-backend _push-frontend _ecs-update-all _ecs-wait-all status

# Deploy backend only
deploy-backend: _ecr-login build-backend _push-backend _ecs-update-backend _ecs-wait-backend
    @echo "Backend deployed."

# Deploy frontend only
deploy-frontend: _ecr-login build-frontend _push-frontend _ecs-update-frontend _ecs-wait-frontend
    @echo "Frontend deployed."

# ── Infrastructure (CDK) ───────────────────────────────────

# Install CDK dependencies
cdk-install:
    cd {{CDK_DIR}} && npm ci

# Synthesize CDK stacks (compile check)
cdk-synth:
    cd {{CDK_DIR}} && npx cdk synth --quiet

# Show pending CDK changes
cdk-diff:
    cd {{CDK_DIR}} && npx cdk diff --all 2>&1 || true

# Deploy all CDK stacks
cdk-deploy:
    cd {{CDK_DIR}} && npx cdk deploy --all --require-approval never

# Deploy storage stack only (EagleStorageStack)
cdk-deploy-storage:
    cd {{CDK_DIR}} && npx cdk deploy EagleStorageStack --require-approval never

# Refresh AWS SSO session — run this when credentials expire
# Usage: just aws-login                          (uses default profile)
#        just aws-login YOUR_ACCOUNT_PowerUserAccess
aws-login PROFILE="eagle":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Refreshing AWS SSO session (profile: {{PROFILE}}) ==="
    aws sso login --profile {{PROFILE}}
    export AWS_PROFILE={{PROFILE}}
    echo ""
    echo "Verifying..."
    aws sts get-caller-identity --profile {{PROFILE}}
    echo ""
    echo "Session active. Run your next command with:"
    echo "  AWS_PROFILE={{PROFILE}} just <command>"
    echo "Or export it for the session:"
    echo "  export AWS_PROFILE={{PROFILE}}"


# Stop the dev box to avoid idle charges (~$0.04/hr)
# Usage: just devbox-stop <instance-id>
devbox-stop INSTANCE_ID:
    aws ec2 stop-instances --instance-ids {{INSTANCE_ID}}
    echo "Dev box stopped. Start again with: just devbox-start {{INSTANCE_ID}}"

# Start the dev box back up
devbox-start INSTANCE_ID:
    aws ec2 start-instances --instance-ids {{INSTANCE_ID}}
    aws ec2 wait instance-running --instance-ids {{INSTANCE_ID}}
    echo "Dev box running. Get IP with:"
    echo "  aws ec2 describe-instances --instance-ids {{INSTANCE_ID}} --query 'Reservations[].Instances[].PublicIpAddress' --output text"

# ── Devbox Deploy ──────────────────────────────────────────

# Deploy code to EC2 devbox: git sync → docker compose up → health check
# Usage: just devbox-deploy [branch] [remote]
devbox-deploy BRANCH="main" REPO="origin":
    python scripts/devbox_deploy.py deploy --branch {{BRANCH}} --repo {{REPO}}

# Open SSM port forwards: localhost:3000 (frontend) + localhost:8000 (backend)
# Keep this running in a terminal while testing. Ctrl+C to close.
devbox-tunnel:
    python scripts/devbox_deploy.py tunnel

# Check container status and endpoint health on devbox
devbox-health:
    python scripts/devbox_deploy.py health

# Tail container logs on devbox (default: backend)
devbox-logs SERVICE="backend":
    python scripts/devbox_deploy.py logs {{SERVICE}}

# Stop containers on devbox (instance keeps running)
devbox-teardown:
    python scripts/devbox_deploy.py teardown

# Full devbox pipeline: deploy → open tunnel → run smoke tests
# Runs deploy + health check, then opens tunnel and smoke tests in parallel.
# Usage: just devbox-ship [branch]
devbox-ship BRANCH="main":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Step 1: Deploy to devbox ==="
    python scripts/devbox_deploy.py deploy --branch {{BRANCH}}
    echo ""
    echo "=== Step 2: Open tunnel (background) ==="
    python scripts/devbox_deploy.py tunnel &
    TUNNEL_PID=$!
    echo "Tunnel PID: $TUNNEL_PID"
    echo "Waiting 5s for tunnels to establish..."
    sleep 5
    echo ""
    echo "=== Step 3: Smoke tests ==="
    # Quick health check through tunnel
    curl -sf http://localhost:8000/api/health && echo " Backend OK" || echo " Backend not reachable"
    curl -so /dev/null -w "Frontend: HTTP %{http_code}\n" http://localhost:3000/ || echo " Frontend not reachable"
    echo ""
    echo "=== Step 4: Playwright smoke tests ==="
    cd client && npx playwright test --grep @smoke 2>/dev/null || echo "No @smoke tests found or Playwright not configured — skipping"
    cd ..
    echo ""
    echo "=== Done ==="
    echo "Tunnel still running (PID: $TUNNEL_PID). Press Ctrl+C to close."
    echo "Run more tests:  just devbox-smoke"
    echo "View logs:       just devbox-logs backend"
    echo "Teardown:        just devbox-teardown"
    wait $TUNNEL_PID 2>/dev/null || true

# Run smoke tests against localhost (requires tunnel running)
devbox-smoke:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Smoke Tests (via tunnel) ==="
    echo ""
    echo "--- Health endpoints ---"
    curl -sf http://localhost:8000/api/health | python3 -m json.tool 2>/dev/null || echo "Backend: not reachable (is tunnel running?)"
    curl -so /dev/null -w "Frontend: HTTP %{http_code}\n" http://localhost:3000/ || echo "Frontend: not reachable (is tunnel running?)"
    echo ""
    echo "--- Playwright E2E ---"
    cd client && npx playwright test 2>/dev/null || echo "Playwright tests not configured or failed"

# ── Operations ──────────────────────────────────────────────

# Show ECS service health and running task counts
status:
    python3 -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    elb = boto3.client('elbv2', region_name='us-east-1'); \
    resp = ecs.describe_services(cluster='{{CLUSTER}}', services=['{{BACKEND_SERVICE}}','{{FRONTEND_SERVICE}}']); \
    print('=== EAGLE Platform Status ({{ENV}}) ==='); \
    print(); \
    print(f'{\"Service\":<25s} {\"Status\":<10s} {\"Running\":>7s} {\"Desired\":>7s}'); \
    print('-' * 52); \
    [print(f'{s[\"serviceName\"]:<25s} {s[\"status\"]:<10s} {s[\"runningCount\"]:>7d} {s[\"desiredCount\"]:>7d}') for s in resp['services']]; \
    print(); \
    lbs = elb.describe_load_balancers()['LoadBalancers']; \
    front = next((lb['DNSName'] for lb in lbs if 'Front' in lb['LoadBalancerName']), 'unknown'); \
    back = next((lb['DNSName'] for lb in lbs if 'Backe' in lb['LoadBalancerName']), 'unknown'); \
    print(f'Frontend: http://{front}'); \
    print(f'Backend:  http://{back}')"

# Tail ECS logs for a service (default: backend)
logs SERVICE="backend":
    python3 -c "\
    import boto3, sys, time; \
    svc = '{{SERVICE}}'; \
    lg = f'/eagle/ecs/{svc}-{{ENV}}'; \
    client = boto3.client('logs', region_name='us-east-1'); \
    import datetime; \
    start = int((datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp() * 1000); \
    resp = client.filter_log_events(logGroupName=lg, startTime=start, limit=100, interleaved=True); \
    [print(e.get('message','').strip()) for e in resp.get('events',[])]"

# Print live URLs from ALBs
urls:
    python3 -c "\
    import boto3; \
    elb = boto3.client('elbv2', region_name='us-east-1'); \
    lbs = elb.describe_load_balancers()['LoadBalancers']; \
    front = next((lb['DNSName'] for lb in lbs if 'Front' in lb['LoadBalancerName']), 'unknown'); \
    back = next((lb['DNSName'] for lb in lbs if 'Backe' in lb['LoadBalancerName']), 'unknown'); \
    print(f'Frontend: http://{front}'); \
    print(f'Backend:  http://{back}')"

# Verify AWS credentials and service connectivity (all EAGLE resources)
check-aws:
    python3 scripts/check_aws.py

# ── Debug webhook channel toggle ───────────────────────────
# Flip DEBUG_WEBHOOK_ENABLED in server/.env. Backend restart required
# for the change to take effect (value is read at module import time).

# Turn ON the debug Teams channel (requires DEBUG_WEBHOOK_URL to be set)
debug-on:
    @bash scripts/toggle_debug_webhook.sh on

# Turn OFF the debug Teams channel
debug-off:
    @bash scripts/toggle_debug_webhook.sh off

# Print current debug-channel state (ENABLED flag + URL status)
debug-status:
    @bash scripts/toggle_debug_webhook.sh status

# Verify AWS SSO credentials are valid and can access Bedrock
check-sso:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Checking AWS SSO Credentials ==="
    echo ""
    echo "1. Testing AWS identity..."
    aws sts get-caller-identity || (echo "❌ Failed to get caller identity" && exit 1)
    echo "✅ AWS identity verified"
    echo ""
    echo "2. Testing Bedrock access..."
    aws bedrock list-foundation-models --region us-east-1 --query 'modelSummaries[?contains(modelId, `claude`)].modelId' --output table || (echo "❌ Failed to access Bedrock" && exit 1)
    echo "✅ Bedrock access verified"
    echo ""
    echo "3. Testing S3 access..."
    aws s3 ls s3://eagle-documents-ACCOUNT-dev --region us-east-1 &>/dev/null || echo "⚠️  S3 bucket 'eagle-documents-ACCOUNT-dev' not accessible (may not exist)"
    echo ""
    echo "=== All checks passed ==="

# ── Langfuse Analytics ─────────────────────────────────────

# Analytical rollup of Langfuse traces — skills/tools/documents breakdown.
# WINDOW: today (default) | 1h | 4h | 24h | 7d
# ENV:    all (default) | local | dev | qa | prod | unknown
# OUT:    optional markdown output path
langfuse-report WINDOW="today" ENV="all" OUT="":
    #!/usr/bin/env bash
    set -euo pipefail
    ARGS=( --window="{{WINDOW}}" --env="{{ENV}}" )
    if [ -n "{{OUT}}" ]; then ARGS+=( --out="{{OUT}}" ); fi
    python3 .claude/skills/langfuse-analytics/scripts/langfuse_report.py "${ARGS[@]}"

# Shorthand: dump today's rollup to docs/development/ with a timestamped filename
langfuse-report-today:
    #!/usr/bin/env bash
    set -euo pipefail
    TS=$(date -u +%Y%m%d-%H%M%S)
    OUT="docs/development/${TS}-report-langfuse-analytics-today-v1.md"
    mkdir -p docs/development
    python3 .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=today --env=all --out="$OUT"
    echo ""
    echo "📊 Report written to $OUT"

# Shorthand: last 7 days rollup
langfuse-report-week:
    python3 .claude/skills/langfuse-analytics/scripts/langfuse_report.py --window=7d --env=all

# HTML dashboard: KPI cards, per-user cost table, CloudWatch section (optional)
langfuse-report-html WINDOW="today" ENV="all":
    #!/usr/bin/env bash
    set -euo pipefail
    TS=$(date -u +%Y%m%d-%H%M%S)
    MD="docs/development/${TS}-report-langfuse-analytics-{{WINDOW}}-v1.md"
    HTML="docs/development/${TS}-report-langfuse-analytics-{{WINDOW}}-v1.html"
    mkdir -p docs/development
    python3 .claude/skills/langfuse-analytics/scripts/langfuse_report.py \
        --window="{{WINDOW}}" --env="{{ENV}}" --out="$MD" --html="$HTML" > /dev/null
    echo ""
    echo "📊 HTML dashboard → $HTML"
    echo "📝 Markdown       → $MD"

# Full analytics: Langfuse + CloudWatch scan → HTML dashboard (requires SSO login)
langfuse-report-full WINDOW="24h" ENV="all" PROFILE="eagle":
    #!/usr/bin/env bash
    set -euo pipefail
    TS=$(date -u +%Y%m%d-%H%M%S)
    MD="docs/development/${TS}-report-langfuse-full-{{WINDOW}}-v1.md"
    HTML="docs/development/${TS}-report-langfuse-full-{{WINDOW}}-v1.html"
    JSON="docs/development/${TS}-report-langfuse-full-{{WINDOW}}-v1.json"
    mkdir -p docs/development
    python3 .claude/skills/langfuse-analytics/scripts/langfuse_report.py \
        --window="{{WINDOW}}" --env="{{ENV}}" \
        --out="$MD" --html="$HTML" --json="$JSON" \
        --cloudwatch --profile="{{PROFILE}}" > /dev/null
    echo ""
    echo "📊 HTML dashboard → $HTML"
    echo "📝 Markdown       → $MD"
    echo "🧾 Raw JSON       → $JSON"

# Build + POST a Langfuse activity Adaptive Card to Teams (uses TEAMS_WEBHOOK_URL)
langfuse-post-teams WINDOW="24h" ENV="all":
    python3 scripts/langfuse_post_teams.py --window="{{WINDOW}}" --env="{{ENV}}"

# Preview the Teams card JSON without posting
langfuse-post-teams-dry WINDOW="24h" ENV="all":
    python3 scripts/langfuse_post_teams.py --window="{{WINDOW}}" --env="{{ENV}}" --dry-run

# ── Validation Ladder ──────────────────────────────────────

# L5: Smoke tests against deployed Fargate environment (requires AWS creds + live stack)
# Levels: base (nav+home) | mid (all pages) | full (all + chat)
smoke-prod LEVEL="mid":
    #!/usr/bin/env bash
    set -euo pipefail
    ALB=$(python3 -c "import boto3; c=boto3.client('elbv2',region_name='us-east-1'); lbs=c.describe_load_balancers()['LoadBalancers']; front=next(lb['DNSName'] for lb in lbs if 'Front' in lb['LoadBalancerName']); print(f'http://{front}')")
    echo "Smoke testing against: $ALB"
    case "{{LEVEL}}" in
      base)
        cd client && BASE_URL=$ALB npx playwright test \
          navigation.spec.ts intake.spec.ts \
          --project=chromium --workers=4
        ;;
      mid)
        cd client && BASE_URL=$ALB npx playwright test \
          navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts documents.spec.ts workflows.spec.ts \
          --project=chromium --workers=4
        ;;
      full)
        cd client && BASE_URL=$ALB npx playwright test \
          navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts documents.spec.ts workflows.spec.ts chat.spec.ts \
          --project=chromium --workers=4
        ;;
      *)
        echo "Unknown level '{{LEVEL}}'. Valid: base | mid | full" && exit 1
        ;;
    esac

# Full local validation: L1 lint → L2 unit → L4 CDK synth → L5 integration smoke
# Starts and tears down the docker stack automatically.
validate:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== L1: Lint (Python + TypeScript) ==="
    just lint
    echo ""
    echo "=== L2: Unit tests ==="
    just test
    echo ""
    echo "=== L4: CDK synth ==="
    just cdk-synth
    echo ""
    echo "=== L5: Integration smoke (docker stack + mid smoke) ==="
    just dev-up
    trap 'just dev-down' EXIT
    just smoke mid
    echo ""
    echo "=== validate PASSED: L1-L5 all green ==="

# Full validation including L6 eval suite (requires AWS creds)
validate-full:
    #!/usr/bin/env bash
    set -euo pipefail
    just validate
    echo ""
    echo "=== L6: Eval suite (AWS eval tests) ==="
    just eval-aws
    echo ""
    echo "=== validate-full PASSED: L1-L6 all green ==="

# ── Composite Workflows ────────────────────────────────────

# CI pipeline: L1 lint + L2 unit + L4 CDK synth + L6 AWS eval
ci: lint test cdk-synth eval-aws

# Ship: lint + CDK synth gate + build + deploy + L5 smoke verify
ship: lint cdk-synth deploy smoke-prod

# ── Internal Helpers (prefixed with _) ──────────────────────

_cdk-bootstrap:
    python3 -c "\
    import boto3, subprocess, sys; \
    account = boto3.client('sts', region_name='us-east-1').get_caller_identity()['Account']; \
    print(f'Bootstrapping CDK for account {account}...'); \
    sys.exit(subprocess.call(['npx', 'cdk', 'bootstrap', f'aws://{account}/us-east-1'], cwd='infrastructure/cdk-eagle'))"

_ecr-login:
    python3 -c "\
    import boto3, subprocess, sys; \
    sts = boto3.client('sts', region_name='us-east-1'); \
    account = sts.get_caller_identity()['Account']; \
    ecr = boto3.client('ecr', region_name='us-east-1'); \
    token = ecr.get_authorization_token()['authorizationData'][0]; \
    registry = f'{account}.dkr.ecr.us-east-1.amazonaws.com'; \
    import base64; \
    user, pwd = base64.b64decode(token['authorizationToken']).decode().split(':'); \
    result = subprocess.run(['docker', 'login', '--username', user, '--password-stdin', registry], input=pwd.encode(), capture_output=True); \
    print(result.stdout.decode().strip()); \
    sys.exit(result.returncode)"

_push-backend:
    python3 -c "\
    import boto3, subprocess, sys; \
    account = boto3.client('sts', region_name='us-east-1').get_caller_identity()['Account']; \
    reg = f'{account}.dkr.ecr.us-east-1.amazonaws.com'; \
    subprocess.check_call(['docker', 'tag', '{{BACKEND_REPO}}:latest', f'{reg}/{{BACKEND_REPO}}:latest']); \
    subprocess.check_call(['docker', 'push', f'{reg}/{{BACKEND_REPO}}:latest'])"

_push-frontend:
    python3 -c "\
    import boto3, subprocess, sys; \
    account = boto3.client('sts', region_name='us-east-1').get_caller_identity()['Account']; \
    reg = f'{account}.dkr.ecr.us-east-1.amazonaws.com'; \
    subprocess.check_call(['docker', 'tag', '{{FRONTEND_REPO}}:latest', f'{reg}/{{FRONTEND_REPO}}:latest']); \
    subprocess.check_call(['docker', 'push', f'{reg}/{{FRONTEND_REPO}}:latest'])"

_ecs-update-all:
    python3 -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='{{CLUSTER}}', service='{{BACKEND_SERVICE}}', forceNewDeployment=True); \
    print('Backend: force new deployment'); \
    ecs.update_service(cluster='{{CLUSTER}}', service='{{FRONTEND_SERVICE}}', forceNewDeployment=True); \
    print('Frontend: force new deployment')"

_ecs-update-backend:
    python3 -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='{{CLUSTER}}', service='{{BACKEND_SERVICE}}', forceNewDeployment=True); \
    print('Backend: force new deployment')"

_ecs-update-frontend:
    python3 -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='{{CLUSTER}}', service='{{FRONTEND_SERVICE}}', forceNewDeployment=True); \
    print('Frontend: force new deployment')"

_ecs-wait-all:
    python3 -c "\
    import boto3; \
    print('Waiting for services to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='{{CLUSTER}}', services=['{{BACKEND_SERVICE}}','{{FRONTEND_SERVICE}}']); \
    print('All services stable.')"

_ecs-wait-backend:
    python3 -c "\
    import boto3; \
    print('Waiting for backend to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='{{CLUSTER}}', services=['{{BACKEND_SERVICE}}']); \
    print('Backend stable.')"

_ecs-wait-frontend:
    python3 -c "\
    import boto3; \
    print('Waiting for frontend to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='{{CLUSTER}}', services=['{{FRONTEND_SERVICE}}']); \
    print('Frontend stable.')"

# ── QA Shortcuts ────────────────────────────────────────────
# All recipes support QA via: EAGLE_ENV=qa just <recipe>
# These aliases save typing for the most common QA operations.
#
# NOTE: In practice, QA deploys go through GitHub Actions (workflow_dispatch
# with environment=qa). These local recipes are available but not the
# primary QA deploy path. Use:
#   gh workflow run deploy.yml --ref <branch> -f environment=qa
# or trigger via GitHub Actions UI > "Deploy EAGLE Platform" > Run workflow > qa.

# Trigger a deploy to dev via GitHub Actions (push-triggered pipeline)
# Usage: just deploy-ci [branch]
deploy-ci BRANCH="main":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Triggering dev deploy via GitHub Actions ==="
    echo "Branch: {{BRANCH}}"
    # Cancel any in-progress deploy runs first
    for run_id in $(gh run list --workflow=deploy.yml --json databaseId,status \
      --jq '.[] | select(.status == "in_progress" or .status == "queued" or .status == "pending") | .databaseId'); do
        echo "Cancelling run $run_id..."
        gh run cancel "$run_id" 2>/dev/null || true
    done
    gh workflow run deploy.yml --ref {{BRANCH}}
    sleep 3
    RUN_ID=$(gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    echo ""
    echo "Deploy triggered: https://github.com/CBIIT/sm_eagle/actions/runs/$RUN_ID"
    echo ""
    echo "Monitor with:"
    echo "  just deploy-watch"
    echo "  just deploy-status"

# Watch the latest deploy run (live streaming output)
deploy-watch:
    #!/usr/bin/env bash
    RUN_ID=$(gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId')
    echo "Watching run $RUN_ID..."
    gh run watch "$RUN_ID"

# Check status of the latest deploy run
deploy-status:
    #!/usr/bin/env bash
    gh run list --workflow=deploy.yml --limit 1 --json databaseId,status,conclusion,headBranch,createdAt \
      --jq '.[0] | "\(.status) \(.conclusion // "—") (branch: \(.headBranch), started: \(.createdAt))"'
    echo ""
    gh run view $(gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId') \
      --json jobs --jq '.jobs[] | "\(if .conclusion == "success" then "✅" elif .conclusion == "failure" then "❌" elif .status == "in_progress" then "🔄" else "⏳" end) \(.name)"'

# Cancel all active deploy runs
deploy-cancel:
    #!/usr/bin/env bash
    CANCELLED=0
    for run_id in $(gh run list --workflow=deploy.yml --json databaseId,status \
      --jq '.[] | select(.status == "in_progress" or .status == "queued" or .status == "pending") | .databaseId'); do
        echo "Cancelling run $run_id..."
        gh run cancel "$run_id" 2>/dev/null || true
        CANCELLED=$((CANCELLED + 1))
    done
    if [ "$CANCELLED" -eq 0 ]; then
        echo "No active runs to cancel."
    else
        echo "Cancelled $CANCELLED run(s)."
    fi

# Deploy to QA via GitHub Actions workflow_dispatch (recommended)
# Usage: just deploy-qa-ci [branch]
deploy-qa-ci BRANCH="main":
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Triggering QA deploy via GitHub Actions ==="
    echo "Branch: {{BRANCH}}"
    gh workflow run deploy.yml --ref {{BRANCH}} -f environment=qa
    echo ""
    echo "Deploy triggered. Watch progress with:"
    echo "  just deploy-watch"

# Deploy to QA environment (local Docker build + ECR push)
deploy-qa:
    EAGLE_ENV=qa just deploy

# Deploy backend to QA only (local Docker build + ECR push)
deploy-backend-qa:
    EAGLE_ENV=qa just deploy-backend

# Deploy frontend to QA only (local Docker build + ECR push)
deploy-frontend-qa:
    EAGLE_ENV=qa just deploy-frontend

# QA service status
status-qa:
    EAGLE_ENV=qa just status

# QA service logs (default: backend)
logs-qa SERVICE="backend":
    EAGLE_ENV=qa just logs {{SERVICE}}

# QA live URLs
urls-qa:
    EAGLE_ENV=qa just urls

# ── Registry & Discoverability ─────────────────────────────
# Entry point for new developers AND new AI agents picking up this codebase.
# Run `just registry` first to see the full command/skill/expert map.

# Categorized print of every operational entry point — recipes, skills, experts, flywheels
registry:
    #!/usr/bin/env bash
    cat <<'EOF'
    =========================================================================
    EAGLE Operational Registry — entry points for humans and agents
    =========================================================================

    QUICKSTART
      Start coding:        just dev-local
      Run tests:           just test  +  just smoke
      Ship to dev:         just deploy-ci main
      Status check:        just status
      Daily rollup:        just langfuse-report-today

    JUST RECIPES (run from terminal — `just <name>`)
      Discovery:           registry  docs  smoke-list  --list
      Dev:                 dev-local  dev-up  dev-backend  dev-frontend  kill-stale
      Test:                test  smoke  smoke-ui  dev-smoke  e2e  eval  eval-aws
      MVP1 ladder:         mvp1  mvp1-quick  mvp1-full  mvp1-visual
      Baseline:            baseline [VERSION]  baseline-list
      Smoke (deployed):    dev-smoke-deployed  qa-smoke-deployed  dev-smoke-triage
      Deploy:              deploy  deploy-backend  deploy-frontend  deploy-ci  ship
      Devbox:              devbox-deploy  devbox-tunnel  devbox-health  devbox-ship
      Diagnostics:         triage-session SESSION_ID  check-cloudwatch  check-langfuse  check-envs
      Analytics:           langfuse-report  langfuse-report-today  langfuse-report-html
      KB ops:              kb-sync  kb-regenerate
      Visual QA:           e2e-judge [URL]
      Onboarding:          handoff [human|agent]
      Health:              on-track  morning-report  status  urls  check-aws  check-sso

    CLAUDE CODE SKILLS (run in Claude Code with /skill-name)
      Workflow:            /plan  /build  /review  /ship  /fix  /test  /simplify
      Discovery:           /on-track  /pid  /check-aws  /check-envs
                           /check-cloudwatch-logs  /check-langfuse-logs
      Diagnostics:         /triage  /kb-regenerate
      Reports:             /scribe  /excalidraw  /langfuse-analytics  /baseline-questions
      Eval:                /mvp1-eval  /e2e-judge
      Knowledge:           /s3-knowledge-base-sync  /obsidian-vault
      Jira:                /jira  /jira-commit-matcher  /jira-story-writer  /jira-sync
      Handoff:             /claude-handoff
      Automation:          /loop  /schedule  /parallel_subagents
      Planning (GSD):      /gsd-add-todo  /gsd-discuss-phase  /gsd-plan-phase  /gsd-execute-phase

    EXPERTS (run /experts:DOMAIN:CMD where CMD = plan|maintenance|question|self-improve)
      Core:                aws  backend  frontend  deployment  git
      Specialized:         cloudwatch  test  eval  claude-sdk  strands  sse  hooks  tac
      Playgrounds:         playground  document-playground

    FLYWHEELS (scheduled GitHub Actions — see .github/workflows/)
      Nightly triage:      cron 0 9  * * *    → docs/development/{ts}-report-triage-*.html
      Eval suite:          cron 0 6  * * *    → server/tests/eval_aws_publisher.py
      Morning report:      cron 0 13 * * 1-5  → Teams Adaptive Card
      Post-deploy smoke:   on workflow_run    → S3 eval-artifacts bucket

    SOURCE-OF-TRUTH FILES (read these first if new)
      Operational guide:   CLAUDE.md
      Quickstart:          README.md
      Plan archive:        .claude/specs/             (70+ dated plans)
      Expert knowledge:    .claude/commands/experts/*/expertise.md
      Skill definitions:   .claude/skills/*/SKILL.md
      Architecture:        docs/architecture/diagrams/
      Past reports:        docs/development/

    Next steps for a new agent:   just handoff agent
    Bundle env for a new human:   just handoff human
    =========================================================================
    EOF

# Print the documentation tree map
docs:
    @echo "EAGLE Documentation Map:"
    @echo "  README.md                        Quickstart, env setup, common commands"
    @echo "  CLAUDE.md                        Operational guide for agents (post-deploy smoke, validation)"
    @echo "  docs/architecture/diagrams/      Excalidraw + Mermaid system diagrams"
    @echo "  docs/development/                Reports, memos, meeting notes (timestamped)"
    @echo "  .claude/specs/                   Implementation plans (70+ dated artifacts)"
    @echo "  .claude/commands/experts/{D}/    Expert mental models (expertise.md) + 4 commands each"
    @echo "  .claude/skills/{S}/SKILL.md      Skill definitions with frontmatter triggers"
    @echo "  eagle-plugin/plugin.json         Active agents + skills manifest"
    @echo "  Justfile                         75+ recipes (run 'just registry' for categorized list)"

# List available post-deploy smoke scenarios (source: server/tests/post_deploy_smoke.py SCENARIOS)
smoke-list:
    @echo "Post-deploy smoke scenarios:"
    @echo "  research_source_transparency   Q4 research-source transparency check (default)"
    @echo "  jefo_q4                        FAR 16.507-6(d)(2) citations / competitor analysis"
    @echo "  sbir_q5                        SBIR protest scenario"
    @echo "  uc21_microscope                UC 2.1 micro-purchase scenario"
    @echo "  kb_inventory_diagnostic        KB retrieval inventory check"
    @echo "  qasp_orphan_unlock             QASP orphan doc-type unlock"
    @echo ""
    @echo "Usage:"
    @echo "  just dev-smoke-deployed <scenario>      # against dev"
    @echo "  just qa-smoke-deployed <scenario>       # against qa (with --auth)"
    @echo "  just dev-smoke-triage                   # run all 5 in sequence"
    @echo ""
    @echo "Source of truth: server/tests/post_deploy_smoke.py SCENARIOS dict"

# ── MVP1 Eval Ladder ───────────────────────────────────────
# Tier 1: unit tests (~30s, no AWS)
# Tier 2: Strands integration (~2 min, needs Bedrock)
# Tier 3: full eval suite (~10 min, needs Bedrock)
# Tier 4: Playwright + visual QA (~5 min, needs deployed env)
# Config: .claude/skills/mvp1-eval/config.json (per-repo paths)

# Tier 1 only — fastest gate, no AWS creds needed
mvp1-quick:
    @echo "=== MVP1 Tier 1: unit tests ==="
    cd server && python -m pytest tests/test_compliance_matrix.py tests/test_chat_kb_flow.py tests/test_canonical_package_document_flow.py tests/test_document_pipeline.py -v

# Tier 1 + 2 — unit tests + Strands integration (default mvp1 invocation)
mvp1: mvp1-quick
    @echo ""
    @echo "=== MVP1 Tier 2: Strands integration ==="
    cd server && python -m pytest tests/test_strands_multi_agent.py tests/test_strands_poc.py tests/test_strands_service_integration.py -v

# Tier 1 + 2 + 3 — adds full Strands eval suite (needs AWS creds)
mvp1-full: mvp1
    @echo ""
    @echo "=== MVP1 Tier 3: full Strands eval suite ==="
    cd server && python3 -u tests/test_strands_eval.py --model haiku

# Tier 1-4 — adds Playwright + e2e-judge visual QA (interactive in Claude Code)
mvp1-visual: mvp1-full
    @echo ""
    @echo "=== MVP1 Tier 4: visual QA via e2e-judge ==="
    @echo "For full Tier 4 visual orchestration, run in Claude Code:"
    @echo "  /mvp1-eval --visual"
    @echo ""
    @echo "Or run e2e-judge directly:  just e2e-judge"

# ── Baseline Questions ─────────────────────────────────────
# Excel-driven 14-question eval against running EAGLE server.
# Captures responses, judges against previous version, generates HTML report.

# Run baseline questions (VERSION = column tag in Use Case List.xlsx, e.g., v6, v7)
baseline VERSION="latest":
    python3 .claude/skills/baseline-questions/scripts/run_baseline.py --version {{VERSION}}

# Show available baseline version columns from the workbook
baseline-list:
    @echo "Baseline versions live in 'Use Case List.xlsx' (repo root)."
    @echo "Each column 'v1', 'v2', 'v3'... captures a baseline run."
    @echo ""
    @echo "Latest column is auto-detected when you run:  just baseline"
    @echo "Or specify explicitly:                         just baseline v6"
    @echo ""
    @echo "Source: .claude/skills/baseline-questions/scripts/run_baseline.py"

# ── Diagnostics (Claude Code Skills) ───────────────────────
# These wrap interactive Claude Code skills. The Justfile recipes print the
# invocation pattern; run the actual diagnostic inside Claude Code.

# Per-session triage: DynamoDB feedback + CloudWatch errors + Langfuse traces
triage-session SESSION_ID:
    @echo "Per-session diagnostic triage — interactive Claude Code skill."
    @echo ""
    @echo "Run in Claude Code:"
    @echo "  /triage {{SESSION_ID}}"
    @echo ""
    @echo "Cross-references DynamoDB feedback, CloudWatch errors, and Langfuse traces."
    @echo "Outputs:  .claude/specs/{ts}-plan-triage-{{SESSION_ID}}-v1.md"
    @echo ""
    @echo "For ALL recent sessions (smoke triage):  just dev-smoke-triage"

# Scan ECS log groups for errors over last N hours
check-cloudwatch HOURS="24" ENV="dev":
    @echo "Open Claude Code and run:"
    @echo "  /check-cloudwatch-logs --hours {{HOURS}} --env {{ENV}}"
    @echo ""
    @echo "Or run hourly in a /loop: /loop 1h /check-cloudwatch-logs"

# Scan Langfuse for errors / latency outliers over WINDOW
check-langfuse WINDOW="24h":
    @echo "Open Claude Code and run:"
    @echo "  /check-langfuse-logs --window {{WINDOW}}"
    @echo ""
    @echo "For a full analytical rollup:  just langfuse-report-today"

# Broad env check — AWS + Langfuse + Cognito + Bedrock + S3 + DynamoDB + Teams + GitHub
check-envs:
    @echo "Comprehensive env credential check (interactive)."
    @echo ""
    @echo "Open Claude Code and run:"
    @echo "  /check-envs"
    @echo ""
    @echo "Or for just AWS resources:  just check-aws"
    @echo "Or for just SSO + Bedrock:  just check-sso"

# ── Knowledge Base Ops ─────────────────────────────────────

# Sync S3 upstream KB → local KB + DynamoDB metadata + compliance matrix
kb-sync:
    @echo "Open Claude Code and run:"
    @echo "  /s3-knowledge-base-sync"

# Rebuild KB index, purge orphan metadata, validate checklists
kb-regenerate:
    @echo "Open Claude Code and run:"
    @echo "  /kb-regenerate"
    @echo ""
    @echo "Combines: orphan-metadata purge + checklist validation + compliance matrix analysis"

# ── Visual QA (e2e-judge) ──────────────────────────────────

# Screenshot-based vision QA — Playwright + Bedrock Sonnet judge
# URL defaults to current dev ALB. Override for QA: URL=$(EAGLE_ENV=qa just urls | grep Frontend | awk '{print $2}')
e2e-judge URL="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "{{URL}}" ]; then
        URL=$(python3 -c "import boto3; c=boto3.client('elbv2',region_name='us-east-1'); lbs=c.describe_load_balancers()['LoadBalancers']; print('http://'+next(lb['DNSName'] for lb in lbs if 'Front' in lb['LoadBalancerName']))")
    else
        URL="{{URL}}"
    fi
    echo "=== e2e-judge against $URL ==="
    echo "For full visual QA orchestration, run in Claude Code:"
    echo "  /e2e-judge"
    echo ""
    echo "Or invoke the orchestrator directly:"
    echo "  cd server && python3 tests/e2e_judge_orchestrator.py --base-url $URL"

# ── Onboarding & Handoff ───────────────────────────────────

# Hand off context — to a human co-worker or to a new AI agent
# MODE = human (default, bundle env via /claude-handoff) | agent (print onboarding checklist)
handoff MODE="human":
    #!/usr/bin/env bash
    case "{{MODE}}" in
      human)
        echo "=== Human handoff — bundle sanitized Claude Code environment ==="
        echo ""
        echo "Open Claude Code and run:"
        echo "  /claude-handoff"
        echo ""
        echo "This bundles:"
        echo "  - ~/.claude config (sanitized)"
        echo "  - Session JSONLs scrubbed via .claude/skills/claude-handoff/scrub-jsonl.py"
        echo "  - Readable HTML transcripts"
        echo "  - Auto-generated setup guide"
        echo ""
        echo "Skill spec: .claude/skills/claude-handoff/SKILL.md"
        ;;
      agent)
        echo "=== Agent onboarding checklist ==="
        echo ""
        echo "New agent picking up this codebase? Follow these steps:"
        echo ""
        echo "  1. Read CLAUDE.md                      (operational guide, validation ladder)"
        echo "  2. Run: just registry                  (full command + skill + expert map)"
        echo "  3. Run: just docs                      (doc tree map)"
        echo "  4. Read .claude/commands/experts/{domain}/expertise.md for relevant domains"
        echo "  5. Skim recent .claude/specs/          (last 5-10 dated entries)"
        echo "  6. Run: just status                    (see deployed state)"
        echo "  7. Run: just check-aws                 (verify AWS access)"
        echo ""
        echo "Validation ladder: ruff check / npx tsc / pytest / playwright / cdk synth"
        echo "Key source files:"
        echo "  server/app/strands_agentic_service.py  (Strands SDK supervisor)"
        echo "  server/app/streaming_routes.py         (SSE endpoint)"
        echo "  eagle-plugin/plugin.json               (active agents + skills)"
        echo "  eagle-plugin/agents/*/agent.md         (agent prompts)"
        ;;
      *)
        echo "Unknown mode '{{MODE}}'. Valid: human | agent"
        exit 1
        ;;
    esac

# ── Project Health ─────────────────────────────────────────

# Scan Jira + git history + branch state against MVP milestones
on-track:
    @echo "Open Claude Code and run:"
    @echo "  /on-track"
    @echo ""
    @echo "Scans Jira + git history + branch state against MVP milestones."

# Generate the daily morning report locally (the same script GH Actions runs at 8am ET)
morning-report:
    python3 scripts/morning_report.py
