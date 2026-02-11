#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# NCI-EAGLE Lightsail Container Service Deployment Script
# ============================================================
SERVICE_NAME="nci-eagle"
REGION="us-east-1"
POWER="small"
SCALE=1
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  create    Create the Lightsail container service (first time only)
  deploy    Build images, push to Lightsail, and deploy
  status    Show current service state and URL
  logs      Fetch recent container logs
  destroy   Delete the Lightsail service (irreversible!)
EOF
  exit 1
}

# ---- Helpers ----
check_prereqs() {
  command -v aws >/dev/null 2>&1 || { error "AWS CLI not found"; exit 1; }
  command -v docker >/dev/null 2>&1 || { error "Docker not found"; exit 1; }
  docker info >/dev/null 2>&1 || { error "Docker daemon not running"; exit 1; }
}

get_state() {
  aws lightsail get-container-services \
    --service-name "$SERVICE_NAME" \
    --query 'containerServices[0].state' \
    --output text --region "$REGION" 2>/dev/null || echo "NOT_FOUND"
}

get_url() {
  aws lightsail get-container-services \
    --service-name "$SERVICE_NAME" \
    --query 'containerServices[0].url' \
    --output text --region "$REGION" 2>/dev/null || echo ""
}

wait_for_ready() {
  info "Waiting for service to be READY..."
  for i in $(seq 1 30); do
    STATE=$(get_state)
    if [ "$STATE" = "READY" ] || [ "$STATE" = "RUNNING" ]; then
      info "Service is $STATE"
      return 0
    fi
    echo -n "."
    sleep 10
  done
  error "Timed out waiting for service (last state: $STATE)"
  exit 1
}

# ---- Commands ----
cmd_create() {
  info "Creating Lightsail container service: $SERVICE_NAME"
  aws lightsail create-container-service \
    --service-name "$SERVICE_NAME" \
    --power "$POWER" \
    --scale "$SCALE" \
    --region "$REGION"
  wait_for_ready
  info "Service created! URL: $(get_url)"
}

