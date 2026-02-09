#!/bin/bash
# EAGLE Plugin AWS Setup Script
# Usage: ./setup-aws.sh <bucket-name> [region]

set -e

BUCKET_NAME=${1:-eagle-documents}
REGION=${2:-us-east-1}
TABLE_NAME="eagle"

echo "🦅 EAGLE AWS Setup"
echo "=================="
echo "Bucket: $BUCKET_NAME"
echo "Region: $REGION"
echo "Table:  $TABLE_NAME"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Install it first:"
    echo "   https://aws.amazon.com/cli/"
    exit 1
fi

# Check credentials
echo "Checking AWS credentials..."
aws sts get-caller-identity > /dev/null 2>&1 || {
    echo "❌ AWS credentials not configured. Run: aws configure"
    exit 1
}
echo "✅ AWS credentials OK"

# Create S3 bucket
echo ""
echo "Creating S3 bucket..."
if aws s3 ls "s3://$BUCKET_NAME" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3 mb "s3://$BUCKET_NAME" --region "$REGION"
    echo "✅ Created bucket: $BUCKET_NAME"
else
    echo "ℹ️  Bucket already exists: $BUCKET_NAME"
fi

# Create folder structure
echo "Creating folder structure..."
aws s3api put-object --bucket "$BUCKET_NAME" --key "eagle/templates/" > /dev/null
aws s3api put-object --bucket "$BUCKET_NAME" --key "eagle/generated/" > /dev/null
aws s3api put-object --bucket "$BUCKET_NAME" --key "eagle/intake-docs/" > /dev/null
echo "✅ Folder structure created"

# Create DynamoDB table
echo ""
echo "Creating DynamoDB table..."
if aws dynamodb describe-table --table-name "$TABLE_NAME" --region "$REGION" 2>&1 | grep -q 'ResourceNotFoundException'; then
    aws dynamodb create-table \
        --table-name "$TABLE_NAME" \
        --attribute-definitions \
            AttributeName=PK,AttributeType=S \
            AttributeName=SK,AttributeType=S \
        --key-schema \
            AttributeName=PK,KeyType=HASH \
            AttributeName=SK,KeyType=RANGE \
        --billing-mode PAY_PER_REQUEST \
        --region "$REGION" > /dev/null
    echo "✅ Created table: $TABLE_NAME"
else
    echo "ℹ️  Table already exists: $TABLE_NAME"
fi

# Create config.json
echo ""
echo "Creating config.json..."
cat > "$(dirname "$0")/../config.json" << EOFCONFIG
{
  "s3_bucket": "$BUCKET_NAME",
  "s3_prefix": "eagle/",
  "dynamodb_table": "$TABLE_NAME",
  "region": "$REGION"
}
EOFCONFIG
echo "✅ Config saved to config.json"

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Run Claude Code with the plugin:"
echo "     claude --plugin-dir ./eagle-plugin"
echo ""
echo "  2. Try a command:"
echo "     /eagle-acquisition:intake"
