#!/usr/bin/env bash
# Load seed documents into an S3 bucket.
# Usage: ./load-seed-documents.sh [BUCKET_NAME]
# Default bucket: $S3_BUCKET env var or eagle-documents-dev

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ZIP_FILE="$SCRIPT_DIR/s3-seed-documents.zip"
TEMP_DIR="$(mktemp -d)"
BUCKET="${1:-${S3_BUCKET:-eagle-documents-dev}}"

if [ ! -f "$ZIP_FILE" ]; then
  echo "ERROR: $ZIP_FILE not found"
  exit 1
fi

echo "Extracting seed documents..."
unzip -q "$ZIP_FILE" -d "$TEMP_DIR"

echo "Uploading to s3://$BUCKET/ ..."
aws s3 sync "$TEMP_DIR/data/s3-documents/" "s3://$BUCKET/" --size-only

COUNT=$(find "$TEMP_DIR/data/s3-documents" -type f | wc -l)
echo "Done: $COUNT documents uploaded to s3://$BUCKET/"

rm -rf "$TEMP_DIR"
