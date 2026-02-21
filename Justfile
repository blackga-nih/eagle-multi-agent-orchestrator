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

# Full first-time setup: S3 bucket → CDK bootstrap → CDK deploy → containers → users → verify
setup: _create-bucket cdk-install _cdk-bootstrap cdk-deploy deploy create-users check-aws
    @echo ""
    @echo "=== Setup complete! ==="
    @echo "Run 'just urls' to see your live application URLs."
    @echo "Test user:  testuser@example.com / EagleTest2024!"
    @echo "Admin user: admin@example.com / EagleAdmin2024!"

# Create test + admin Cognito users with required tenant attributes
create-users:
    python scripts/create_users.py

# ── Development ─────────────────────────────────────────────

# Start backend + frontend via docker compose (foreground, with logs)
dev:
    docker compose -f {{COMPOSE_FILE}} up --build

# Start stack detached and wait for backend health (ready for smoke tests)
dev-up:
    docker compose -f {{COMPOSE_FILE}} up --build --detach
    python scripts/wait_for_backend.py

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
          --project=chromium
        ;;
      mid)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts documents.spec.ts workflows.spec.ts \
          --project=chromium
        ;;
      full)
        cd client && BASE_URL=http://localhost:3000 npx playwright test \
          navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts documents.spec.ts workflows.spec.ts chat.spec.ts \
          --project=chromium
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

# Start FastAPI backend only (local)
dev-backend:
    cd server && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Start Next.js frontend only (local)
dev-frontend:
    cd client && npm run dev

# ── Lint ────────────────────────────────────────────────────

# Run all linters (Python + TypeScript)
lint: lint-py lint-ts

# Lint Python with ruff
lint-py:
    cd server && python -m ruff check app/

# Type-check TypeScript
lint-ts:
    cd client && npx tsc --noEmit

# ── Test ────────────────────────────────────────────────────

# Run backend unit tests
test *ARGS:
    cd server && python -m pytest tests/ -v {{ARGS}}

# Run Playwright E2E tests against Fargate (headless)
test-e2e *ARGS:
    python -c "import boto3; c=boto3.client('elbv2',region_name='us-east-1'); dns=[lb['DNSName'] for lb in c.describe_load_balancers()['LoadBalancers'] if 'Front' in lb['LoadBalancerName']]; print(f'Testing against: http://{dns[0]}')" && cd client && npx playwright test {{ARGS}}

# Run Playwright E2E tests against Fargate with a visible browser window
test-e2e-ui *ARGS:
    python -c "import boto3; c=boto3.client('elbv2',region_name='us-east-1'); dns=[lb['DNSName'] for lb in c.describe_load_balancers()['LoadBalancers'] if 'Front' in lb['LoadBalancerName']]; print(f'Testing against: http://{dns[0]}')" && cd client && npx playwright test {{ARGS}} --headed

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

# Run full eval suite (28 tests) with haiku and publish results
eval:
    cd server && python -u tests/test_eagle_sdk_eval.py --model haiku

# Run specific eval tests (e.g., just eval-quick 1,2,3)
eval-quick TESTS:
    cd server && python -u tests/test_eagle_sdk_eval.py --model haiku --tests {{TESTS}}

# Run AWS tool eval tests only (16-20)
eval-aws:
    cd server && python -u tests/test_eagle_sdk_eval.py --model haiku --tests 16,17,18,19,20

# ── Docker Build ────────────────────────────────────────────

# Build all containers locally
build:
    docker compose -f {{COMPOSE_FILE}} build

# Build backend image
build-backend:
    docker build -f deployment/docker/Dockerfile.backend -t {{BACKEND_REPO}}:latest .

# Build frontend image (fetches Cognito config from CDK outputs)
build-frontend:
    python -c "\
    import boto3, subprocess, sys; \
    cf = boto3.client('cloudformation', region_name='us-east-1'); \
    stacks = cf.describe_stacks(StackName='EagleCoreStack')['Stacks'][0]['Outputs']; \
    outputs = {o['OutputKey']: o['OutputValue'] for o in stacks}; \
    pool_id = [v for k,v in outputs.items() if 'UserPoolId' in k and 'Client' not in k][0]; \
    client_id = [v for k,v in outputs.items() if 'ClientId' in k][0]; \
    print(f'Building frontend: POOL_ID={pool_id} CLIENT_ID={client_id}'); \
    sys.exit(subprocess.call([ \
      'docker', 'build', '-f', 'deployment/docker/Dockerfile.frontend', \
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

# ── Operations ──────────────────────────────────────────────

