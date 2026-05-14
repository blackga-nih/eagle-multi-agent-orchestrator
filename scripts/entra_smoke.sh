#!/usr/bin/env bash
# entra_smoke.sh — minimal post-deploy smoke for the Entra OIDC wire.
#
# Verifies, from inside a running frontend ECS task on the deployed cluster:
#   1. Next.js root path /          → returns 200
#   2. Frontend proxy /api/auth/login → returns 3xx with Location header
#      pointing at login.microsoftonline.com (proves /api/auth/* is no longer
#      hitting the localhost:8000 fallback and the backend Entra config is
#      complete).
#   3. Backend /api/health (via FASTAPI_URL inside the task) → 200
#   4. Backend /api/auth/login (via FASTAPI_URL) → 302 to microsoftonline.com
#
# Exits 0 if all four pass, 1 if any fail.
#
# Why this exists instead of the full Playwright smoke: the existing
# server/tests/post_deploy_smoke.py is tightly coupled to the old Cognito
# auth path (cognito_login, Cognito sign-in form Playwright). The Entra
# migration broke those assumptions; this script provides a fast
# auth-free wire check while the full Playwright suite is refactored.
#
# Usage:
#   bash scripts/entra_smoke.sh [dev|qa]    # default: dev
set -e

ENV="${1:-dev}"
CLUSTER="eagle-${ENV}"
SERVICE="eagle-frontend-${ENV}"

echo "=== Entra smoke probe — ${ENV} ==="

# Pick the first RUNNING task on the frontend service
TASK=$(aws --profile eagle --region us-east-1 ecs list-tasks \
    --cluster "$CLUSTER" --service-name "$SERVICE" \
    --desired-status RUNNING --query 'taskArns[0]' --output text)
if [ -z "$TASK" ] || [ "$TASK" = "None" ]; then
    echo "FAIL: no RUNNING task on $SERVICE" >&2
    exit 1
fi
TASK_ID="${TASK##*/}"
echo "Task: $TASK_ID"

# Make sure session-manager-plugin is on PATH (Windows install location).
if [ -d "/c/Program Files/Amazon/SessionManagerPlugin/bin" ]; then
    export PATH="$PATH:/c/Program Files/Amazon/SessionManagerPlugin/bin"
fi

# Probe script runs INSIDE the container. Single shell command so we can
# do it in one execute-command call.
PROBE='set -e
fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "PASS: $*"; }

# 1) Local Next.js root
code=$(curl -sS -o /dev/null -w "%{http_code}" http://localhost:3000/)
[ "$code" = "200" ] && ok "/ → 200" || fail "/ → $code"

# 2) Frontend /api/auth/login proxy → backend → 302 to microsoftonline.com
# Use -I and follow no redirects locally. We just need the Location header.
loc=$(curl -sS -o /dev/null -D - -w "%{http_code}\n" http://localhost:3000/api/auth/login | tr -d "\r")
echo "$loc" | head -20
case "$loc" in
    *login.microsoftonline.com*) ok "/api/auth/login redirects to Entra" ;;
    *localhost*)                 fail "/api/auth/login still hitting localhost — FASTAPI_URL not baked into rewrites" ;;
    *)                            fail "/api/auth/login Location unexpected" ;;
esac

# 3) Backend health via runtime FASTAPI_URL
code=$(curl -sS -o /dev/null -w "%{http_code}" "${FASTAPI_URL}/api/health")
[ "$code" = "200" ] && ok "backend /api/health → 200" || fail "backend /api/health → $code"

# 4) Backend /api/auth/login → 302 microsoftonline
loc=$(curl -sS -o /dev/null -D - -w "" "${FASTAPI_URL}/api/auth/login" | tr -d "\r")
case "$loc" in
    *login.microsoftonline.com*) ok "backend /api/auth/login redirects to Entra" ;;
    *)                            fail "backend /api/auth/login: $(echo "$loc" | head -5)" ;;
esac

echo "=== ALL PROBES PASSED ==="
'

aws --profile eagle --region us-east-1 ecs execute-command \
    --cluster "$CLUSTER" --task "$TASK_ID" \
    --container "eagle-frontend" --interactive \
    --command "sh -c '$PROBE'"
