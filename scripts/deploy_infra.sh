#!/bin/bash

echo "🏗️ Deploying Multi-Tenant Bedrock Infrastructure"
echo "================================================"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Check CDK
if ! command -v cdk &> /dev/null; then
    echo "❌ AWS CDK not found. Installing..."
    npm install -g aws-cdk
fi

# Navigate to CDK directory
cd infra/cdk

# Install CDK dependencies
echo "📦 Installing CDK dependencies..."
pip install -r requirements.txt

# Bootstrap CDK (if needed)
echo "🚀 Bootstrapping CDK..."
cdk bootstrap

# Deploy infrastructure
echo "🏗️ Deploying infrastructure..."
cdk deploy --require-approval never

# Get outputs
echo "📋 Getting deployment outputs..."
OUTPUTS=$(cdk output --json)

# Extract values
USER_POOL_ID=$(echo $OUTPUTS | jq -r '.MultiTenantBedrockStack.UserPoolId // empty')
CLIENT_ID=$(echo $OUTPUTS | jq -r '.MultiTenantBedrockStack.UserPoolClientId // empty')
SESSIONS_TABLE=$(echo $OUTPUTS | jq -r '.MultiTenantBedrockStack.SessionsTableName // empty')
USAGE_TABLE=$(echo $OUTPUTS | jq -r '.MultiTenantBedrockStack.UsageTableName // empty')

# Create .env file
cd ../../
echo "📝 Creating .env file..."

cat > .env << EOF
# Cognito Configuration
COGNITO_USER_POOL_ID=${USER_POOL_ID}
COGNITO_CLIENT_ID=${CLIENT_ID}

# DynamoDB Configuration  
SESSIONS_TABLE=${SESSIONS_TABLE}
USAGE_TABLE=${USAGE_TABLE}

# Bedrock Configuration (optional - uses Claude 3.5 Sonnet directly)
BEDROCK_AGENT_ID=
BEDROCK_AGENT_ALIAS_ID=TSTALIASID
AWS_REGION=us-east-1

# Application Configuration
APP_HOST=0.0.0.0
APP_PORT=8000
JWT_SECRET=multi-tenant-secret-key-$(date +%s)
EOF

echo "✅ Infrastructure deployed successfully!"
echo ""
echo "📋 Configuration:"
echo "   User Pool ID: ${USER_POOL_ID}"
echo "   Client ID: ${CLIENT_ID}"
echo "   Sessions Table: ${SESSIONS_TABLE}"
echo "   Usage Table: ${USAGE_TABLE}"
echo ""
echo "🔧 Next steps:"
echo "   1. Run: python scripts/create_test_user.py"
echo "   2. Run: python run.py"