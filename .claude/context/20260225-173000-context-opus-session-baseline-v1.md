# Opus Session Baseline — Feb 23 2026

**Purpose**: Reference baseline for future Haiku comparison. Captures everything available about the 12-minute Opus session that generated $71.26 in Bedrock charges.

---

## Session Metadata

| Field | Value |
|---|---|
| Date | 2026-02-23 |
| Time (ET) | 19:42 – 19:53 (12 minutes) |
| Time (UTC) | 2026-02-24 00:42 – 00:53 |
| User | pinedar@nih.gov |
| Source IP | 128.231.234.8 (NIH workstation) |
| IAM Role | AWSReservedSSO_NCIAWSPowerUserAccess_679a31105bdc1d70 |
| User Agent | claude-cli/2.1.50 (external, cli) |
| Bedrock Endpoint | bedrock-runtime.us-east-1.amazonaws.com |
| Inference Region (Opus) | us-east-2 (cross-region inference) |
| Inference Region (Haiku) | global pool — us-east-2, us-west-2, ap-northeast-2, eu-north-1, eu-west-1 |

## Billing

| Day | Model | Charges |
|---|---|---|
| Feb 23 | Opus 4.6 | $64.33 |
| Feb 24 | Opus 4.6 | $6.93 (same session, crossed UTC midnight) |
| **Total** | | **$71.26** |

## Call Volume

| Model | Calls |
|---|---|
| `us.anthropic.claude-opus-4-6-v1` | **29** |
| `global.anthropic.claude-haiku-4-5-20251001-v1:0` | **13** |

Pattern: Haiku fires first (tool use / context management), Opus fires 1–3 seconds later (main response). Typical sub-task cadence: 1 Haiku + 1–5 Opus calls, then a gap of 1–2 minutes before the next task.

## Call Timeline

```
19:42:48 haiku  → 19:42:49 opus                          [task 1 — ~1 min gap to task 2]
19:43:48 haiku  → 19:43:49 opus                          [task 2]
19:44:09 haiku  → 19:44:11 opus
19:44:14 haiku  → 19:44:15 opus
                → 19:44:18 opus                          [task 3 burst — 3 opus calls]
19:45:36 haiku  → 19:45:38 opus
19:45:46 haiku  → 19:45:48 opus
                → 19:45:52 opus                          [task 4 burst — ~1 min 14s gap]
19:47:06 haiku  → 19:47:08 opus
                → 19:47:15 opus
                → 19:47:24 opus
                → 19:47:43 opus
                → 19:47:47 opus
19:47:51 haiku  → 19:47:53 opus
                → 19:48:01 opus                          [task 5 large burst — ~1 min 24s gap]
19:49:25 haiku  → 19:49:27 opus
                → 19:49:37 opus
                → 19:49:41 opus
                → 19:49:46 opus
                → 19:49:49 opus
19:50:03 haiku  → 19:50:05 opus
                → 19:50:13 opus
                → 19:50:16 opus                          [task 6 large burst]
19:50:54 haiku  → 19:50:56 opus
                → 19:51:00 opus
                → 19:51:04 opus                          [task 7 — ~1 min 49s gap to task 8]
19:52:53 haiku  → 19:52:55 opus                          [task 8]
19:53:10 haiku  → 19:53:12 opus
                → 19:53:15 opus                          [task 9 — session ends]
```

**Longest gaps** (likely largest Opus outputs):
- After 19:48:01 → 1m 24s until next task
- After 19:51:04 → 1m 49s until next task ← probable biggest output
- After 19:45:52 → 1m 14s until next task

## Content Availability

**CloudTrail captures**: model ID, request ID, timestamp, IAM principal, source IP only. No prompt or response content.

**Bedrock model invocation logging**: NOT enabled as of 2026-02-25. To enable for future sessions:
```bash
AWS_PROFILE=eagle aws bedrock put-model-invocation-logging-configuration \
  --region us-east-1 \
  --logging-config '{
    "cloudWatchConfig": {
      "logGroupName": "/aws/bedrock/model-invocations",
      "roleArn": "arn:aws:iam::695681773636:role/..."
    },
    "textDataDeliveryEnabled": true
  }'
```

**Local transcripts**: Stored on pinedar@nih.gov's workstation at:
```
~/.claude/projects/<project-hash>/<session-id>.jsonl
```
pinedar can share that file to recover actual prompts and responses.

## Suggested Haiku Comparison Methodology

When running the equivalent tasks with Haiku, capture:

1. **Timing**: Did the same tasks complete in similar wall-clock time?
2. **Call count**: Haiku may need more turns for complex reasoning tasks
3. **Output quality**: Did Haiku produce equivalent analysis depth for `/code-review`, `/fix`, `/scribe`?
4. **Cost**: Target <$5 for equivalent session (vs $71.26 for Opus)

Enable Bedrock invocation logging before the comparison run so actual prompts/responses are preserved.
