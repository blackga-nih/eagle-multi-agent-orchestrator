#!/bin/bash

echo "🚀 Multi-Tenant Bedrock Chat Deployment"
echo "======================================="

# Check if Bedrock Agent ID is set
if [ -z "$BEDROCK_AGENT_ID" ]; then
    echo "❌ BEDROCK_AGENT_ID environment variable is required"
    echo "💡 Set it with: export BEDROCK_AGENT_ID=your-agent-id"
    exit 1
fi

echo "✅ Bedrock Agent ID: $BEDROCK_AGENT_ID"

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Validate AWS credentials
echo "🔐 Checking AWS credentials..."
aws sts get-caller-identity > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ AWS credentials not configured"
    echo "💡 Run: aws configure"
    exit 1
fi

echo "✅ AWS credentials valid"

# Start the application
echo "🚀 Starting multi-tenant chat application..."
python run.py