---
type: expert-file
file-type: index
domain: test
tags: [expert, test, pytest, playwright, smoke, performance, cache, fast-path, regression]
---

# Test Expert

> EAGLE test suite specialist for pytest unit tests, Playwright E2E tests, smoke tests, performance validation, cache behavior, and regression testing.

## Domain Scope

This expert covers:
- **Pytest Unit Tests** - `server/tests/test_*.py` (9 active files, ~50 tests)
- **Playwright E2E Tests** - `client/tests/*.spec.ts` (11 spec files, ~40 tests)
- **Performance Tests** - `test_perf_simple_message.py` (cache, async, fast-path)
- **Smoke Tests** - Fast-path regex, fire-and-forget writes, parallel reads, endpoint health
- **Eval Suite** - `test_strands_eval.py` (38 tests across 7 tiers, Bedrock-backed)
- **Test Patterns** - Mocking (unittest.mock), async (pytest-asyncio), fixtures, conftest

## Available Commands

| Command | Purpose |
|---------|---------|
| `/experts:test:question` | Answer test suite questions without coding |
| `/experts:test:plan` | Plan new tests or test changes |
| `/experts:test:add-test` | Scaffold and register a new pytest test file |
| `/experts:test:self-improve` | Update expertise after test runs |
| `/experts:test:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:test:maintenance` | Run test suites and report results |
| `/experts:test:use-case-builder` | Build tests across all 4 suites for a UC |
| `/experts:test:status` | Quick test inventory count (no execution) |

## Key Files

| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model for test domain |
| `question.md` | Query command for read-only questions |
| `plan.md` | Planning command for new tests |
| `add-test.md` | Add test command (scaffold + validate) |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Run tests and report results |
| `use-case-builder.md` | Build tests across all 4 suites for a UC |

## Architecture

```
server/tests/
  |-- test_perf_simple_message.py     # 10 tests — cache, async, prompt, reload
  |-- test_chat_endpoints.py          # ~15 tests — REST vs SSE, auth, schema
  |-- test_document_pipeline.py       # ~12 tests — doc gen, export, SSE metadata
  |-- test_strands_eval.py            # 38 tests — full eval suite (Bedrock)
  |-- test_strands_poc.py             # 1 test — Strands SDK POC
  |-- test_strands_multi_agent.py     # 3 tests — supervisor routing
  |-- test_strands_service_integration.py  # 2 tests — sdk_query adapters
  |-- test_bedrock_hello.py           # 4 tests — direct Bedrock invocation
  |-- test_bedrock_tools.py           # 1 test — inline agent with tools

client/tests/
  |-- chat.spec.ts                    # Chat UI structure + streaming
  |-- intake.spec.ts                  # Home page + backend connectivity
  |-- admin-dashboard.spec.ts         # Dashboard metrics + health
  |-- navigation.spec.ts              # Branding + feature cards
  |-- documents.spec.ts               # Doc list + filters
  |-- document-pipeline.spec.ts       # Doc viewer + generation E2E
  |-- session-memory.spec.ts          # Multi-turn context retention
  |-- workflows.spec.ts               # Acquisition packages UI
  |-- uc-intake.spec.ts               # UC intake workflow E2E
  |-- uc-document.spec.ts             # SOW generation E2E
  |-- uc-far-search.spec.ts           # FAR search E2E

Config:
  |-- server/pytest.ini               # asyncio_mode = auto
  |-- client/playwright.config.ts     # Chromium + Firefox + WebKit + Mobile
  |-- client/tests/global-setup.ts    # Cognito login (shared auth state)
```

## Test Categories

| Category | Framework | AWS Needed | LLM Cost | Speed |
|----------|-----------|------------|----------|-------|
| Unit (mocked) | pytest | No | $0 | <10s |
| Performance | pytest | Partial | $0 | <10s |
| Smoke | pytest | Yes | $0-0.05 | <30s |
| Integration | pytest | Yes | $0.10-0.50 | 1-5min |
| Eval Suite | pytest (custom CLI) | Yes | ~$0.50 | 5-15min |
| E2E Frontend | Playwright | Yes (backend) | $0.10+ | 1-5min |

## ACT-LEARN-REUSE Pattern

```
ACT    ->  Add/modify tests, run suites, validate coverage
LEARN  ->  Update expertise.md with patterns and failures
REUSE  ->  Apply patterns to future test development
```
