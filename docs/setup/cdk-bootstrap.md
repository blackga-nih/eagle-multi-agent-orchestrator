# Checklist C: First-Time Cloud Setup (CDK Bootstrap)

Only needed when deploying to a **new AWS account** for the first time.

## C0 — Prerequisites

- [ ] **AWS CLI** with admin credentials (or PowerUser + boundary for NCI accounts)
- [ ] **Node.js 20+**, **`just`**

## C1 — Configure Account-Specific Names

S3 bucket names are globally unique. Update `infrastructure/cdk-eagle/config/environments.ts`:

```typescript
documentBucketName: 'eagle-documents-{account-id}-dev',  // must be globally unique
githubOwner: 'your-github-org',
githubRepo:  'your-repo-name',
```

## C2 — Enable Bedrock Model Access *(manual, one-time)*

1. Open **AWS Console → Amazon Bedrock → Model access**
2. Enable **Anthropic Claude Sonnet 4.6** and **Claude Haiku 4.5**
3. Wait for **"Access granted"**

## C3 — Bootstrap CDK and Deploy All Stacks

```bash
just cdk-install   # npm ci in infrastructure/cdk-eagle/

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
npx cdk bootstrap aws://$ACCOUNT_ID/us-east-1

just cdk-deploy    # deploys all 5 stacks
```

> **NCI accounts** use a patched bootstrap (PowerUser boundary). See `.claude/context/` for the NCI-specific bootstrap procedure.

## C4 — Create Cognito Users

```bash
just create-users
```

| User | Email | Password | Tenant | Tier |
|------|-------|----------|--------|------|
| Test | testuser@example.com | EagleTest2024! | nci | basic |
| Admin | admin@example.com | EagleAdmin2024! | nci | premium |

<details>
<summary>Manual user creation</summary>

```bash
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name EagleCoreStack \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text)

aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username testuser@example.com \
  --user-attributes \
    Name=email,Value=testuser@example.com \
    Name=email_verified,Value=true \
    Name=given_name,Value=Test \
    Name=family_name,Value=User \
    Name=custom:tenant_id,Value=nci \
    Name=custom:subscription_tier,Value=basic \
  --temporary-password 'TempPass123!' \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username testuser@example.com \
  --password 'EagleTest2024!' \
  --permanent
```

</details>

## C5 — Set GitHub Secret for CI/CD

```bash
# Get the deploy role ARN from CiCdStack
aws cloudformation describe-stacks --stack-name EagleCiCdStack \
  --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" --output text

# Set the secret (or use gh CLI):
gh secret set DEPLOY_ROLE_ARN --body "arn:aws:iam::ACCOUNT_ID:role/eagle-github-actions-dev"
```

## C6 — Upload Knowledge Base Documents *(optional)*

```bash
aws s3 sync path/to/knowledge-base/ s3://eagle-documents-{account-id}-dev/eagle/knowledge-base/ \
  --region us-east-1
```

S3 event notifications auto-trigger the metadata extraction Lambda on upload.
