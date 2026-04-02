---
description: Scan CloudWatch logs for errors across EAGLE ECS services. Run hourly with /loop 1h /check-logs or on-demand.
argument-hint: [1h|4h|24h|7d] [keyword] [--backend|--frontend|--bedrock|--all]
---

# Check CloudWatch Logs for Errors

Query CloudWatch Logs Insights for recent errors across EAGLE ECS services.

## Prerequisites — SSO Login

Before querying, verify SSO credentials are valid. If expired, instruct the user to run:

```bash
aws sso login --profile eagle
```

Quick check (run this FIRST before any CloudWatch queries):

```bash
aws sts get-caller-identity --profile eagle 2>&1
```

If this returns an error containing `expired` or `Token`, stop and tell the user to re-authenticate.

## EAGLE Log Groups

| Log Group | Purpose | Retention |
|-----------|---------|-----------|
| `/eagle/ecs/backend-dev` | Backend ECS Fargate tasks (FastAPI) | 30 days |
| `/eagle/ecs/frontend-dev` | Frontend ECS tasks (Next.js) | 30 days |
| `/eagle/app` | Application-level logs (tool dispatch, sessions) | 90 days |
| `/eagle/inference` | Model inference telemetry (Bedrock calls) | none |
| `/eagle/lambda/metadata-extraction-dev` | Metadata extraction Lambda | 30 days |
| `/aws/ecs/containerinsights/eagle-dev/performance` | Container insights | 1 day |
| `/aws/bedrock/modelinvocations` | Bedrock per-call invocation logs (latency, tokens, model ID, errors) | 2 weeks |

## Instructions

1. **Validate SSO** by running `aws sts get-caller-identity --profile eagle`. If it fails, tell the user to `aws sso login --profile eagle` and stop.

2. **Query log groups in parallel** using `mcp__cloudwatch-mcp-server__execute_log_insights_query`. Query these groups simultaneously:
   - `/eagle/ecs/backend-dev`
   - `/eagle/ecs/frontend-dev`
   - `/eagle/app`

3. **Base query:**

```
filter @message like /(?i)(error|ERROR|exception|Exception|FATAL|fatal|crash|fail|FAIL)/
| fields @timestamp, @logStream, @message
| sort @timestamp desc
| limit 30
```

4. **Time window:** Default is **1 hour** (for hourly loop usage). If the user passes an argument:
   - `1h`, `4h`, `24h`, `7d`, `30m` — adjust `start_time` accordingly
   - A keyword like `AccessDenied`, `OOM`, `SIGTERM` — add to the filter
   - `--backend` — query only `/eagle/ecs/backend-dev`
   - `--frontend` — query only `/eagle/ecs/frontend-dev`
   - `--bedrock` — query only `/aws/bedrock/modelinvocations` (uses Bedrock-specific query below)
   - `--all` — query ALL 7 log groups (includes Bedrock invocation logs)

5. **Use these parameters for every query:**
   - `region: "us-east-1"`
   - `profile_name: "eagle"`

6. **Produce a summary table:**
   - Group errors by type/category
   - Count occurrences
   - Mark as **ACTIONABLE** or **Noise**
   - For IAM errors: note exact role ARN, denied action, resource ARN

## Bedrock Invocation Log Queries (`--bedrock` or `--all`)

When querying `/aws/bedrock/modelinvocations`, use these Bedrock-specific Insights queries instead of the error-grep pattern. Bedrock invocation logs are structured JSON with fields like `modelId`, `inputTokenCount`, `outputTokenCount`, `invocationLatency`, `errorCode`.

**Latency & TTFT overview** (default for `--bedrock`):

```
stats avg(invocationLatency) as avg_ms,
      max(invocationLatency) as max_ms,
      min(invocationLatency) as min_ms,
      count(*) as calls
by modelId
| sort avg_ms desc
```

**Slow calls** (calls >10s — potential cold starts):

```
filter invocationLatency > 10000
| fields @timestamp, modelId, invocationLatency, inputTokenCount, outputTokenCount, errorCode
| sort invocationLatency desc
| limit 20
```

**Errors only**:

