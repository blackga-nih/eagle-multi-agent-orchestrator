---
type: expert-file
file-type: index
domain: backend
tags: [expert, backend, agentic-service, eagle, aws, s3, dynamodb, cloudwatch, anthropic]
---

# Backend Expert

> EAGLE Agentic Service specialist for tool dispatch, AWS integrations, document generation, tenant scoping, and system prompt architecture.

## Domain Scope

This expert covers:
- **Agentic Service** - `server/app/agentic_service.py` (2357 lines) — main backend file
- **Tool Dispatch** - `execute_tool()`, `TOOL_DISPATCH` dict, `TOOLS_NEEDING_SESSION` set
- **AWS Tool Handlers** - S3 ops, DynamoDB intake, CloudWatch logs, FAR search, document generation, intake status, intake workflow
- **Tenant Scoping** - `_extract_tenant_id()`, `_extract_user_id()`, `_get_user_prefix()`, per-tenant S3/DDB isolation
- **Document Generation** - 10 doc types with `_generate_*()` functions, S3 persistence
- **SYSTEM_PROMPT** - 5-phase intake workflow, specialist lenses, key thresholds, tool guidance
- **Anthropic Client** - Bedrock toggle, `stream_chat()` tool-use loop, `get_client()`

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:backend:question` | Answer backend questions without coding |
| `/experts:backend:plan` | Plan backend changes using expertise context |
| `/experts:backend:self-improve` | Update expertise after implementations |
| `/experts:backend:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:backend:maintenance` | Run checks and validate backend health |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for backend domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for backend changes |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation and health check command |

## Architecture

```
server/app/agentic_service.py (2357 lines)
  |
  |-- SYSTEM_PROMPT: ~4800 chars, 7 sections
  |     |-- Identity & Mission
  |     |-- Intake Philosophy ("Trish" pattern)
  |     |-- Five-Phase Intake Workflow
  |     |-- Key Thresholds (MPT, SAT, etc.)
  |     |-- Specialist Lenses (Legal, Tech, Market, Public)
  |     |-- Document Types (10 types)
  |     |-- Tool Usage Guidance
  |
  |-- AWS Clients (lazy singletons)
  |     |-- _get_s3()       -> boto3 S3 client (us-east-1)
  |     |-- _get_dynamodb() -> boto3 DynamoDB resource (us-east-1)
  |     |-- _get_logs()     -> boto3 CloudWatch Logs client (us-east-1)
  |
  |-- Tenant Scoping
  |     |-- _extract_tenant_id(session_id) -> "demo-tenant"
  |     |-- _extract_user_id(session_id)   -> "demo-user" or ws-* session
  |     |-- _get_user_prefix(session_id)   -> "eagle/{tenant}/{user}/"
  |
  |-- EAGLE_TOOLS: Anthropic tool_use schema definitions
  |
  |-- Tool Handlers
  |     |-- _exec_s3_document_ops()       line 384
  |     |-- _exec_dynamodb_intake()       line 471
  |     |-- _exec_cloudwatch_logs()       line 589
  |     |-- _exec_search_far()            line 708
  |     |-- _exec_create_document()       line 1027
  |     |-- _exec_get_intake_status()     line 1828
  |     |-- _exec_intake_workflow()       line 1955
  |
  |-- Document Generators (10 functions)
  |     |-- _generate_sow()                         line 1086
  |     |-- _generate_igce()                         line 1173
  |     |-- _generate_market_research()              line 1250
  |     |-- _generate_justification()                line 1313
  |     |-- _generate_acquisition_plan()             line 1381
  |     |-- _generate_eval_criteria()                line 1481
  |     |-- _generate_security_checklist()           line 1546
  |     |-- _generate_section_508()                  line 1610
  |     |-- _generate_cor_certification()            line 1681
  |     |-- _generate_contract_type_justification()  line 1754
  |
  |-- TOOL_DISPATCH dict                  line 2167
  |-- TOOLS_NEEDING_SESSION set           line 2178
  |-- execute_tool()                      line 2181
  |
  |-- Anthropic Client
  |     |-- get_client()    -> Anthropic or AnthropicBedrock
  |     |-- stream_chat()   -> tool-use loop with callbacks
```

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Add/modify tool handlers, update dispatch, change prompts
LEARN  ->  Update expertise.md with patterns and issues
REUSE  ->  Apply patterns to future backend development
```
