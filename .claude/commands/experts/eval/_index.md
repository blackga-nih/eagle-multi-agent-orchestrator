---
type: expert-file
file-type: index
domain: eval
tags: [expert, eval, testing, eagle, sdk, aws, cloudwatch, boto3]
---

# Eval Expert

> EAGLE SDK Evaluation Suite specialist for test development, AWS tool integration testing, and CloudWatch telemetry verification.

## Domain Scope

This expert covers:
- **Test Suite** - `server/tests/test_eagle_sdk_eval.py` (20 tests across 3 tiers)
- **SDK Patterns** (1-6) - Sessions, resume, traces, subagents, cost tracking, MCP tools
- **Skill Validation** (7-15) - OA intake, legal, market, tech, public interest, doc gen, supervisor chain
- **AWS Tool Integration** (16-20) - S3 ops, DynamoDB CRUD, CloudWatch logs, document generation, E2E verification
- **CloudWatch Telemetry** - `/eagle/test-runs` log group, per-run streams, structured events
- **Agentic Service** - `server/app/agentic_service.py` tools: `execute_tool()`, S3, DynamoDB, CloudWatch, document generators

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:eval:question` | Answer eval suite questions without coding |
| `/experts:eval:plan` | Plan new tests or eval changes |
| `/experts:eval:add-test` | Scaffold and register a new test (full SOP) |
| `/experts:eval:self-improve` | Update expertise after test runs |
| `/experts:eval:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:eval:maintenance` | Run eval suite and report results |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for eval domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for new tests |
| `add-test.md` | Add test command (scaffold + 8-point registration) |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Run tests and report results |

## Architecture

```
server/tests/test_eagle_sdk_eval.py
  |-- Tests 1-6:  claude-agent-sdk query() calls (LLM-based, Bedrock)
  |-- Tests 7-15: Skill loading via system_prompt (LLM-based)
  |-- Tests 16-20: execute_tool() direct calls (no LLM, boto3 confirm)
  |
  |-- TraceCollector: SDK message trace observer
  |-- CapturingStream: stdout capture for per-test logs
  |-- emit_to_cloudwatch(): structured JSON to /eagle/test-runs
  |-- trace_logs.json: local file output for dashboard

server/app/agentic_service.py
  |-- execute_tool(): tool dispatch router
  |-- _exec_s3_document_ops(): S3 read/write/list
  |-- _exec_dynamodb_intake(): DDB create/read/update/list
  |-- _exec_cloudwatch_logs(): CW get_stream/recent/search
  |-- _exec_create_document(): 10 doc type generators + S3 save
```

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Add/modify tests, run eval suite
LEARN  ->  Update expertise.md with patterns and failures
REUSE  ->  Apply patterns to future test development
```
