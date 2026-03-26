---
type: expert-file
file-type: index
domain: eval
tags: [expert, eval, testing, eagle, strands, aws, cloudwatch, langfuse, self-improve]
---

# Eval Expert

> EAGLE Strands Evaluation Suite specialist -- 98 tests across 10 categories, closed-loop agent self-improvement, CloudWatch telemetry, and Langfuse trace validation.

## Domain Scope

This expert covers:
- **Eval Suite** - `server/tests/test_strands_eval.py` (98 tests across 10 categories)
- **Eval Helpers** - `server/tests/eval_helpers.py` (LangfuseTraceValidator, CloudWatchEventValidator, ToolChainValidator, SkillPromptValidator)
- **AWS Publisher** - `server/tests/eval_aws_publisher.py` (CloudWatch custom metrics + S3 archival)
- **Agent Self-Improvement** - Closed-loop: diagnose failures -> edit agent/skill/routing code -> re-validate
- **Strands Orchestration** - `server/app/strands_agentic_service.py` (supervisor + subagents via BedrockModel)
- **Plugin System** - `eagle-plugin/agents/*/agent.md` + `eagle-plugin/skills/*/SKILL.md`
- **CloudWatch Telemetry** - `/eagle/test-runs` log group, structured events, custom metrics
- **Langfuse Traces** - Trace validation, token counts, subagent hierarchy, session propagation

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:eval:question` | Answer eval suite questions without coding |
| `/experts:eval:plan` | Plan new tests or eval changes |
| `/experts:eval:add-test` | Scaffold and register a new test (full SOP) |
| `/experts:eval:self-improve` | **Closed-loop**: diagnose failures, fix agent/skill code, re-validate |
| `/experts:eval:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:eval:maintenance` | Run eval suite and report results |
| `/experts:eval:e2e-judge` | Run the e2e-judge screenshot + vision pipeline |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for eval domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for new tests |
| `add-test.md` | Add test command (scaffold + registration) |
| `self-improve.md` | Closed-loop agent improvement (DIAGNOSE -> PRIORITIZE -> FIX -> VALIDATE) |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Run tests and report results |
| `e2e-judge.md` | Run e2e-judge screenshot + vision pipeline |

## Architecture

```
server/tests/test_strands_eval.py          # 98 tests, standalone CLI (not pytest)
server/tests/eval_helpers.py               # Validators (Langfuse, CloudWatch, ToolChain, SkillPrompt)
server/tests/eval_aws_publisher.py         # CloudWatch metrics + S3 archival
  |
  |-- Categories 1-2:  SDK Patterns (sessions, traces, subagents, cost, tools)
  |-- Categories 3-5:  Skill Validation (7 specialists + supervisor chains)
  |-- Categories 6:    AWS Tool Integration (S3, DynamoDB, CloudWatch, doc gen)
  |-- Category 7:      Langfuse + CloudWatch E2E verification
  |-- Categories 8-10: Context loss, handoff, state persistence, context budget
  |
  |-- TraceCollector: SDK message trace observer
  |-- CapturingStream: stdout capture for per-test logs
  |-- emit_to_cloudwatch(): structured JSON to /eagle/test-runs
  |-- eval_aws_publisher: custom metrics to EAGLE/Eval namespace

server/app/strands_agentic_service.py      # Supervisor + subagent orchestration
  |-- sdk_query(): async generator for LLM queries
  |-- build_skill_tools(): @tool-wrapped subagent factories
  |-- build_supervisor_prompt(): routing prompt generation
  |-- MAX_SKILL_PROMPT_CHARS = 4000: truncation threshold

eagle-plugin/                              # Agent/skill source of truth
  |-- agents/supervisor/agent.md           # FAST vs DEEP routing rules
  |-- agents/oa-intake/agent.md            # OA Intake specialist
  |-- agents/legal-counsel/agent.md        # Legal Counsel specialist
  |-- agents/market-intelligence/agent.md  # Market Intelligence specialist
  |-- agents/tech-translator/agent.md      # Tech Translator specialist
  |-- agents/policy-analyst/agent.md       # Policy Analyst specialist
  |-- agents/public-interest/agent.md      # Public Interest specialist
  |-- agents/document-generator/agent.md   # Document Generator specialist
  |-- skills/*/SKILL.md                    # Skill workflow definitions
```

## Test Categories (98 tests)

| Category | Tests | Description |
|----------|-------|-------------|
| 1. SDK Patterns | 1-8 | Sessions, traces, subagents, cost, tier-gated tools |
| 2. Skill Validation | 9-15 | 7 specialist agents + supervisor multi-skill chain |
| 3. AWS Tools | 16-20 | S3, DynamoDB, CloudWatch, doc gen, E2E verification |
| 4. UC Workflows | 21-27 | Use case workflow queries (UC-02 through UC-09) |
| 5. SDK Architecture | 28-34 | Skill-subagent orchestration, admin, workspace, CRUD |
| 6. Compliance Matrix | 35-48 | Requirements matrix + FAR/tool chain validation |
| 7. Langfuse + CW | 49-55 | Trace validation, token counts, CloudWatch events |
| 8. Context Loss | 56-60, 77-82 | KB integration, prompt truncation, empty responses |
| 9. Handoff | 83-87 | Cross-agent context propagation, synthesis |
| 10. State + Budget | 88-98 | Session persistence, concurrent isolation, prompt size |

## Self-Improvement Loop

The eval expert now has a closed-loop self-improvement capability:

```
DIAGNOSE  ->  Classify failures by root cause (ROUTING/PROMPT/TOOL/TRUNCATION/DATA/BUDGET)
PRIORITIZE -> Rank fixes by impact (tests unblocked) and risk (change scope)
FIX       ->  Edit agent prompts, skill workflows, supervisor routing, or context budget
VALIDATE  ->  Re-run affected tests to confirm fixes work
RECORD    ->  Update expertise.md with learnings
```

### 5 Improvement Levers

| # | Lever | Files |
|---|-------|-------|
| 1 | Agent prompts | `eagle-plugin/agents/*/agent.md` |
| 2 | Skill workflows | `eagle-plugin/skills/*/SKILL.md` |
| 3 | Supervisor routing | `eagle-plugin/agents/supervisor/agent.md` |
| 4 | Trigger patterns | YAML frontmatter in agent/skill files |
| 5 | Context budget | `MAX_SKILL_PROMPT_CHARS` in strands_agentic_service.py |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Run eval suite, diagnose failures, apply fixes
LEARN  ->  Record which levers worked for which root causes
REUSE  ->  Apply proven fix patterns to new failures
```
