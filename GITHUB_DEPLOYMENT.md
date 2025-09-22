# Complete GitHub Deployment Guide

## 📋 **Pre-Deployment Checklist**

### **Required Files (All Present):**
- ✅ `.github/workflows/deploy.yml` - Main deployment workflow
- ✅ `infra/cdk/app.py` - CDK infrastructure stack
- ✅ `infra/cdk/bedrock_agents.py` - Bedrock Agent configuration
- ✅ `infra/cdk/requirements.txt` - CDK dependencies
- ✅ `infra/cdk/cdk.json` - CDK configuration
- ✅ `scripts/create_test_user.py` - User creation script
- ✅ `app/` - Complete application code
- ✅ `requirements.txt` - Python dependencies

## 🚀 **Step-by-Step Deployment**

### **Step 1: Repository Setup**

#### **1.1 Create GitHub Repository**
```bash
# Create new repository on GitHub
# Clone locally
git clone https://github.com/YOUR_USERNAME/multi-tenant-bedrock-chat.git
cd multi-tenant-bedrock-chat

# Copy all files to repository
cp -r /path/to/Agent-Core/* .
```

#### **1.2 Set GitHub Secrets**
Go to: **Repository → Settings → Secrets and variables → Actions**

**Required Secrets:**
```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
JWT_SECRET=your-production-secret-key
```

### **Step 2: AWS Permissions**

#### **2.1 IAM User Permissions**
Your AWS user needs these policies:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "cognito-idp:*",
        "dynamodb:*",
        "bedrock:*",
        "lambda:*",
        "iam:*",
        "s3:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### **Step 3: Deploy Infrastructure**

#### **3.1 Push to Main Branch**
```bash
git add .
git commit -m "Initial deployment of multi-tenant Bedrock chat"
git push origin main
```

#### **3.2 Monitor Deployment**
1. Go to **Actions** tab in GitHub
2. Watch **"Deploy Multi-Tenant Bedrock Chat"** workflow
3. Check each step for success/failure

#### **3.3 Expected Workflow Steps**
```
✅ Deploy Infrastructure (CDK)
  - Create Cognito User Pool
  - Create DynamoDB Tables
  - Deploy Bedrock Agent
  - Create IAM Roles

✅ Create Test Users
  - Generate users in Cognito
  - Output JWT tokens

✅ Run Tests
  - Test runtime context
  - Validate deployment
```

### **Step 4: Get Deployment Outputs**

#### **4.1 From GitHub Actions Logs**
Look for outputs like:
```
UserPoolId: us-east-1_ABC123DEF
UserPoolClientId: abc123def456ghi789
AgentId: AGENT123
SessionsTableName: tenant-sessions
UsageTableName: tenant-usage
```

#### **4.2 JWT Tokens**
From the "Create Test Users" step:
```
✅ Created user: tenant1-user1 (Tenant: tenant-001)
   JWT Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

✅ Created user: tenant2-user1 (Tenant: tenant-002)
   JWT Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### **Step 5: Test Deployment**

#### **5.1 Run Application Locally**
```bash
# Set environment variables from deployment
export COGNITO_USER_POOL_ID="us-east-1_ABC123DEF"
export COGNITO_CLIENT_ID="abc123def456ghi789"
export BEDROCK_AGENT_ID="AGENT123"
export AWS_REGION="us-east-1"

# Run application
python run.py
```

#### **5.2 Test in Browser**
1. Open: http://localhost:8000
2. Paste JWT token from deployment logs
3. Click "Set Auth" → "Create Session"
4. Send test messages
5. Verify tenant isolation

### **Step 6: Verify Multi-Tenancy**

#### **6.1 Test Different Tenants**
```bash
# Use tenant-001 JWT token
# Create session, send messages
# Check usage: /api/tenants/tenant-001/usage

# Use tenant-002 JWT token  
# Create session, send messages
# Check usage: /api/tenants/tenant-002/usage

# Verify complete isolation
```

## 🔧 **Troubleshooting**

### **Common Issues:**

#### **CDK Bootstrap Error**
```bash
# If CDK bootstrap fails
cdk bootstrap aws://ACCOUNT-ID/us-east-1
```

#### **Bedrock Agent Creation Fails**
```bash
# Check Bedrock service availability in region
# Ensure proper IAM permissions
```

#### **Cognito User Creation Fails**
```bash
# Check if custom attributes are supported
# Verify IAM permissions for Cognito
```

### **Debug Steps:**
1. Check GitHub Actions logs for specific errors
2. Verify AWS credentials and permissions
3. Check CloudFormation stack in AWS Console
4. Validate CDK synthesis: `cd infra/cdk && cdk synth`

## 📊 **Post-Deployment Verification**

### **AWS Console Checks:**
- ✅ **CloudFormation** - Stack deployed successfully
- ✅ **Cognito** - User pool with custom attributes
- ✅ **DynamoDB** - Tables created (tenant-sessions, tenant-usage)
- ✅ **Bedrock** - Agent deployed with Claude 3.5 Sonnet
- ✅ **Lambda** - Action group functions created

### **Application Checks:**
- ✅ **Authentication** - JWT tokens work
- ✅ **Sessions** - Created per tenant
- ✅ **Chat** - Messages processed by Bedrock Agent
- ✅ **Isolation** - Tenants see only their data
- ✅ **Analytics** - Usage metrics tracked per tenant

## 🎯 **Success Criteria**

Your deployment is successful when:
1. ✅ GitHub Actions workflow completes without errors
2. ✅ AWS resources are created in CloudFormation
3. ✅ JWT tokens are generated for test users
4. ✅ Application runs locally with deployed infrastructure
5. ✅ Multi-tenant isolation is verified
6. ✅ Bedrock Agent responds to chat messages
7. ✅ Usage analytics show tenant-specific data

## 🔄 **Continuous Deployment**

Future changes automatically deploy when you:
```bash
git add .
git commit -m "Update application"
git push origin main
```

The GitHub Actions workflow will:
- Update infrastructure if CDK files changed
- Recreate test users if needed
- Run tests to verify deployment