```
filter errorCode != ""
| fields @timestamp, modelId, errorCode, invocationLatency, inputTokenCount
| sort @timestamp desc
| limit 20
```

**Token usage breakdown**:

```
stats sum(inputTokenCount) as total_input,
      sum(outputTokenCount) as total_output,
      count(*) as calls
by modelId
| sort total_input desc
```

### Bedrock-specific setup

- Log group: `/aws/bedrock/modelinvocations` (2-week retention, CDK-managed)
- Logging role: `power-user-eagle-bedrock-logging-dev` (assumes `bedrock.amazonaws.com`, has `PermissionBoundary_PowerUser`)
- Enabled via: `scripts/enable_bedrock_logging.py` (idempotent, re-run after CDK deploys)
- Captures: text data delivery only (images/embeddings disabled)

## Known Error Patterns

| Pattern | Category | Severity |
|---------|----------|----------|
| `Failed to detach context` | OTel async context (handled — spans nest via Langfuse parent wrapper) | Noise |
| `s3:PutObject` AccessDenied | IAM missing permission | ACTIONABLE |
| `s3:GetObject` AccessDenied | IAM missing permission | ACTIONABLE |
| `logs:CreateLogGroup` AccessDenied | IAM missing permission | ACTIONABLE |
| `BadZipFile: File is not a zip file` | Corrupt upload | ACTIONABLE |
| `MemoryStore is not designed for production` | Session store warning | Warning |
| `DeprecationWarning: datetime.utcnow` | Python 3.12 deprecation | Noise |
| `Task stopped` + `Essential container` | ECS task crash | ACTIONABLE |
| `OOM` / `OutOfMemory` | Memory limit exceeded | ACTIONABLE |
| `ThrottlingException` | Bedrock rate limit | Warning |
| `ModelNotReadyException` | Bedrock cold start | Warning |
| `SIGTERM` / `SIGKILL` | Container killed | ACTIONABLE |
| `ModelTimeoutException` (Bedrock) | Bedrock inference timeout — cold start or overload | ACTIONABLE |
| `invocationLatency > 10000` (Bedrock) | Slow call — likely cross-region cold start | Warning |
| `AccessDeniedException` (Bedrock) | IAM role missing bedrock:InvokeModel | ACTIONABLE |
| `ValidationException` (Bedrock) | Bad request (context too long, invalid params) | ACTIONABLE |
| `ResourceNotFoundException` (Bedrock) | Model ID or inference profile not found | ACTIONABLE |

## Report Format

```
EAGLE Log Scan — {timestamp}
Window: last {duration}
SSO Profile: eagle (account 695681773636)

Backend (/eagle/ecs/backend-dev)
┌──────────────────────────────┬───────┬────────────┐
│ Error Category               │ Count │ Severity   │
├──────────────────────────────┼───────┼────────────┤
│ ...                          │ ...   │ ...        │
└──────────────────────────────┴───────┴────────────┘

Frontend (/eagle/ecs/frontend-dev)
┌──────────────────────────────┬───────┬────────────┐
│ ...                          │ ...   │ ...        │
└──────────────────────────────┴───────┴────────────┘

App (/eagle/app)
┌──────────────────────────────┬───────┬────────────┐
│ ...                          │ ...   │ ...        │
└──────────────────────────────┴───────┴────────────┘

Bedrock Invocations (/aws/bedrock/modelinvocations) — if --bedrock or --all
┌──────────────────────┬──────────┬──────────┬──────────┬───────┐
│ Model                │ Avg (ms) │ Max (ms) │ Calls    │ Errors│
├──────────────────────┼──────────┼──────────┼──────────┼───────┤
│ us.anthropic.sonnet…  │ ...      │ ...      │ ...      │ ...   │
└──────────────────────┴──────────┴──────────┴──────────┴───────┘
Slow calls (>10s): {N} — potential cold starts
Top error: {errorCode} ({N} occurrences)

Summary: X actionable errors, Y warnings, Z noise
```

If zero errors found, report "All clear — no errors in the last {duration}."

## Hourly Loop Usage

To run this every hour automatically:

```
/loop 1h /check-logs
```

This will scan the last 1 hour of logs on each run, catching new errors as they appear.
