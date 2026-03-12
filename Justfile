# ============================================================
# EAGLE Platform — Unified Task Runner
# Usage: just --list
# ============================================================

set dotenv-load := false
set positional-arguments := true

# ── Constants ───────────────────────────────────────────────
REGION          := "us-east-1"
CLUSTER         := "eagle-dev"
BACKEND_SERVICE := "eagle-backend-dev"
FRONTEND_SERVICE := "eagle-frontend-dev"
BACKEND_REPO    := "eagle-backend-dev"
FRONTEND_REPO   := "eagle-frontend-dev"
CDK_DIR         := "infrastructure/cdk-eagle"
COMPOSE_FILE    := "deployment/docker-compose.dev.yml"

# ── First-Time Setup ──────────────────────────────────────

# Full first-time setup: CDK bootstrap → CDK deploy → containers → users → verify
setup: cdk-install _cdk-bootstrap cdk-deploy deploy create-users check-aws
    @echo ""
    @echo "=== Setup complete! ==="
    @echo "Run 'just urls' to see your live application URLs."
    @echo "Test user:  testuser@example.com / EagleTest2024!"
    @echo "Admin user: admin@example.com / EagleAdmin2024!"

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

# Kill processes on a given port (cross-platform: macOS/Linux + Windows/MINGW)
[private]
kill-port PORT:
    #!/usr/bin/env bash
    if [[ "$OSTYPE" == msys* ]] || [[ "$OSTYPE" == mingw* ]] || [[ "$OSTYPE" == cygwin* ]]; then
        # Windows (Git Bash / MINGW) — netstat -ano + taskkill / PowerShell fallback
        for pid in $(netstat -ano 2>/dev/null | grep ":{{PORT}} " | grep LISTENING | awk '{print $5}' | sort -u | grep -v '^0$'); do
            echo "Killing PID $pid on port {{PORT}}"
            taskkill //F //PID "$pid" 2>/dev/null \
                || powershell -Command "Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue" 2>/dev/null \
                || echo "  WARNING: could not kill PID $pid"
        done
    else
        # macOS / Linux — lsof + kill
        pids=$(lsof -ti :{{PORT}} 2>/dev/null || true)
        for pid in $pids; do
            echo "Killing PID $pid on port {{PORT}}"
            kill -9 "$pid" 2>/dev/null || echo "  WARNING: could not kill PID $pid"
        done
    fi

# Kill zombie processes on dev ports (8000, 3000)
kill:
    just kill-port 8000
    just kill-port 3000
    @echo "Dev ports cleared."

# Verify AWS SSO session, auto-login if expired
[private]
ensure-sso PROFILE="eagle":
    #!/usr/bin/env bash
    set -euo pipefail
    if AWS_PROFILE="{{PROFILE}}" aws sts get-caller-identity &>/dev/null; then
        echo "✓ AWS SSO active ({{PROFILE}})"
    else
        echo "⚠ AWS SSO expired — logging in..."
        AWS_PROFILE="{{PROFILE}}" aws sso login --profile "{{PROFILE}}"
        if ! AWS_PROFILE="{{PROFILE}}" aws sts get-caller-identity &>/dev/null; then
            echo "ERROR: SSO login failed. AWS services will not work."
            exit 1
        fi
        echo "✓ AWS SSO active ({{PROFILE}})"
    fi

# Start backend + frontend locally (no docker) — kills zombies, checks SSO
dev-local:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== Clearing ports ==="
    just kill-port 8000
    just kill-port 3000
    just kill-port 3001
    sleep 2
    echo "=== Checking AWS SSO ==="
    just ensure-sso
    # Clear Next.js cache to purge stale env vars
    rm -rf client/.next 2>/dev/null || true
    unset FASTAPI_URL
    export FASTAPI_URL=http://127.0.0.1:8000
    echo "=== Starting backend (port 8000) ==="
    cd server && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app &
    BACKEND_PID=$!
    sleep 5
    echo "=== Starting frontend (port 3000) ==="
    cd client && npm run dev &
    FRONTEND_PID=$!
    echo ""
    echo "Backend PID: $BACKEND_PID (http://localhost:8000)"
    echo "Frontend PID: $FRONTEND_PID (http://localhost:3000)"
    echo "Press Ctrl+C to stop both."
    trap "just kill-port 8000; just kill-port 3000" EXIT
    wait

# Start FastAPI backend only (local) — kills zombies, checks SSO
dev-backend:
    #!/usr/bin/env bash
    set -euo pipefail
    just kill-port 8000
    sleep 1
    just ensure-sso
    cd server && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app

# Start Next.js frontend only (local) — kills zombies on port 3000
dev-frontend:
    #!/usr/bin/env bash
    set -euo pipefail
    just kill-port 3000
    sleep 1
    unset FASTAPI_URL
    cd client && npm run dev