# Show ECS service health and running task counts
status:
    python -c "\
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
    python -c "\
    import boto3, sys, time; \
    svc = '{{SERVICE}}'; \
    lg = f'/ecs/eagle-{svc}-dev'; \
    client = boto3.client('logs', region_name='us-east-1'); \
    import datetime; \
    start = int((datetime.datetime.now() - datetime.timedelta(minutes=30)).timestamp() * 1000); \
    resp = client.filter_log_events(logGroupName=lg, startTime=start, limit=100, interleaved=True); \
    [print(e.get('message','').strip()) for e in resp.get('events',[])]"

# Print live URLs from ALBs
urls:
    python -c "\
    import boto3; \
    elb = boto3.client('elbv2', region_name='us-east-1'); \
    lbs = elb.describe_load_balancers()['LoadBalancers']; \
    front = next((lb['DNSName'] for lb in lbs if 'Front' in lb['LoadBalancerName']), 'unknown'); \
    back = next((lb['DNSName'] for lb in lbs if 'Backe' in lb['LoadBalancerName']), 'unknown'); \
    print(f'Frontend: http://{front}'); \
    print(f'Backend:  http://{back}')"

# Verify AWS credentials and service connectivity (all EAGLE resources)
check-aws:
    python scripts/check_aws.py

# ── Composite Workflows ────────────────────────────────────

# CI pipeline: lint + test + AWS eval tests
ci: lint test eval-aws

# Ship: lint + build + deploy + verify
ship: lint deploy

# ── Internal Helpers (prefixed with _) ──────────────────────

_create-bucket:
    python -c "\
    import boto3; \
    s3 = boto3.client('s3', region_name='us-east-1'); \
    try: \
        s3.head_bucket(Bucket='nci-documents'); \
        print('S3 bucket nci-documents already exists.'); \
    except s3.exceptions.ClientError: \
        s3.create_bucket(Bucket='nci-documents'); \
        print('Created S3 bucket: nci-documents')"

_cdk-bootstrap:
    python -c "\
    import boto3, subprocess, sys; \
    account = boto3.client('sts', region_name='us-east-1').get_caller_identity()['Account']; \
    print(f'Bootstrapping CDK for account {account}...'); \
    sys.exit(subprocess.call(['npx', 'cdk', 'bootstrap', f'aws://{account}/us-east-1'], cwd='infrastructure/cdk-eagle'))"

_ecr-login:
    python -c "\
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
    python -c "\
    import boto3, subprocess, sys; \
    account = boto3.client('sts', region_name='us-east-1').get_caller_identity()['Account']; \
    reg = f'{account}.dkr.ecr.us-east-1.amazonaws.com'; \
    subprocess.check_call(['docker', 'tag', '{{BACKEND_REPO}}:latest', f'{reg}/{{BACKEND_REPO}}:latest']); \
    subprocess.check_call(['docker', 'push', f'{reg}/{{BACKEND_REPO}}:latest'])"

_push-frontend:
    python -c "\
    import boto3, subprocess, sys; \
    account = boto3.client('sts', region_name='us-east-1').get_caller_identity()['Account']; \
    reg = f'{account}.dkr.ecr.us-east-1.amazonaws.com'; \
    subprocess.check_call(['docker', 'tag', '{{FRONTEND_REPO}}:latest', f'{reg}/{{FRONTEND_REPO}}:latest']); \
    subprocess.check_call(['docker', 'push', f'{reg}/{{FRONTEND_REPO}}:latest'])"

_ecs-update-all:
    python -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-backend-dev', forceNewDeployment=True); \
    print('Backend: force new deployment'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-frontend-dev', forceNewDeployment=True); \
    print('Frontend: force new deployment')"

_ecs-update-backend:
    python -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-backend-dev', forceNewDeployment=True); \
    print('Backend: force new deployment')"

_ecs-update-frontend:
    python -c "\
    import boto3; \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    ecs.update_service(cluster='eagle-dev', service='eagle-frontend-dev', forceNewDeployment=True); \
    print('Frontend: force new deployment')"

_ecs-wait-all:
    python -c "\
    import boto3; \
    print('Waiting for services to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='eagle-dev', services=['eagle-backend-dev','eagle-frontend-dev']); \
    print('All services stable.')"

_ecs-wait-backend:
    python -c "\
    import boto3; \
    print('Waiting for backend to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='eagle-dev', services=['eagle-backend-dev']); \
    print('Backend stable.')"

_ecs-wait-frontend:
    python -c "\
    import boto3; \
    print('Waiting for frontend to stabilize...'); \
    ecs = boto3.client('ecs', region_name='us-east-1'); \
    waiter = ecs.get_waiter('services_stable'); \
    waiter.wait(cluster='eagle-dev', services=['eagle-frontend-dev']); \
    print('Frontend stable.')"
