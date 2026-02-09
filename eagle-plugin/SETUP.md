# EAGLE Plugin Setup Guide

Complete walkthrough for setting up the EAGLE acquisition assistant.

## How The Plugin Works

This is a **Claude Code plugin** — it's just markdown instructions that tell Claude what to do. The plugin itself doesn't execute code. When you use the plugin:

1. You run `claude --plugin-dir ./eagle-plugin`
2. Claude loads the skills/commands as context
3. When you ask about acquisitions, Claude follows the skill instructions
4. Claude uses its `exec` tool to run `aws` CLI commands for S3/DynamoDB

**This means:** Your host machine needs AWS CLI configured with credentials.

---

## Step 1: Prerequisites

### Install AWS CLI

```bash
# macOS
brew install awscli

# Linux (Ubuntu/Debian)
sudo apt-get update && sudo apt-get install awscli

# Windows
# Download from https://aws.amazon.com/cli/

# Verify installation
aws --version
```

### Configure AWS Credentials

```bash
aws configure
# Enter:
#   AWS Access Key ID: your_key
#   AWS Secret Access Key: your_secret
#   Default region: us-east-1
#   Output format: json
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

---

## Step 2: Create AWS Resources

### Option A: Quick Setup Script

```bash
# Run the setup script (creates S3 bucket + DynamoDB table)
./eagle-plugin/scripts/setup-aws.sh my-eagle-docs
```

### Option B: Manual Setup

#### Create S3 Bucket
```bash
# Replace 'my-eagle-docs' with your bucket name
aws s3 mb s3://my-eagle-docs --region us-east-1

# Create folder structure
aws s3api put-object --bucket my-eagle-docs --key eagle/templates/
aws s3api put-object --bucket my-eagle-docs --key eagle/generated/
aws s3api put-object --bucket my-eagle-docs --key eagle/intake-docs/
```

#### Create DynamoDB Table (Optional)
```bash
aws dynamodb create-table \
  --table-name eagle \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

---

## Step 3: Configure the Plugin

### Set Your Bucket Name

Edit `eagle-plugin/config.json` (create if not exists):

```json
{
  "s3_bucket": "my-eagle-docs",
  "s3_prefix": "eagle/",
  "dynamodb_table": "eagle",
  "region": "us-east-1"
}
```

Or set environment variables:
```bash
export EAGLE_S3_BUCKET=my-eagle-docs
export EAGLE_S3_PREFIX=eagle/
export EAGLE_DYNAMODB_TABLE=eagle
```

---

## Step 4: Verify IAM Permissions

Your AWS user/role needs these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::my-eagle-docs",
        "arn:aws:s3:::my-eagle-docs/*"
      ]
    },
    {
      "Sid": "DynamoDBAccess",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:*:table/eagle"
    }
  ]
}
```

Test your permissions:
```bash
# Test S3
aws s3 ls s3://my-eagle-docs/

# Test DynamoDB
aws dynamodb describe-table --table-name eagle
```

---

## Step 5: Install and Run

```bash
# Clone the repo (if you haven't)
git clone https://github.com/gblack686/nci-oa-agent.git
cd nci-oa-agent
git checkout feature/eagle-plugin

# Run Claude Code with the plugin
claude --plugin-dir ./eagle-plugin
```

---

## Step 6: Test the Plugin

Once Claude starts, try these:

```
> /eagle-acquisition:intake
> I need to purchase a CT scanner for $500,000

> /eagle-acquisition:search simplified acquisition threshold

> /eagle-acquisition:document sow
```

---

## Troubleshooting

### "Access Denied" errors
- Check your AWS credentials: `aws sts get-caller-identity`
- Verify IAM permissions include the correct bucket/table names

### "Bucket does not exist"
- Create the bucket: `aws s3 mb s3://your-bucket-name`
- Check region matches: `aws s3 ls --region us-east-1`

### Plugin not loading
- Verify structure: `ls eagle-plugin/.claude-plugin/plugin.json`
- Check Claude Code version: `claude --version` (needs 1.0.33+)

---

## Environment Summary

| Item | Required | Default |
|------|----------|---------|
| AWS CLI | Yes | — |
| AWS credentials | Yes | — |
| S3 Bucket | Yes | — |
| DynamoDB Table | No | `eagle` |
| Anthropic API Key | No* | Handled by Claude Code |

*Claude Code manages its own authentication
