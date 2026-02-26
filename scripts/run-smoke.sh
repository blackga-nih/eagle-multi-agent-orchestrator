#!/bin/bash
# Eagle full-stack smoke test runner
# Runs on eagle-runner-dev (i-0390c06d166d18926) via SSM.
# Starts docker compose, runs all Playwright tests, uploads artifacts to S3,
# and writes a run metadata record to DynamoDB.
set -e
cd /root/eagle

echo "=== Fetching instance credentials ==="
TOKEN=$(curl -sf -X PUT http://169.254.169.254/latest/api/token \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
ROLE=$(curl -sf http://169.254.169.254/latest/meta-data/iam/security-credentials/ \
  -H "X-aws-ec2-metadata-token: $TOKEN")
CREDS=$(curl -sf "http://169.254.169.254/latest/meta-data/iam/security-credentials/$ROLE" \
  -H "X-aws-ec2-metadata-token: $TOKEN")
export AWS_ACCESS_KEY_ID=$(echo "$CREDS"    | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKeyId'])")
export AWS_SECRET_ACCESS_KEY=$(echo "$CREDS" | python3 -c "import sys,json; print(json.load(sys.stdin)['SecretAccessKey'])")
export AWS_SESSION_TOKEN=$(echo "$CREDS"    | python3 -c "import sys,json; print(json.load(sys.stdin)['Token'])")
echo "Credentials loaded: ${AWS_ACCESS_KEY_ID:0:8}..."

echo "=== Writing .env ==="
cat > /root/eagle/.env << 'ENVEOF'
COGNITO_USER_POOL_ID=us-east-1_GqZzjtSu9
COGNITO_CLIENT_ID=50r0sfnqbqq9t96v50knal0esa
EAGLE_SESSIONS_TABLE=eagle
USE_BEDROCK=true
S3_BUCKET=eagle-documents-695681773636-dev
S3_PREFIX=eagle/
JWT_SECRET=dev-local-secret
DEV_MODE=true
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
DEBUG=true
USE_PERSISTENT_SESSIONS=true
ENVEOF
# Append live IMDS credentials so Docker containers can call AWS APIs
echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}" >> /root/eagle/.env
echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}" >> /root/eagle/.env
echo "AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}" >> /root/eagle/.env

echo "=== Pulling latest config from S3 ==="
aws s3 cp s3://eagle-documents-695681773636-dev/scripts/global-setup.ts \
  /root/eagle/client/tests/global-setup.ts --region us-east-1
aws s3 cp s3://eagle-documents-695681773636-dev/scripts/playwright.config.ts \
  /root/eagle/client/playwright.config.ts --region us-east-1
aws s3 cp s3://eagle-documents-695681773636-dev/scripts/chat.spec.ts \
  /root/eagle/client/tests/chat.spec.ts --region us-east-1
aws s3 cp s3://eagle-documents-695681773636-dev/scripts/Dockerfile.backend \
  /root/eagle/deployment/docker/Dockerfile.backend --region us-east-1
aws s3 cp s3://eagle-documents-695681773636-dev/scripts/sdk_agentic_service.py \
  /root/eagle/server/app/sdk_agentic_service.py --region us-east-1

# Patch docker-compose to remove lines that break credential resolution in headless EC2 context.
# AWS_PROFILE="" (empty string) causes boto3 to look for a named profile "" instead of
# using the AWS_ACCESS_KEY_ID/SECRET/TOKEN env vars that are already in the container.
python3 -c "
import re
path = 'deployment/docker-compose.dev.yml'
with open(path) as f:
    content = f.read()
# Remove AWS_PROFILE and AWS_SDK_LOAD_CONFIG — both interfere with env-var credential chain
content = re.sub(r'[ \t]*-[ \t]*AWS_PROFILE=.*\n', '', content)
content = re.sub(r'[ \t]*-[ \t]*AWS_SDK_LOAD_CONFIG=.*\n', '', content)
# Remove .aws volume mount — no valid .aws dir on headless EC2 (HOME is unset in SSM)
content = re.sub(r'[ \t]*-[ \t]*\\\$\{(?:AWS_CONFIG_DIR|HOME)[^}]*\}[^\n]*\.aws[^\n]*\n', '', content)
with open(path, 'w') as f:
    f.write(content)
print('Patched docker-compose.dev.yml (removed AWS_PROFILE, AWS_SDK_LOAD_CONFIG, .aws mount)')
"

echo "=== Starting docker compose ==="
docker compose -f deployment/docker-compose.dev.yml down --remove-orphans 2>&1 | tail -3 || true
docker compose -f deployment/docker-compose.dev.yml up --build --detach 2>&1

echo "=== Waiting for backend ==="
python3 scripts/wait_for_backend.py

