# New EAGLE Jira Items — 2026-03-02

> Prepared for sprint planning. Covers Strands SDK migration (completed today),
> follow-up work, infrastructure gaps found during eval, and next-phase work.

---

## Completed Stories (Done 2026-03-02)

### EAGLE-49: Migrate EAGLE from Claude Agent SDK to Strands Agents SDK
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Full migration from Claude Agent SDK to Strands Agents SDK — plan, build, wire, cleanup
- **Status**: Done
- **Assignee**: `assignee:greg`
- **Expert Domain**: `strands-sdk`, `backend`
- **PR**: [CBIIT/sm_eagle#5](https://github.com/CBIIT/sm_eagle/pull/5) (`feat/strands-migration`)
- **Commits**: `48395e9`, `ea8d316`, `ae222ee`
- **Plan**: `.claude/specs/20260302-183000-plan-strands-full-migration-v1.md` (5-phase plan, all phases complete)
- **Architecture Report**: `docs/development/20260302-140000-report-claude-sdk-vs-strands-v1.md`
- **POC Spec**: `.claude/specs/20260302-160000-plan-strands-poc-v1.md`
- **Description**: Executed the full 5-phase migration plan to replace Claude Agent SDK with Strands Agents SDK. Phase 1: created Strands expert system and validated 3 Bedrock models via POC (Nova Pro 5/5, Llama 4 4/5, DeepSeek R1 5/5). Phase 2: built `strands_agentic_service.py` (490 lines) as drop-in replacement with identical API (`sdk_query`, `sdk_query_single_skill`, `build_skill_tools`, `build_supervisor_prompt`). Uses shared module-level `BedrockModel`, per-request `Agent()` construction, `@tool`-wrapped subagents (agents-as-tools pattern), and adapter dataclasses matching the Claude SDK message interface. Phase 3: wired into `streaming_routes.py` and `main.py` — callers unchanged. Phase 5: removed `claude-agent-sdk` from requirements, archived old test files, updated CLAUDE.md.
- **Acceptance Criteria**:
  - [x] `strands_agentic_service.py` exports same API as `sdk_agentic_service.py`
  - [x] Shared `BedrockModel` at module level (no per-request boto3 overhead)
  - [x] `@tool`-wrapped subagent factory with 4-layer prompt resolution (wspc → plugin → bundled → tenant)
  - [x] `streaming_routes.py` and `main.py` consume Strands adapter messages unchanged
  - [x] `claude-agent-sdk` removed from requirements; old tests archived
  - [x] Integration test passes (`test_strands_service_integration.py`)

### EAGLE-50: Port & Validate 28-Test Eval Suite on Strands — 26/28 Pass
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Port eval suite to Strands, fix tool tracking bug, run full 28-test validation — 26/28 pass
- **Status**: Done
- **Assignee**: `assignee:greg`
- **Expert Domain**: `strands-sdk`, `eval`
- **PR**: [CBIIT/sm_eagle#5](https://github.com/CBIIT/sm_eagle/pull/5) (`feat/strands-migration`)
- **Commits**: `ae222ee`, `8d91f87`
- **Plan**: `.claude/specs/20260302-183000-plan-strands-full-migration-v1.md` — Phase 4
- **Description**: Ported all 28 tests from `test_eagle_sdk_eval.py` to `test_strands_eval.py` (2858 lines). Replaced `TraceCollector` with `StrandsResultCollector`, replaced `ClaudeAgentOptions` + `query()` with `Agent()` + direct invocation. During validation, discovered that Strands `AgentResult.messages` is empty — tool call history lives in `result.metrics.tool_metrics` (EventLoopMetrics) using Bedrock camelCase `toolUse` format (not Anthropic `tool_use`). Fixed both the eval collector and the production `strands_agentic_service.sdk_query()`. Full suite result on Nova Pro v1: 26/28 pass. 2 failures are pre-existing S3 bucket env config (tests 16, 19 — not Strands-related). All skill validations 5/5, supervisor multi-skill chain 5/5, all 7 UC workflows pass. CloudWatch telemetry: 29 events emitted, 81 metrics published, results archived to S3.
- **Acceptance Criteria**:
  - [x] All 28 test functions ported with Strands patterns (same numbering for CloudWatch compatibility)
  - [x] `StrandsResultCollector` extracts tool use from `metrics.tool_metrics` (not empty `result.messages`)
  - [x] Production fix: `sdk_query()` tool extraction uses metrics
  - [x] Full suite: 26/28 pass — 2 failures are pre-existing S3 config, not Strands
  - [x] All 6 skill validations score 5/5 indicators
  - [x] CloudWatch telemetry emitted and results archived to S3

---

## Updates to Existing Issues

### EAGLE-32: Risk-Trigger-Based Specialist Agent Routing
- **Update label**: `claude-sdk` → `strands-sdk`
- **Note**: Routing is now implemented via `@tool`-wrapped subagents in `strands_agentic_service.py`. Risk triggers can be added as additional `@tool` functions or as routing logic in the supervisor prompt.

### EAGLE-36: CO Session Handoff — Fork or Transfer Acquisition Chat
- **Update label**: `claude-sdk` → `strands-sdk`
- **Note**: Session persistence is a Strands follow-up (see new EAGLE-42 below). Once session manager is in place, handoff becomes a session metadata operation.

---

## New Epic

### [NEW EPIC] Strands Agents SDK Migration & Stabilization
- **Type**: Epic
- **Summary**: Strands Agents SDK Migration & Stabilization
- **Description**: Migrate EAGLE from Claude Agent SDK to Strands Agents SDK. Covers core migration (complete), session persistence, health check cleanup, S3 tool env fix, EC2 runner validation, and AgentCore evaluation.
- **Status**: In Progress
- **Assignee**: `assignee:greg`

---

## New Stories

### EAGLE-42: Strands Session Persistence with DynamoDB SessionManager
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Implement session persistence for Strands agents using custom DynamoDB SessionManager
- **Description**: Currently Strands agents are stateless (fresh Agent() per request). Implement a custom `DynamoDBSessionManager` that stores conversation history in the existing eagle DynamoDB table using the `SESSION#` prefix pattern. Wire it into `sdk_query()` so multi-turn conversations resume context. Must preserve multi-tenant isolation (tenant_id in PK).
- **Expert Domain**: `strands-sdk`, `backend`
- **Assignee**: `assignee:greg`
- **Acceptance Criteria**:
  - [ ] Custom SessionManager class implements Strands `SessionManager` interface
  - [ ] Conversation history stored in DynamoDB `SESSION#{tenant}-{user}-{session_id}`
  - [ ] `sdk_query()` accepts `session_id` and loads prior context
  - [ ] Eval test 2 (session resume) upgraded from simulated to real persistence
  - [ ] Multi-tenant isolation verified (tenant A cannot read tenant B sessions)

### EAGLE-43: Fix S3 Document Tool Bucket Configuration
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Fix S3 bucket env var for document tools — eval tests 16 & 19 failing
- **Description**: Eval tests 16 (S3 Document Operations) and 19 (Document Generation) fail because `S3_BUCKET` environment variable is empty when running tests locally. The `execute_tool()` handler in `agentic_service.py` reads `os.environ.get("S3_BUCKET", "")` which returns empty string. Need to either (a) add `S3_BUCKET` to test env setup, or (b) have `execute_tool` fall back to the documented bucket name from config. Documents generate correctly — only S3 write/confirm fails.
- **Expert Domain**: `backend`, `eval`
- **Assignee**: `assignee:greg`
- **Acceptance Criteria**:
  - [ ] `S3_BUCKET` resolved from config or env in test context
  - [ ] Eval tests 16 and 19 pass (28/28 green)
  - [ ] No hardcoded bucket names — use config-driven resolution

### EAGLE-44: Remove Legacy agentic_service.py Health Check Dependency
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Move MODEL and EAGLE_TOOLS exports from legacy agentic_service.py to strands_agentic_service.py
- **Description**: `streaming_routes.py` and `main.py` still import `MODEL` and `EAGLE_TOOLS` from the legacy `agentic_service.py` for the health check endpoint. This prevents full removal of the old file. Move these exports to `strands_agentic_service.py` or a shared `config.py`, then update imports. The `execute_tool()` function also lives in `agentic_service.py` — evaluate whether to extract it to a standalone module.
- **Expert Domain**: `backend`, `strands-sdk`
- **Assignee**: `assignee:greg`
- **Acceptance Criteria**:
  - [ ] Health check endpoint imports from strands module or shared config
  - [ ] `agentic_service.py` can be fully archived (no active imports)
  - [ ] `execute_tool()` moved to standalone module or kept in a clearly-labeled utility file
  - [ ] All 28 eval tests still pass

### EAGLE-45: Validate Strands Eval Suite on EC2 Runner
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Run full 28-test Strands eval suite on EC2 runner (eagle-runner-dev) and publish results
- **Description**: The eval suite has been validated locally (26/28 pass). Need to deploy the latest code to the EC2 runner via git bundle, install `strands-agents`, and run the full suite. Validate that CloudWatch telemetry flows correctly from EC2 and that results match local. The EC2 runner uses IAM instance role (not SSO) so credential handling differs.
- **Expert Domain**: `eval`, `deployment`
- **Assignee**: `assignee:greg`
- **Acceptance Criteria**:
  - [ ] Code deployed to EC2 via git bundle
  - [ ] `strands-agents` pip installed on EC2 (Python 3.12)
  - [ ] Full 28-test suite runs to completion
  - [ ] CloudWatch telemetry emitted from EC2 matches local format
  - [ ] Results archived to S3

### EAGLE-46: Strands SSE Streaming via stream_async() and CallbackHandler
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Replace sync Agent() call with stream_async() for real-time SSE token streaming
- **Description**: Currently `sdk_query()` makes a synchronous `supervisor(prompt)` call and yields the full response as a single AssistantMessage. This means the frontend gets the entire response at once (no token-by-token streaming). Implement Strands `stream_async()` with a custom `CallbackHandler` that emits SSE events as tokens arrive. This will restore the real-time typing effect the frontend had with the Claude SDK streaming path.
- **Expert Domain**: `strands-sdk`, `backend`, `frontend`
- **Assignee**: `assignee:greg`
- **Acceptance Criteria**:
  - [ ] `sdk_query()` uses `agent.stream_async()` instead of `agent(prompt)`
  - [ ] Custom `CallbackHandler` converts token events to SSE via `MultiAgentStreamWriter`
  - [ ] Frontend receives incremental text updates (visible typing effect)
  - [ ] Tool use events streamed in real-time (not batched at end)
  - [ ] Error handling preserves current behavior (ERROR SSE event on failure)

### EAGLE-47: Evaluate Bedrock AgentCore for Phase 6 Deployment
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Evaluate Amazon Bedrock AgentCore as managed runtime for EAGLE agent deployment
- **Description**: AgentCore provides serverless agent runtime with per-session microVMs, I/O-aware billing, built-in session management, and auto-scaling. Evaluate whether AgentCore adds value over current ECS Fargate deployment. Key questions: (1) Do NCI IAM SCP constraints allow AgentCore roles? (2) Does I/O-aware billing reduce costs vs always-on Fargate? (3) Can built-in session management replace our custom DynamoDB SessionManager? (4) Does code interpreter sandbox benefit our document generation use case? Plan documented in `.claude/specs/20260302-191000-plan-bedrock-agentcore-phase6-v1.md`.
- **Expert Domain**: `aws`, `strands-sdk`, `deployment`
- **Assignee**: `assignee:greg`
- **Acceptance Criteria**:
  - [ ] AgentCore spike tested in NCI sandbox account
  - [ ] IAM/SCP compatibility verified
  - [ ] Cost comparison: AgentCore vs ECS Fargate for EAGLE workload
  - [ ] Go/no-go decision documented

### EAGLE-48: Frontend SSE Integration Test with Strands Backend
- **Type**: Story
- **Epic**: Strands Agents SDK Migration & Stabilization
- **Summary**: Validate frontend chat interface works end-to-end with Strands streaming backend
- **Description**: With the backend now running Strands instead of Claude SDK, verify the full SSE streaming pipeline works: frontend sends POST `/api/chat/stream` → `streaming_routes.py` → `sdk_query()` → Strands Agent → adapter messages → SSE events → frontend renders. Test with the chat interface on localhost. Verify agent selection, tool use indicators, and cost ticker all render correctly.
- **Expert Domain**: `frontend`, `backend`
- **Assignee**: `assignee:fullstack`
- **Acceptance Criteria**:
  - [ ] Chat messages flow through Strands backend and render in frontend
  - [ ] Tool use events display in agent trace panel
  - [ ] Multi-agent delegation visible (supervisor → specialist)
  - [ ] Error states handled gracefully (SSE ERROR event → UI notification)
  - [ ] Playwright smoke test passes

---

## Summary

### Completed Today (2026-03-02)

| Key | Summary | Status | PR / Commits |
|-----|---------|--------|--------------|
| EAGLE-49 | Migrate EAGLE from Claude Agent SDK to Strands Agents SDK | Done | [PR #5](https://github.com/CBIIT/sm_eagle/pull/5) · `48395e9` `ea8d316` `ae222ee` |
| EAGLE-50 | Port & validate 28-test eval suite on Strands — 26/28 pass | Done | [PR #5](https://github.com/CBIIT/sm_eagle/pull/5) · `ae222ee` `8d91f87` |

### Open — Priority Order

| Priority | Key | Summary | Effort |
|----------|-----|---------|--------|
| P1 | EAGLE-43 | Fix S3 bucket env for eval tests 16 & 19 | S |
| P1 | EAGLE-44 | Remove legacy health check dependency | M |
| P2 | EAGLE-42 | Session persistence with DynamoDB | L |
| P2 | EAGLE-46 | SSE streaming via stream_async() | L |
| P2 | EAGLE-45 | Validate eval on EC2 runner | M |
| P2 | EAGLE-48 | Frontend SSE integration test | M |
| P3 | EAGLE-47 | Evaluate Bedrock AgentCore (Phase 6) | L |

**S** = small (< 1 day), **M** = medium (1-2 days), **L** = large (3-5 days)
