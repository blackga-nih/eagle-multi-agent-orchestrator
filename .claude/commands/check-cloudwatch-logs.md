---
description: Scan CloudWatch logs for errors across EAGLE ECS services. Run hourly with /loop 1h /check-logs or on-demand.
argument-hint: [1h|4h|24h|7d] [keyword] [--backend|--frontend|--all]
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
| `/aws/bedrock/modelinvocations` | Bedrock API calls (shared) | none |

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
   - `--all` — query ALL 7 log groups

5. **Use these parameters for every query:**
   - `region: "us-east-1"`
   - `profile_name: "eagle"`

6. **Produce a summary table:**
   - Group errors by type/category
   - Count occurrences
   - Mark as **ACTIONABLE** or **Noise**
   - For IAM errors: note exact role ARN, denied action, resource ARN

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

Summary: X actionable errors, Y warnings, Z noise
```

If zero errors found, report "All clear — no errors in the last {duration}."

## Hourly Loop Usage

To run this every hour automatically:

```
/loop 1h /check-logs
```

This will scan the last 1 hour of logs on each run, catching new errors as they appear.