cmd_deploy() {
  check_prereqs

  # Load secrets from .env.lightsail if present
  ENV_FILE="$REPO_ROOT/.env.lightsail"
  if [ -f "$ENV_FILE" ]; then
    info "Loading secrets from .env.lightsail"
    set -a; source "$ENV_FILE"; set +a
  else
    warn "No .env.lightsail found — using environment variables"
  fi

  # Validate required env vars
  : "${CONTAINER_AWS_ACCESS_KEY_ID:?Set CONTAINER_AWS_ACCESS_KEY_ID in .env.lightsail}"
  : "${CONTAINER_AWS_SECRET_ACCESS_KEY:?Set CONTAINER_AWS_SECRET_ACCESS_KEY in .env.lightsail}"

  # Step 1: Build
  info "Building frontend image..."
  docker build -t nci-eagle-frontend:latest "$REPO_ROOT/client"

  info "Building backend image..."
  docker build -t nci-eagle-backend:latest -f "$REPO_ROOT/Dockerfile.backend" "$REPO_ROOT"

  # Step 2: Push
  info "Pushing backend image..."
  BACKEND_REF=$(aws lightsail push-container-image \
    --service-name "$SERVICE_NAME" \
    --label backend \
    --image nci-eagle-backend:latest \
    --region "$REGION" 2>&1 | grep -oP ':\S+\.\d+' | tail -1)
  info "Backend image: $BACKEND_REF"

  info "Pushing frontend image..."
  FRONTEND_REF=$(aws lightsail push-container-image \
    --service-name "$SERVICE_NAME" \
    --label frontend \
    --image nci-eagle-frontend:latest \
    --region "$REGION" 2>&1 | grep -oP ':\S+\.\d+' | tail -1)
  info "Frontend image: $FRONTEND_REF"

  # Step 3: Generate deployment JSON
  DEPLOY_JSON=$(cat <<EOJSON
{
  "serviceName": "$SERVICE_NAME",
  "containers": {
    "backend": {
      "image": "$BACKEND_REF",
      "command": [],
      "environment": {
        "USE_BEDROCK": "true",
        "AWS_ACCESS_KEY_ID": "$CONTAINER_AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY": "$CONTAINER_AWS_SECRET_ACCESS_KEY",
        "AWS_REGION": "us-east-1",
        "COGNITO_USER_POOL_ID": "us-east-1_AZuPs6Ifs",
        "COGNITO_CLIENT_ID": "4cv12gt73qi3nct25vl6mno72a",
        "COGNITO_REGION": "us-east-1",
        "REQUIRE_AUTH": "true",
        "DEV_MODE": "false",
        "USE_PERSISTENT_SESSIONS": "true"
      },
      "ports": {
        "8000": "HTTP"
      }
    },
    "frontend": {
      "image": "$FRONTEND_REF",
      "command": [],
      "environment": {
        "FASTAPI_URL": "http://localhost:8000",
        "NEXT_PUBLIC_COGNITO_USER_POOL_ID": "us-east-1_AZuPs6Ifs",
        "NEXT_PUBLIC_COGNITO_CLIENT_ID": "4cv12gt73qi3nct25vl6mno72a",
        "NEXT_PUBLIC_COGNITO_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "$CONTAINER_AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY": "$CONTAINER_AWS_SECRET_ACCESS_KEY",
        "AWS_REGION": "us-east-1",
        "NODE_ENV": "production"
      },
      "ports": {
        "3000": "HTTP"
      }
    }
  },
  "publicEndpoint": {
    "containerName": "frontend",
    "containerPort": 3000,
    "healthCheck": {
      "healthyThreshold": 2,
      "unhealthyThreshold": 5,
      "timeoutSeconds": 5,
      "intervalSeconds": 10,
      "path": "/",
      "successCodes": "200-399"
    }
  }
}
EOJSON
)

  # Step 4: Deploy
  info "Deploying to Lightsail..."
  echo "$DEPLOY_JSON" | aws lightsail create-container-service-deployment \
    --service-name "$SERVICE_NAME" \
    --cli-input-json file:///dev/stdin \
    --region "$REGION"

  info "Deployment started! Monitoring..."
  for i in $(seq 1 40); do
    DEP_STATE=$(aws lightsail get-container-services \
      --service-name "$SERVICE_NAME" \
      --query 'containerServices[0].currentDeployment.state' \
      --output text --region "$REGION" 2>/dev/null || echo "PENDING")
    SVC_STATE=$(get_state)
    if [ "$DEP_STATE" = "ACTIVE" ]; then
      info "Deployment ACTIVE!"
      info "URL: $(get_url)"
      return 0
    fi
    echo -ne "\r  Service: $SVC_STATE | Deployment: $DEP_STATE (${i}/40)"
    sleep 15
  done
  warn "Deployment still in progress. Check with: $0 status"
}

cmd_status() {
  STATE=$(get_state)
  URL=$(get_url)
  DEP_STATE=$(aws lightsail get-container-services \
    --service-name "$SERVICE_NAME" \
    --query 'containerServices[0].currentDeployment.state' \
    --output text --region "$REGION" 2>/dev/null || echo "NONE")
  info "Service: $SERVICE_NAME"
  info "State: $STATE"
  info "Deployment: $DEP_STATE"
  info "URL: $URL"
}

cmd_logs() {
  CONTAINER="${2:-frontend}"
  info "Fetching logs for container: $CONTAINER"
  aws lightsail get-container-log \
    --service-name "$SERVICE_NAME" \
    --container-name "$CONTAINER" \
    --region "$REGION" \
    --query 'logEvents[*].message' \
    --output text 2>&1 | tail -50
}

cmd_destroy() {
  warn "This will delete the $SERVICE_NAME service and all deployments!"
  read -p "Type 'yes' to confirm: " CONFIRM
  if [ "$CONFIRM" = "yes" ]; then
    aws lightsail delete-container-service \
      --service-name "$SERVICE_NAME" \
      --region "$REGION"
    info "Service deleted."
  else
    info "Cancelled."
  fi
}

# ---- Main ----
[ $# -lt 1 ] && usage
case "$1" in
  create)  cmd_create ;;
  deploy)  cmd_deploy ;;
  status)  cmd_status ;;
  logs)    cmd_logs "$@" ;;
  destroy) cmd_destroy ;;
  *)       usage ;;
esac
