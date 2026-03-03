# Bedrock AgentCore Phase 6 Plan: Post-Migration Adoption

## Overview

- **Integration Type**: Future Phase (after Strands migration completes)
- **Prerequisite**: Phases 1-5 of Strands full migration (`20260302-183000-plan-strands-full-migration-v1.md`)
- **Constraint**: No Claude/Anthropic models — AgentCore supports any Bedrock model
- **Decision**: Adopt AgentCore AFTER Strands migration stabilizes, not during

---

## What Is Amazon Bedrock AgentCore?

AgentCore is a **managed runtime infrastructure layer** for deploying AI agents. It sits BETWEEN the Strands SDK (orchestration logic) and raw AWS compute (ECS/Lambda):

```
┌─────────────────────────────────────────┐
│  Strands Agents SDK (orchestration)     │  ← Agent logic, @tool, multi-agent
├─────────────────────────────────────────┤
│  Bedrock AgentCore (runtime)            │  ← Session isolation, memory, scaling
├─────────────────────────────────────────┤
│  AWS Compute (ECS/Lambda/AgentCore VM)  │  ← Infrastructure
└─────────────────────────────────────────┘
```

**Key capabilities**:
- **Serverless agent runtime** — per-session microVMs with built-in isolation
- **I/O-aware billing** — pay only during active LLM/tool execution, not idle wait
- **Session management** — built-in multi-turn memory without custom DynamoDB code
- **Code interpreter** — sandboxed Python/JS execution per session
- **Auto-scaling** — scale-to-zero when no requests, burst on demand
- **Observability** — built-in tracing and metrics (CloudWatch integration)
- **Identity passthrough** — IAM role per session for tenant isolation

---

## Why NOT Now (During Migration)

| Concern | Detail |
|---------|--------|
| **Scope creep** | Adding AgentCore during Strands migration doubles the blast radius |
| **NCI SCP constraints** | `iam:CreateRole` restrictions may block AgentCore's IAM requirements; need to test in sandbox first |
| **ECS Fargate works** | Current infrastructure is deployed and functional (5 stacks, all `CREATE_COMPLETE`) |
| **Strands migration is the priority** | Phase 1-5 plan is well-defined; adding AgentCore creates dependencies |
| **GA maturity** | AgentCore launched mid-2025; give it time to stabilize before production adoption |
| **Learning curve** | Team should master Strands patterns first, then layer on AgentCore |

---

## Why Later (Phase 6)

| Benefit | EAGLE Impact |
|---------|-------------|
| **Cost reduction** | I/O-aware billing — stop paying for idle ECS tasks during agent "think" time. EAGLE agents spend ~70% of wall time waiting on Bedrock `ConverseStream` responses |
| **Session isolation** | Per-session microVMs replace our custom `DynamoDBSessionManager`. Each tenant session gets its own isolated runtime — better security for government use |
| **Scale-to-zero** | Dev/staging environments cost $0 when idle (currently ECS Fargate charges for `desiredCount: 1` 24/7) |
| **Built-in memory** | AgentCore's session management replaces manual DynamoDB `SESSION#`/`MSG#` CRUD in `session_store.py` |
| **Code interpreter** | Future EAGLE skills (document analysis, data processing) can use sandboxed execution without custom Lambda |
| **Observability** | Built-in tracing replaces our custom CloudWatch emission pipeline for agent-level metrics |
| **Identity passthrough** | IAM role per session maps cleanly to EAGLE's multi-tenant model (tenant → role → resource access) |

---

## Migration Path: ECS Fargate → AgentCore

### Phase 6a: Sandbox Validation

**Goal**: Prove AgentCore works within NCI account constraints.

```bash
# Test AgentCore API access
AWS_PROFILE=eagle aws bedrock-agent-runtime list-agents --region us-east-1

# Check for SCP blocks
AWS_PROFILE=eagle aws bedrock-agent-runtime create-agent \
  --agent-name eagle-sandbox-test \
  --foundation-model us.amazon.nova-pro-v1:0 \
  --instruction "Test agent" \
  --region us-east-1
```

**Validation**:
- [ ] AgentCore API is accessible from NCI account
- [ ] Agent creation is not blocked by SCPs
- [ ] IAM role creation for AgentCore is within `power-user-*` boundary
- [ ] Network connectivity works through NCI VPC

