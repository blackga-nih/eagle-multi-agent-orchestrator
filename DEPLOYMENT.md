# GitHub Actions Deployment Guide

## 🚀 **Automated AWS Deployment**

### **1. Repository Setup**

#### **Required GitHub Secrets:**
```bash
# AWS Credentials
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...

# Application Secrets
JWT_SECRET=your-production-jwt-secret
```

#### **Set Secrets in GitHub:**
1. Go to repository → Settings → Secrets and variables → Actions
2. Add the required secrets above

### **2. Deployment Workflows**

#### **Main Deployment (`deploy.yml`):**
- **Triggers:** Push to `main` branch
- **Steps:**
  1. Deploy CDK infrastructure (DynamoDB, Cognito, Bedrock Agents)
  2. Create test users with JWT tokens
  3. Run integration tests

#### **Docker Deployment (`docker-deploy.yml`):**
- **Triggers:** Changes to app code, Dockerfile
- **Steps:**
  1. Build Docker image
  2. Push to Amazon ECR
  3. Update ECS service (if exists)

### **3. Infrastructure Components Deployed**

#### **AWS Services:**
- **Amazon Cognito** - User authentication with tenant attributes
- **Amazon DynamoDB** - Session and usage storage
- **Amazon Bedrock** - Agent with Claude 3.5 Sonnet
- **AWS Lambda** - Action groups for tenant operations
- **Amazon ECR** - Container registry (optional)
- **Amazon ECS** - Container service (optional)

#### **CDK Stack Outputs:**
```json
{
  "UserPoolId": "us-east-1_ABC123",
  "UserPoolClientId": "abc123def456",
  "AgentId": "AGENT123",
  "SessionsTableName": "tenant-sessions",
  "UsageTableName": "tenant-usage"
}
```

### **4. Deployment Process**

#### **Automatic Deployment:**
```bash
# Push to main branch triggers deployment
git add .
git commit -m "Deploy multi-tenant chat app"
git push origin main
```

#### **Manual Deployment:**
```bash
# Trigger workflow manually
# Go to Actions tab → Deploy Multi-Tenant Bedrock Chat → Run workflow
```

### **5. Environment Configuration**

#### **Production Environment Variables:**
```bash
# Set automatically by GitHub Actions
COGNITO_USER_POOL_ID=us-east-1_ABC123
COGNITO_CLIENT_ID=abc123def456
BEDROCK_AGENT_ID=AGENT123
AWS_REGION=us-east-1
SESSIONS_TABLE=tenant-sessions
USAGE_TABLE=tenant-usage
JWT_SECRET=production-secret
```

### **6. Monitoring Deployment**

#### **GitHub Actions:**
- View deployment progress in Actions tab
- Check logs for any errors
- Monitor CDK deployment status

#### **AWS Console:**
- **CloudFormation** - Stack deployment status
- **Cognito** - User pool creation
- **Bedrock** - Agent deployment
- **DynamoDB** - Table creation

### **7. Post-Deployment Testing**

#### **Automatic Tests:**
- Runtime context demo
- Integration tests (if configured)

#### **Manual Testing:**
```bash
# Get deployment outputs
export COGNITO_USER_POOL_ID="from-github-actions-output"
export COGNITO_CLIENT_ID="from-github-actions-output"

# Test locally
python scripts/create_test_user.py
python run.py
```

### **8. Production Deployment (ECS)**

#### **Enable ECS Deployment:**
1. Uncomment ECS service in `infra/cdk/app.py`
2. Push changes to trigger deployment
3. Access via Application Load Balancer DNS

#### **ECS Service Features:**
- **Auto-scaling** based on CPU/memory
- **Health checks** for container health
- **Load balancing** across multiple instances
- **Rolling deployments** for zero downtime

### **9. Rollback Strategy**

#### **Infrastructure Rollback:**
```bash
# Revert CDK stack to previous version
cd infra/cdk
cdk deploy --previous-parameters
```

#### **Application Rollback:**
```bash
# Deploy previous Docker image
aws ecs update-service \
  --cluster multi-tenant-cluster \
  --service multi-tenant-chat-service \
  --task-definition previous-task-def
```

### **10. Cost Optimization**

#### **Development:**
- DynamoDB on-demand pricing
- Single ECS task
- No NAT Gateway (public subnets)

#### **Production:**
- DynamoDB provisioned capacity
- Auto-scaling ECS tasks
- Multi-AZ deployment

## ✅ **Deployment Checklist**

- [ ] Set GitHub secrets (AWS credentials, JWT secret)
- [ ] Push code to main branch
- [ ] Monitor GitHub Actions deployment
- [ ] Verify AWS resources created
- [ ] Test with generated JWT tokens
- [ ] Enable ECS for production (optional)
- [ ] Configure monitoring and alerts

The GitHub Actions workflows provide complete automation for deploying the multi-tenant Bedrock chat application to AWS.