# ── Run ID and paths ────────────────────────────────────────────────────────
RUN_ID=$(date -u +%Y-%m-%dT%H-%M-%SZ)
S3_BUCKET=eagle-documents-695681773636-dev
S3_RESULTS_PREFIX="smoke-results/${RUN_ID}"
DYNAMO_TABLE=eagle
PW_OUTPUT="/tmp/pw-${RUN_ID}.txt"

echo "=== Running full smoke tests (run: ${RUN_ID}) ==="
cd /root/eagle/client
rm -f tests/.auth/user.json
BASE_URL=http://localhost:3000 npx playwright test \
  navigation.spec.ts intake.spec.ts admin-dashboard.spec.ts \
  documents.spec.ts workflows.spec.ts chat.spec.ts \
  --project=chromium --workers=2 2>&1 | tee "${PW_OUTPUT}"
PW_EXIT=${PIPESTATUS[0]}
echo "pw-exit:$PW_EXIT"

# ── Upload artifacts to S3 ──────────────────────────────────────────────────
echo "=== Uploading artifacts to S3 ==="
if [ -d test-results ]; then
  aws s3 sync test-results/ \
    "s3://${S3_BUCKET}/${S3_RESULTS_PREFIX}/test-results/" \
    --region us-east-1 \
    --exclude "*" \
    --include "*.webm" \
    --include "*.zip" \
    --include "*.png" \
    --quiet \
  && echo "Artifacts: s3://${S3_BUCKET}/${S3_RESULTS_PREFIX}/test-results/" \
  || echo "WARN: S3 artifact upload failed (non-fatal)"
fi

# ── Parse results ───────────────────────────────────────────────────────────
echo "=== Parsing results ==="
RESULTS=$(python3 -c "
import re, sys
with open('${PW_OUTPUT}') as f:
    content = f.read()
passed = 0; failed = 0; duration = '0s'
for line in reversed(content.strip().split('\n')):
    pm = re.search(r'(\d+) passed', line)
    fm = re.search(r'(\d+) failed', line)
    dm = re.search(r'\((\d+\.?\d*s)\)', line)
    if pm: passed = int(pm.group(1))
    if fm: failed = int(fm.group(1))
    if dm: duration = dm.group(1)
    if pm or fm: break
print(f'{passed},{failed},{duration}')
")
PASSED=$(echo "$RESULTS" | cut -d, -f1)
FAILED=$(echo "$RESULTS" | cut -d, -f2)
DURATION=$(echo "$RESULTS" | cut -d, -f3)
STATUS=$([ "$PW_EXIT" -eq 0 ] && echo "passed" || echo "failed")
echo "Results: ${PASSED} passed, ${FAILED} failed in ${DURATION} — status=${STATUS}"

# ── Write DynamoDB record ───────────────────────────────────────────────────
# Uses AWS CLI (not boto3 — not installed on EC2 system Python).
# Python is used only to build the JSON item; aws dynamodb put-item does the write.
echo "=== Writing run record to DynamoDB ==="
TTL=$(( $(date +%s) + 7776000 ))  # 90-day retention
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

ITEM=$(RUN_ID="$RUN_ID" STATUS="$STATUS" PASSED="${PASSED:-0}" FAILED="${FAILED:-0}" \
  DURATION="${DURATION:-0s}" PW_EXIT="$PW_EXIT" S3_BUCKET="$S3_BUCKET" \
  S3_RESULTS_PREFIX="$S3_RESULTS_PREFIX" TTL="$TTL" TIMESTAMP="$TIMESTAMP" \
  python3 -c "
import json, os
e = os.environ
run_id = e['RUN_ID']
item = {
    'PK':        {'S': f'SMOKE_RUN#{run_id}'},
    'SK':        {'S': 'METADATA'},
    'run_id':    {'S': run_id},
    'timestamp': {'S': e['TIMESTAMP']},
    'status':    {'S': e['STATUS']},
    'passed':    {'N': e['PASSED'] or '0'},
    'failed':    {'N': e['FAILED'] or '0'},
    'duration':  {'S': e['DURATION']},
    'pw_exit':   {'N': e['PW_EXIT']},
    's3_prefix': {'S': 's3://' + e['S3_BUCKET'] + '/' + e['S3_RESULTS_PREFIX'] + '/test-results/'},
    'ttl':       {'N': e['TTL']},
}
print(json.dumps(item))
")

(
  aws dynamodb put-item \
    --table-name "$DYNAMO_TABLE" \
    --item "$ITEM" \
    --region us-east-1 \
  && echo "DynamoDB record written: SMOKE_RUN#${RUN_ID}"
) || echo "WARN: DynamoDB write failed (non-fatal — check EC2 role has dynamodb:PutItem on eagle table)"

exit $PW_EXIT