### Phase 6b: Single-Skill AgentCore POC

**Goal**: Deploy one EAGLE skill (oa-intake) on AgentCore and verify it works.

```python
# agentcore_poc.py
import boto3

bedrock_agent = boto3.client("bedrock-agent-runtime", region_name="us-east-1")

# Deploy Strands agent as AgentCore-hosted agent
# Uses same Agent() code but deployed to AgentCore runtime
response = bedrock_agent.invoke_agent(
    agentId="<poc-agent-id>",
    agentAliasId="TSTALIASID",
    sessionId="poc-session-001",
    inputText="I need to buy $13,800 in lab supplies via purchase card",
)
```

**Pass criteria**: Same 3/5 indicator threshold as `test_strands_poc.py`.

### Phase 6c: Multi-Agent AgentCore Migration

**Goal**: Move the full supervisor + subagent topology to AgentCore.

**Approach**:
1. Deploy each skill agent as an AgentCore agent
2. Supervisor uses AgentCore's built-in agent collaboration (or Strands agents-as-tools calling AgentCore-hosted subagents)
3. Session management switches from DynamoDB CRUD to AgentCore sessions
4. Streaming switches from SSE + FastAPI to AgentCore's streaming response

### Phase 6d: ECS Fargate Decommission

**Goal**: Remove ECS Fargate backend, replace with AgentCore-hosted agents.

**Changes**:
- `compute-stack.ts` → remove ECS service for backend
- `streaming_routes.py` → adapt to AgentCore streaming API
- `session_store.py` → simplify (AgentCore handles session persistence)
- `cost_attribution.py` → adapt to AgentCore billing metrics

---

## Cost Comparison (Estimated)

| Component | ECS Fargate (Current) | AgentCore (Phase 6) |
|-----------|----------------------|---------------------|
| Compute (idle) | ~$30/mo (t3.micro equiv, 24/7) | $0 (scale-to-zero) |
| Compute (active) | Same as idle | ~$0.015/min active |
| DynamoDB sessions | ~$5/mo | $0 (built-in) |
| CloudWatch custom | ~$3/mo | Reduced (built-in) |
| **Dev/staging total** | **~$38/mo** | **~$5-10/mo** |

*Note: AgentCore pricing is I/O-aware — you only pay during active LLM calls and tool execution, not during idle wait between user messages.*

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| NCI SCPs block AgentCore | Phase 6a sandbox test before any production plans |
| AgentCore API changes (pre-GA stability) | Pin SDK versions; maintain ECS Fargate as fallback |
| Multi-tenant isolation differs from current model | Test IAM role passthrough with NCI's permission boundary |
| Streaming protocol incompatible with current SSE | Adapt `streaming_routes.py` or use API Gateway WebSocket |
| Session format migration (DynamoDB → AgentCore) | One-time migration script; keep DynamoDB as read-only archive |

---

## Prerequisites

- [ ] Strands migration Phases 1-5 complete and stable
- [ ] AgentCore API accessible from NCI account (SCP check)
- [ ] Team familiar with Strands patterns (multi-agent, @tool, streaming)
- [ ] Dev environment cost baseline established for comparison
- [ ] AgentCore pricing confirmed for government accounts

---

## Validation Commands

```bash
# Phase 6a: SCP check
AWS_PROFILE=eagle aws bedrock-agent-runtime list-agents --region us-east-1

# Phase 6b: POC test
AWS_PROFILE=eagle python -m pytest tests/test_agentcore_poc.py -v -s

# Phase 6c: Multi-agent test
AWS_PROFILE=eagle python -m pytest tests/test_agentcore_multi_agent.py -v -s

# Phase 6d: Verify ECS decommissioned
aws ecs describe-services --cluster eagle-dev --services eagle-backend-dev --query 'services[0].desiredCount'
# Should return 0 or service not found
```

---

## Decision Timeline

| Milestone | When | Action |
|-----------|------|--------|
| Strands Phase 5 complete | +2-3 weeks | Begin Phase 6a sandbox validation |
| SCP validation passes | +1 week after 6a | Begin Phase 6b single-skill POC |
| POC passes | +1 week after 6b | Decide go/no-go on full migration |
| Full migration | +2-3 weeks after decision | Phase 6c + 6d |

**Total estimated timeline**: 6-8 weeks after Strands migration completes.
