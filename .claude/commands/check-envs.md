---
description: Check all environment credentials and service connectivity for the EAGLE eval suite
---

# /check-envs

Check all configured environment credentials and service connectivity required by the EAGLE SDK Evaluation Suite.

## Variables
- `SERVICES`: Optional comma-separated list (default: all)

## Instructions
- Run credential and connectivity checks for each required service
- Report status for each configured service
- Highlight any credentials that are missing or invalid
- IMPORTANT: Never expose actual credential values in output

## Workflow

1. **Run All Checks** — Execute each service check and capture results:

   ```bash
   python -c "
   import os, sys

   results = []

   # 1. AWS Credentials
   try:
       import boto3
       sts = boto3.client('sts', region_name='us-east-1')
       identity = sts.get_caller_identity()
       results.append(('AWS Credentials', 'OK', f'Account: {identity[\"Account\"]}'))
   except Exception as e:
       results.append(('AWS Credentials', 'FAIL', str(e)[:60]))

   # 2. S3 Bucket
   try:
       s3 = boto3.client('s3', region_name='us-east-1')
       s3.head_bucket(Bucket='nci-documents')
       results.append(('S3 (nci-documents)', 'OK', 'Bucket accessible'))
   except Exception as e:
       results.append(('S3 (nci-documents)', 'FAIL', str(e)[:60]))

   # 3. DynamoDB Table
   try:
       ddb = boto3.client('dynamodb', region_name='us-east-1')
       resp = ddb.describe_table(TableName='eagle')
       results.append(('DynamoDB (eagle)', 'OK', f'Status: {resp[\"Table\"][\"TableStatus\"]}'))
   except Exception as e:
       results.append(('DynamoDB (eagle)', 'FAIL', str(e)[:60]))

   # 4. CloudWatch
   try:
       logs = boto3.client('logs', region_name='us-east-1')
       resp = logs.describe_log_groups(logGroupNamePrefix='/eagle/test-runs')
       found = any(g['logGroupName'] == '/eagle/test-runs' for g in resp.get('logGroups', []))
       results.append(('CloudWatch (/eagle/test-runs)', 'OK' if found else 'MISSING', 'Log group ' + ('exists' if found else 'not found')))
   except Exception as e:
       results.append(('CloudWatch', 'FAIL', str(e)[:60]))

   # 5. Bedrock
   try:
       bedrock = boto3.client('bedrock', region_name='us-east-1')
       resp = bedrock.list_foundation_models(byProvider='Anthropic')
       count = len([m for m in resp.get('modelSummaries', []) if 'haiku' in m['modelId'].lower()])
       results.append(('Bedrock (Anthropic)', 'OK', f'{count} Haiku models available'))
   except Exception as e:
       results.append(('Bedrock (Anthropic)', 'FAIL', str(e)[:60]))

   # 6. Python imports
   try:
       from claude_agent_sdk import query
       results.append(('claude-agent-sdk', 'OK', 'Importable'))
   except ImportError:
       results.append(('claude-agent-sdk', 'FAIL', 'Not installed'))

   # 7. agentic_service import
   try:
       sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('.')), 'app'))
       sys.path.insert(0, 'app')
       from agentic_service import execute_tool
       results.append(('execute_tool import', 'OK', 'Importable from app/'))
   except Exception as e:
       results.append(('execute_tool import', 'FAIL', str(e)[:60]))

   # Report
   print()
   print('Environment Check — EAGLE Eval Suite')
   print('=' * 65)
   for name, status, detail in results:
       icon = 'OK' if status == 'OK' else 'FAIL' if status == 'FAIL' else 'WARN'
       print(f'  {name:30s} {icon:6s} {detail}')
   print('=' * 65)
   ok = sum(1 for _, s, _ in results if s == 'OK')
   total = len(results)
   print(f'  Summary: {ok}/{total} services active')
   "
   ```

2. **Parse Results** - Review the status of each service:
   - OK = Credentials valid and service accessible
   - WARN = Partially available
   - FAIL = Credentials rejected or service unavailable

3. **Report Issues** - For any failed services, suggest remediation:
   - AWS: Check `~/.aws/credentials` or environment variables
   - Bedrock: Verify model access is enabled in AWS console
   - S3/DynamoDB: Verify resources exist in us-east-1
   - CloudWatch: Log group auto-created on first test run
   - claude-agent-sdk: `pip install claude-agent-sdk`
