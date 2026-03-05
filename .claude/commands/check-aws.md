---
description: Check AWS credentials, Bedrock access, and S3/DynamoDB/CloudWatch connectivity
argument-hint: [--verbose]
---

# /check-aws

Check AWS credentials, caller identity, Bedrock model access, and connectivity to the AWS services used by the EAGLE eval suite.

## Variables
- `VERBOSE`: Include detailed output for each service check

## Instructions
- Validate AWS credentials using STS GetCallerIdentity
- Check Bedrock model access (Haiku)
- Verify S3 bucket, DynamoDB table, and CloudWatch log group exist
- Report account ID, ARN, and region
- IMPORTANT: Never expose secret keys in output

## Workflow

1. **Check AWS Identity**:
   ```bash
   python -c "
   import boto3, json
   sts = boto3.client('sts', region_name='us-east-1')
   identity = sts.get_caller_identity()
   print(json.dumps({
       'Account': identity['Account'],
       'Arn': identity['Arn'],
       'Region': 'us-east-1'
   }, indent=2))
   "
   ```

2. **Check S3 Bucket** (nci-documents):
   ```bash
   python -c "
   import boto3
   s3 = boto3.client('s3', region_name='us-east-1')
   try:
       s3.head_bucket(Bucket='nci-documents')
       print('S3 nci-documents: OK')
   except Exception as e:
       print(f'S3 nci-documents: FAIL - {e}')
   "
   ```

3. **Check DynamoDB Table** (eagle):
   ```bash
   python -c "
   import boto3
   ddb = boto3.client('dynamodb', region_name='us-east-1')
   try:
       resp = ddb.describe_table(TableName='eagle')
       status = resp['Table']['TableStatus']
       print(f'DynamoDB eagle: {status}')
   except Exception as e:
       print(f'DynamoDB eagle: FAIL - {e}')
   "
   ```

4. **Check CloudWatch Log Group** (/eagle/test-runs):
   ```bash
   python -c "
   import boto3
   logs = boto3.client('logs', region_name='us-east-1')
   try:
       resp = logs.describe_log_groups(logGroupNamePrefix='/eagle/test-runs')
       groups = [g['logGroupName'] for g in resp.get('logGroups', [])]
       if '/eagle/test-runs' in groups:
           print('CloudWatch /eagle/test-runs: OK')
       else:
           print('CloudWatch /eagle/test-runs: NOT FOUND')
   except Exception as e:
       print(f'CloudWatch: FAIL - {e}')
   "
   ```

5. **Check Bedrock Access**:
   ```bash
   python -c "
   import boto3
   bedrock = boto3.client('bedrock', region_name='us-east-1')
   try:
       resp = bedrock.list_foundation_models(byProvider='Anthropic')
       models = [m['modelId'] for m in resp.get('modelSummaries', []) if 'haiku' in m['modelId'].lower()]
       print(f'Bedrock Anthropic Haiku models: {len(models)}')
       for m in models[:3]:
           print(f'  {m}')
   except Exception as e:
       print(f'Bedrock: FAIL - {e}')
   "
   ```

## Report
```
AWS Environment Check — EAGLE Eval Suite
+-----------------+------------------+
| Service         | Status           |
+-----------------+------------------+
| AWS Identity    | OK / FAIL        |
| S3 Bucket       | OK / FAIL        |
| DynamoDB Table  | OK / FAIL        |
| CloudWatch Logs | OK / FAIL        |
| Bedrock Access  | OK / FAIL        |
+-----------------+------------------+
```