# ── Lint ────────────────────────────────────────────────────

# Run all linters (Python + TypeScript)
lint: lint-py lint-ts

# Lint Python with ruff
lint-py:
    cd server && python3 -m ruff check app/

# Type-check TypeScript
lint-ts:
    cd client && npx tsc --noEmit

# ── Test ────────────────────────────────────────────────────

# Run backend unit tests
test *ARGS:
    cd server && python3 -m pytest tests/ -v {{ARGS}}

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

# Run all test suites and generate a markdown report matrix in test-reports/
# Usage: just test-report           (all suites)
#        just test-report --no-e2e  (skip Playwright — no running stack needed)
test-report *ARGS:
    #!/usr/bin/env bash
    set -uo pipefail
    SKIP_E2E=false
    for arg in {{ARGS}}; do
        [[ "$arg" == "--no-e2e" ]] && SKIP_E2E=true
    done
    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    REPORT="test-reports/${TIMESTAMP}-test-report.md"
    mkdir -p test-reports

    echo "# EAGLE Test Report — ${TIMESTAMP}" > "$REPORT"
    echo "" >> "$REPORT"
    echo "| Suite | Passed | Failed | Errors | Skipped | Status |" >> "$REPORT"
    echo "|-------|--------|--------|--------|---------|--------|" >> "$REPORT"

    TOTAL_PASS=0; TOTAL_FAIL=0; TOTAL_ERR=0; TOTAL_SKIP=0

    # ── L1a: Ruff ──
    echo "Running ruff..."
    RUFF_OUT=$(cd server && python3 -m ruff check app/ 2>&1)
    RUFF_RC=$?
    RUFF_ERRORS=$(echo "$RUFF_OUT" | grep -c "Found [0-9]" || true)
    RUFF_COUNT=$(echo "$RUFF_OUT" | grep -oP 'Found \K[0-9]+' || echo "0")
    if [ "$RUFF_RC" -eq 0 ]; then
        echo "| Ruff (Python lint) | - | 0 | 0 | - | PASS |" >> "$REPORT"
    else
        echo "| Ruff (Python lint) | - | ${RUFF_COUNT} | 0 | - | FAIL |" >> "$REPORT"
    fi

    # ── L1b: TypeScript ──
    echo "Running tsc..."
    TSC_OUT=$(cd client && npx tsc --noEmit 2>&1)
    TSC_RC=$?
    TSC_ERRORS=$(echo "$TSC_OUT" | grep -c "error TS" || true)
    if [ "$TSC_RC" -eq 0 ]; then
        echo "| TypeScript (tsc) | - | 0 | 0 | - | PASS |" >> "$REPORT"
    else
        echo "| TypeScript (tsc) | - | ${TSC_ERRORS} | 0 | - | FAIL |" >> "$REPORT"
    fi

    export AWS_PROFILE="${AWS_PROFILE:-eagle}"

    # ── L2: Pytest ──
    echo "Running pytest..."
    PYTEST_OUT=$(cd server && python3 -m pytest tests/ --ignore=tests/test_strands_eval.py -v --tb=no -q 2>&1)
    PYTEST_RC=$?
    # Parse "X passed, Y failed, Z errors, W skipped" from last line
    PYTEST_SUMMARY=$(echo "$PYTEST_OUT" | grep -E "[0-9]+ (passed|failed|error)" | tail -1)
    PY_PASS=$(echo "$PYTEST_SUMMARY" | grep -oP '[0-9]+(?= passed)' || echo "0")
    PY_FAIL=$(echo "$PYTEST_SUMMARY" | grep -oP '[0-9]+(?= failed)' || echo "0")
    PY_ERR=$(echo "$PYTEST_SUMMARY" | grep -oP '[0-9]+(?= error)' || echo "0")
    PY_SKIP=$(echo "$PYTEST_SUMMARY" | grep -oP '[0-9]+(?= skipped)' || echo "0")
    PY_STATUS="PASS"; [ "$PY_FAIL" -gt 0 ] || [ "$PY_ERR" -gt 0 ] && PY_STATUS="FAIL"
    echo "| Pytest (unit) | ${PY_PASS} | ${PY_FAIL} | ${PY_ERR} | ${PY_SKIP} | ${PY_STATUS} |" >> "$REPORT"
    TOTAL_PASS=$((TOTAL_PASS + PY_PASS))
    TOTAL_FAIL=$((TOTAL_FAIL + PY_FAIL))
    TOTAL_ERR=$((TOTAL_ERR + PY_ERR))
    TOTAL_SKIP=$((TOTAL_SKIP + PY_SKIP))

    # ── L3: Playwright (optional) ──
    if [ "$SKIP_E2E" = false ]; then
        echo "Running Playwright..."
        PW_OUT=$(cd client && BASE_URL=http://localhost:3000 npx playwright test --reporter=list 2>&1)
        PW_RC=$?
        PW_PASS=$(echo "$PW_OUT" | grep -oP '[0-9]+(?= passed)' || echo "0")
        PW_FAIL=$(echo "$PW_OUT" | grep -oP '[0-9]+(?= failed)' || echo "0")
        PW_SKIP=$(echo "$PW_OUT" | grep -oP '[0-9]+(?= skipped)' || echo "0")
        PW_STATUS="PASS"; [ "$PW_FAIL" -gt 0 ] && PW_STATUS="FAIL"
        echo "| Playwright (E2E) | ${PW_PASS} | ${PW_FAIL} | 0 | ${PW_SKIP} | ${PW_STATUS} |" >> "$REPORT"
        TOTAL_PASS=$((TOTAL_PASS + PW_PASS))
        TOTAL_FAIL=$((TOTAL_FAIL + PW_FAIL))
        TOTAL_SKIP=$((TOTAL_SKIP + PW_SKIP))
    else
        echo "| Playwright (E2E) | - | - | - | - | SKIPPED |" >> "$REPORT"
    fi

    # ── L4: CDK synth ──
    echo "Running CDK synth..."
    CDK_OUT=$(cd infrastructure/cdk-eagle && npx cdk synth --quiet 2>&1)
    CDK_RC=$?
    if [ "$CDK_RC" -eq 0 ]; then
        echo "| CDK synth | - | 0 | 0 | - | PASS |" >> "$REPORT"
    else
        echo "| CDK synth | - | 1 | 0 | - | FAIL |" >> "$REPORT"
    fi

    # ── Totals ──
    echo "" >> "$REPORT"
    echo "**Totals:** ${TOTAL_PASS} passed, ${TOTAL_FAIL} failed, ${TOTAL_ERR} errors, ${TOTAL_SKIP} skipped" >> "$REPORT"
    echo "" >> "$REPORT"

    # ── Failure details ──
    if [ "$PY_FAIL" -gt 0 ] || [ "$PY_ERR" -gt 0 ]; then
        echo "## Failed Tests (Pytest)" >> "$REPORT"
        echo '```' >> "$REPORT"
        echo "$PYTEST_OUT" | grep -E "^(FAILED|ERROR) " >> "$REPORT"
        echo '```' >> "$REPORT"
        echo "" >> "$REPORT"
    fi

    if [ "$RUFF_RC" -ne 0 ]; then
        echo "## Ruff Lint Errors" >> "$REPORT"
        echo '```' >> "$REPORT"
        echo "$RUFF_OUT" | tail -5 >> "$REPORT"
        echo '```' >> "$REPORT"
        echo "" >> "$REPORT"
    fi

    echo "---" >> "$REPORT"
    echo "*Generated: $(date -Iseconds) on branch $(git branch --show-current)*" >> "$REPORT"

    echo ""
    echo "=== Report saved: $REPORT ==="
    echo ""
    cat "$REPORT"

# ── Eval Suite ──────────────────────────────────────────────

# Run full eval suite (28 tests) with haiku and publish results
eval:
    cd server && python3 -u tests/test_eagle_sdk_eval.py --model haiku

# Run specific eval tests (e.g., just eval-quick 1,2,3)
eval-quick TESTS:
    cd server && python3 -u tests/test_eagle_sdk_eval.py --model haiku --tests {{TESTS}}

# Run AWS tool eval tests only (16-20)
eval-aws:
    cd server && python3 -u tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20

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
    resp = ecs.describe_services(cluster='eagle-dev', services=['eagle-backend-dev','eagle-frontend-dev']); \
    print('=== EAGLE Platform Status ==='); \
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
    lg = f'/eagle/ecs/{svc}-dev'; \
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
    ecs.update_service(cluster='eagle-dev', service='eagle-backend-dev', forceNewDeployment=True); \
    print('Backend: force new deployment'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-frontend-dev', forceNewDeployment=True); \
    print('Frontend: force new deployment')"

_ecs-update-backend:
    python3 -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-backend-dev', forceNewDeployment=True); \
    print('Backend: force new deployment')"

_ecs-update-frontend:
    python3 -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-frontend-dev', forceNewDeployment=True); \
    print('Frontend: force new deployment')"

_ecs-wait-all:
    python3 -c "\
    import boto3; \
    print('Waiting for services to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='eagle-dev', services=['eagle-backend-dev','eagle-frontend-dev']); \
    print('All services stable.')"

_ecs-wait-backend:
    python3 -c "\
    import boto3; \
    print('Waiting for backend to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='eagle-dev', services=['eagle-backend-dev']); \
    print('Backend stable.')"

_ecs-wait-frontend:
    python3 -c "\
    import boto3; \
    print('Waiting for frontend to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='eagle-dev', services=['eagle-frontend-dev']); \
    print('Frontend stable.')"
