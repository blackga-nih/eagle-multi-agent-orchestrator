#!/usr/bin/env bash
# run-smoke.sh — Run Playwright smoke tests and upload artifacts to S3
#
# Usage:
#   ./scripts/run-smoke.sh                          # all tests, chromium
#   ./scripts/run-smoke.sh --grep "Document Viewer" # filtered
#   UPLOAD=false ./scripts/run-smoke.sh             # skip S3 upload
#
# Env vars:
#   BASE_URL      Target app URL (default: http://localhost:3000)
#   AWS_PROFILE   AWS profile to use (default: eagle)
#   UPLOAD        Set to "false" to skip S3 upload (default: true)
#   PROJECT       Playwright project (default: chromium)

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:3000}"
AWS_PROFILE="${AWS_PROFILE:-eagle}"
UPLOAD="${UPLOAD:-true}"
PROJECT="${PROJECT:-chromium}"
BUCKET="eagle-eval-artifacts-695681773636-dev"
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
S3_PREFIX="qa-artifacts/playwright/${TIMESTAMP}"
RESULTS_DIR="$(dirname "$0")/../test-results"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIENT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== EAGLE Playwright Smoke Test ==="
echo "  URL:     $BASE_URL"
echo "  Project: $PROJECT"
echo "  Results: $RESULTS_DIR"
echo ""

# Run Playwright
cd "$CLIENT_DIR"
BASE_URL="$BASE_URL" npx playwright test \
  --project="$PROJECT" \
  --reporter=line \
  "$@" || PLAYWRIGHT_EXIT=$?

PLAYWRIGHT_EXIT="${PLAYWRIGHT_EXIT:-0}"

echo ""
echo "=== Test run complete (exit $PLAYWRIGHT_EXIT) ==="

if [[ "$UPLOAD" != "false" ]]; then
  echo ""
  echo "=== Uploading artifacts to S3 ==="
  echo "  Bucket: s3://$BUCKET/$S3_PREFIX/"

  aws s3 cp "$RESULTS_DIR" "s3://$BUCKET/$S3_PREFIX/playwright/" \
    --recursive \
    --exclude "*" \
    --include "*.webm" \
    --include "*.png" \
    --include "*.zip" \
    --profile "$AWS_PROFILE" \
    --region us-east-1 \
    2>&1 | tail -5

  echo ""
  echo "  Artifacts: https://s3.console.aws.amazon.com/s3/buckets/$BUCKET?prefix=$S3_PREFIX/"
fi

exit $PLAYWRIGHT_EXIT
