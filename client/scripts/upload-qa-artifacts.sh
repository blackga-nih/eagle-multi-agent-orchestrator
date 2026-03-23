#!/usr/bin/env bash
# upload-qa-artifacts.sh — Upload QA screenshots/videos to S3
#
# Usage:
#   ./scripts/upload-qa-artifacts.sh <local-dir> [label]
#
# Examples:
#   ./scripts/upload-qa-artifacts.sh ./screenshots/bowser-qa "acquisition-package"
#   ./scripts/upload-qa-artifacts.sh /tmp/acq-pkg-screenshots "acq-pkg-run5"
#
# Env vars:
#   AWS_PROFILE   AWS profile (default: eagle)

set -euo pipefail

LOCAL_DIR="${1:-}"
LABEL="${2:-manual}"
AWS_PROFILE="${AWS_PROFILE:-eagle}"
BUCKET="eagle-eval-artifacts-695681773636-dev"
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
S3_PREFIX="qa-artifacts/browser/${TIMESTAMP}-${LABEL}"

if [[ -z "$LOCAL_DIR" || ! -d "$LOCAL_DIR" ]]; then
  echo "Usage: $0 <local-dir> [label]"
  echo "  <local-dir> must be an existing directory"
  exit 1
fi

echo "=== Uploading QA artifacts ==="
echo "  From:   $LOCAL_DIR"
echo "  To:     s3://$BUCKET/$S3_PREFIX/"
echo "  Profile: $AWS_PROFILE"
echo ""

aws s3 cp "$LOCAL_DIR" "s3://$BUCKET/$S3_PREFIX/" \
  --recursive \
  --exclude "*" \
  --include "*.png" \
  --include "*.webm" \
  --include "*.mp4" \
  --include "*.zip" \
  --profile "$AWS_PROFILE" \
  --region us-east-1

echo ""
echo "Done. View at:"
echo "  https://s3.console.aws.amazon.com/s3/buckets/$BUCKET?prefix=$S3_PREFIX/"
