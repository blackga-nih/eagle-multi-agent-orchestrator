# Plan D: OpenClaw-Inspired Backend Architecture (Backup)

> Backup alternative to Option C (Claude SDK as orchestration layer). OpenClaw patterns for session management, memory, and context compaction. Reference only - not currently implementing.

## Why This Exists

During Option C research, we evaluated OpenClaw's architecture for its mature session management, semantic memory, and context compaction patterns. While Option C (Claude SDK + `query(resume=session_id)`) is the primary implementation path, OpenClaw's patterns are worth preserving as a backup for when we need:

- **Context compaction** when sessions exceed token limits
- **Semantic memory** across sessions (not just within)
- **Message tree structures** for branching conversations

## Source Documentation

### Primary Docs
- **Getting Started**: https://docs.openclaw.ai/start/getting-started
- **Sessions**: https://docs.openclaw.ai/cli/sessions
- **Memory**: https://docs.openclaw.ai/cli/memory

### Architecture References
- **Session Model**: https://docs.openclaw.ai/concepts/session.md
- **Session Compaction**: https://docs.openclaw.ai/reference/session-management-compaction.md
- **Architecture**: https://docs.openclaw.ai/concepts/architecture.md
- **Memory System**: https://docs.openclaw.ai/concepts/memory.md
- **Agent Loop**: https://docs.openclaw.ai/concepts/agent-loop.md
- **Messages**: https://docs.openclaw.ai/concepts/messages.md

### Source Code
- **Repository**: https://github.com/openclaw/openclaw
- **License**: Open source (check repo for specific license)

## Key Architecture Patterns

### 1. Gateway-Based Session Routing

OpenClaw uses a single daemon process (Gateway) that routes messages to session workers by key pattern:

```
Client Request
  │
  ▼
┌─────────────────────────────────────────────┐
│ Gateway (Single Daemon)                      │
│                                              │
│ Session Key: agent:<id>:<channel>:group:<gid>│
│                                              │
│ Routing:                                     │
│   key → existing worker (if alive)           │
│   key → new worker (if first message)        │
│   key → restore from JSONL (if evicted)      │
└──────────────┬──────────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Worker A   Worker B   Worker C
 (session1) (session2) (session3)
```

**Multi-tenant adaptation**: Replace `agent:<id>:<channel>` with `tenant:<id>:user:<uid>:session:<sid>`. The gateway pattern naturally isolates tenants - each session key maps to exactly one worker.

### 2. JSONL Transcript with Tree Structure

Messages stored as append-only JSONL with tree relationships:

```jsonl
{"id": "msg_001", "parentId": null, "role": "user", "content": "Hello"}
{"id": "msg_002", "parentId": "msg_001", "role": "assistant", "content": "Hi!"}
{"id": "msg_003", "parentId": "msg_002", "role": "user", "content": "Tell me about..."}
{"id": "msg_004", "parentId": "msg_001", "role": "user", "content": "Actually, different question"}
```

The `parentId` field creates a tree - `msg_004` branches from `msg_001`, creating a fork. The active conversation is the path from root to current leaf. This enables:
- **Branching**: User can go back and explore different conversation paths
- **Efficient storage**: Only append, never rewrite
- **Replay**: Walk the tree to reconstruct any conversation path

**Multi-tenant adaptation**: Store JSONL in DynamoDB (tenant-scoped) or S3 (`s3://bucket/tenants/{tenant_id}/sessions/{session_id}.jsonl`).

### 3. Three-Layer Context Management

OpenClaw manages context windows with three progressive strategies:

```
Full Context (fits in window)
  │
  │ When context exceeds ~80% of window:
  ▼
┌──────────────────────────────────────┐
│ Layer 1: TRIM                         │
│                                       │
│ Remove old tool results (keep calls)  │
│ Truncate long text blocks             │
│ Keep system prompt + recent messages  │
│                                       │
│ Cost: Zero (just filtering)           │
└──────────────┬───────────────────────┘
               │
               │ If still too large:
               ▼
┌──────────────────────────────────────┐
│ Layer 2: MEMORY FLUSH                 │
│                                       │
│ Extract key facts from old messages   │
│ Write to daily .md memory log         │
│ Remove flushed messages from context  │
│ Inject memory summary at top          │
│                                       │
│ Cost: One LLM call for extraction     │
└──────────────┬───────────────────────┘
               │
               │ If memory logs grow large:
               ▼
┌──────────────────────────────────────┐
│ Layer 3: COMPACTION                   │
│                                       │
│ Summarize entire conversation so far  │
│ Replace all messages with summary     │
│ Keep only: summary + last N messages  │
│ Write compaction checkpoint to JSONL  │
│                                       │
│ Cost: One LLM call for summarization  │
└──────────────────────────────────────┘
```

**Multi-tenant adaptation**: Compaction budgets differ by tier:
- Basic: Trim only (no LLM calls for memory)
- Advanced: Trim + Memory flush
- Premium: Full three-layer with long-term memory

### 4. Semantic Memory System

OpenClaw maintains memory across sessions using:

```
Per-Session Memory:
  └─ daily .md log files (auto-generated from memory flush)
     - 2026-02-03.md: "User discussed product catalog integration"
     - 2026-02-02.md: "User set up Bedrock agent with premium tier"

Cross-Session Memory:
  └─ MEMORY.md (curated, persistent)
     "## User Preferences
      - Prefers concise responses
      - Works on multi-tenant SaaS platform
      ## Key Decisions
      - Using Claude SDK over Bedrock Agent API
      - Premium tier has $0.50/query budget"

Search Index:
  └─ SQLite + sqlite-vec
     - BM25 keyword search
     - Vector similarity search (embeddings)
     - Hybrid: BM25 + vector, re-ranked
```

**Multi-tenant adaptation**:
- Replace file-based storage with DynamoDB (per-tenant partition)
- Replace SQLite with pgvector (already in our stack)
- Memory isolation: each tenant's memory is fully partitioned
- Tier-gated: only premium gets cross-session memory

### 5. dmScope Control

OpenClaw uses `dmScope` to control which messages are visible to which channel:

```
dmScope: "inner"  → Only visible within the current agent/subagent
dmScope: "outer"  → Visible to parent orchestrator
dmScope: "all"    → Visible everywhere
```

**Multi-tenant adaptation**: Maps to our tenant isolation - subagent messages scoped to the session, admin can see all scopes.

## Comparison Matrix

| Feature | OpenClaw | Claude SDK (Option C) | ChatGPT |
|---|---|---|---|
| Session persistence | JSONL files (tree) | `~/.claude/projects/*.jsonl` | Server-side DB |
| Multi-turn | Gateway worker pool | `query(resume=session_id)` | Stateless + DB |
| Context management | 3-layer (trim/flush/compact) | SDK auto-manages | Proprietary |
| Memory across sessions | Daily .md + MEMORY.md + SQLite-vec | None (Issue #109) | Proprietary |
| Branching | Tree structure (parentId) | `fork_session=True` | Not supported |
| Scaling model | Single daemon + workers | Stateless per-query | Distributed |
| Multi-tenant | Not designed for it | App-layer isolation | Built-in |
| Language | TypeScript/Node.js | Python (SDK wrapper) | N/A |

## When to Activate Plan D

Migrate to OpenClaw-inspired patterns if:

1. **Session context exceeds token limits** - SDK has no built-in compaction. If conversations regularly exceed 200K context, implement Layer 1-3 compaction.

2. **Cross-session memory needed** - SDK sessions are isolated. If users need "remember my preferences across sessions," implement pgvector memory store.

3. **Conversation branching requested** - SDK's `fork_session` is binary (fork or don't). If users need to explore multiple paths, implement tree-structured message storage.

4. **Session restore latency** - If `query(resume=session_id)` becomes slow with large JSONL transcripts, implement compaction checkpoints.

## Incremental Adoption Path

Don't wholesale adopt OpenClaw. Cherry-pick patterns incrementally:

```
Phase 1 (Current): Option C - Claude SDK query(resume=session_id)
  ├─ Stateless between turns
  ├─ SDK manages session files
  └─ Simple, proven, works today

Phase 2 (When needed): DynamoDB Message Mirror
  ├─ On each SDK message, also write to DynamoDB
  ├─ Enables: chat history API, search, analytics
  ├─ Pattern: OpenClaw's JSONL but in DynamoDB
  └─ Trigger: When GET /api/sessions/{id}/messages needed

Phase 3 (When needed): Context Compaction
  ├─ Implement trim layer (free - just filter old tool results)
  ├─ Implement memory flush (one LLM call to extract facts)
  ├─ Store compaction checkpoints
  └─ Trigger: When sessions regularly exceed 100K tokens

Phase 4 (When needed): pgvector Cross-Session Memory
  ├─ Store extracted facts with embeddings
  ├─ Hybrid BM25 + vector search on conversation start
  ├─ Inject relevant memories into system_prompt
  └─ Trigger: When users need "remember across sessions"
```

## Architecture Diagram (Full Plan D)

```
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND (Vue 3)                                                    │
│  Same as Option C - no frontend changes for Plan D                   │
└────────────────────────────┬────────────────────────────────────────┘
                             │ WebSocket
┌────────────────────────────┴────────────────────────────────────────┐
│  BACKEND (FastAPI)                                                   │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  SDK Orchestrator (same as Option C)                           │ │
│  │  query(prompt, options=ClaudeAgentOptions(resume=session_id))  │ │
│  └───────────┬────────────────────────────────────────────────────┘ │
│              │                                                       │
│  ┌───────────▼────────────────────────────────────────────────────┐ │
│  │  Message Mirror (Plan D addition)                              │ │
│  │  On each SDK message → write to DynamoDB                       │ │
│  │  {tenant_id, session_id, msg_id, parent_id, role, content}     │ │
│  └───────────┬────────────────────────────────────────────────────┘ │
│              │                                                       │
│  ┌───────────▼────────────────────────────────────────────────────┐ │
│  │  Context Manager (Plan D addition)                             │ │
│  │                                                                │ │
│  │  Pre-query:                                                    │ │
│  │    1. Count tokens in session transcript                       │ │
│  │    2. If > threshold: run compaction                           │ │
│  │    3. Inject memory summary into system_prompt                 │ │
│  │                                                                │ │
│  │  Post-query:                                                   │ │
│  │    1. Extract facts from new messages (memory flush)           │ │
│  │    2. Store in pgvector with embeddings                        │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  pgvector Memory Store                                         │ │
│  │                                                                │ │
│  │  Table: tenant_memories                                        │ │
│  │    tenant_id, user_id, fact_text, embedding vector(1536),      │ │
│  │    source_session_id, created_at, memory_type                  │ │
│  │                                                                │ │
│  │  Search: hybrid BM25 + cosine similarity                      │ │
│  │  Partition: by tenant_id (full isolation)                      │ │
│  └────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

## Integration Analysis: OpenClaw as Backend

### What OpenClaw Replaces

OpenClaw is an open-source TypeScript/Node.js gateway and agent runtime (MIT License, 145K+ GitHub stars). Originally released as Clawdbot (Nov 2025), renamed Moltbot, then OpenClaw (Jan 2026). It operates as a single daemon process that manages sessions, routes messages, and executes agent workflows. In this integration, OpenClaw's gateway would replace our custom `agentic_service.py` (Bedrock Agent API Layer 2) and potentially the SDK orchestrator (Option C) as the backend runtime.

Sources: [OpenClaw](https://openclaw.ai/), [Wikipedia](https://en.wikipedia.org/wiki/OpenClaw), [DigitalOcean Overview](https://www.digitalocean.com/resources/articles/what-is-openclaw), [Architecture Guide](https://vertu.com/ai-tools/openclaw-clawdbot-architecture-engineering-reliable-and-controllable-ai-agents/)

### Integration Complexity

| Component | Complexity | Effort | Notes |
|---|---|---|---|
| Gateway deployment | **Low** | Install via npm, configure `openclaw.json` | Single daemon on port 18789, WebSocket API |
| Model routing to Bedrock | **Low** | Set `CLAUDE_CODE_USE_BEDROCK=1` + AWS creds | OpenClaw is model-agnostic, BYO API keys |
| Session management | **None** | Built-in | Gateway owns all session state, JSONL transcripts at `~/.openclaw/agents/<id>/sessions/` |
| Context compaction | **None** | Built-in | 3-layer trim/flush/compact, `/compact` command |
| Microsoft Teams channel | **Low** | `openclaw plugins install @openclaw/msteams` | Plugin-based, Azure Bot registration required |
| Cognito auth migration | **Medium** | Map JWT claims to OpenClaw device identity | Gateway uses device pairing + token auth; need adapter for Cognito JWTs |
| Tenant isolation | **Medium** | Map tenant IDs to session key prefixes | Session keys: `agent:<id>:<channel>:dm:<peerId>`, need `tenant:<id>` prefix convention |
| Subscription tier enforcement | **Medium** | Implement as gateway middleware or hooks | OpenClaw has no built-in tier/rate-limit concept; must add app-layer checks |
| Cost attribution | **Medium** | Pipe `ResultMessage.usage` to DynamoDB | OpenClaw doesn't track costs; need post-query hook to capture token usage |
| DynamoDB integration | **Medium** | Replace file-based session store with DynamoDB | Default: sessions in `~/.openclaw/` on gateway host; need custom store adapter for multi-instance |
| Custom skills (OA Intake) | **Low** | Port as AgentSkill | OpenClaw supports 100+ AgentSkills; our SKILL.md files map directly |
| Admin cost reports | **Medium** | Retain existing `admin_cost_service.py` | OpenClaw has no admin/analytics; keep our app-layer service |

**Overall integration complexity: Medium.** The gateway handles session management, context compaction, and channel routing out of the box. The main work is mapping our multi-tenant concepts (tiers, rate limits, cost attribution) onto OpenClaw's single-tenant-per-gateway model.

### Microsoft Teams Integration (Project Requirement)

OpenClaw provides a first-class Teams integration via the `@openclaw/msteams` plugin. This is a significant advantage — Teams support is a project requirement, and OpenClaw makes it near-trivial.

Source: [Microsoft Teams - OpenClaw Docs](https://docs.openclaw.ai/channels/msteams)

**Setup steps:**
1. `openclaw plugins install @openclaw/msteams`
2. Create Azure Bot resource (App ID + client secret + tenant ID)
3. Configure credentials in `openclaw.json` or env vars (`MSTEAMS_APP_ID`, `MSTEAMS_APP_PASSWORD`, `MSTEAMS_TENANT_ID`)
4. Expose `/api/messages` (port 3978) via public URL or tunnel
5. Install Teams app manifest package

**Channel support:**

| Context | Session Key Pattern | Access Control |
|---|---|---|
| Direct Messages | `agent:<id>:<mainKey>` | Pairing (default), allowlist, open, or disabled |
| Group Chats | `agent:<id>:msteams:group:<conversationId>` | Allowlist (default), open, or disabled |
| Channels | `agent:<id>:msteams:channel:<conversationId>` | Mention-gated, RSC permissions required |

**What works out of the box:**
- DM text messages and file attachments (FileConsentCard flow)
- Channel text messages with @mention triggering
- Adaptive Cards for polls and structured content
- Proactive messaging (after initial user interaction)
- Thread-style or top-level reply modes

**Limitations:**
- Channel/group file sending requires SharePoint Graph permissions (`Sites.ReadWrite.All`)
- Channel images require `ChannelMessage.Read.All` Graph permission
- Webhook timeouts possible with slow LLM responses (Teams retries can cause duplicates)
- Teams markdown is more restrictive than Slack/Discord
- Private channels have limited bot support
- Multi-tenant Azure bot registration was deprecated after 2025-07-31 — use Single Tenant for new bots

**Multi-tenant note:** Azure's deprecation of multi-tenant bot registration (July 2025) means each NCI organization/tenant would need its own Single Tenant bot registration, OR all tenants share one bot within the NCI Azure tenant. This aligns with our Cognito model where all users are in the same NCI tenant with different groups/tiers.

### Tradeoffs

| Factor | Advantage | Disadvantage |
|---|---|---|
| **Teams integration** | Plugin install, works immediately. Supports DMs, groups, channels. Huge win for project requirement. | Azure Bot registration required. Single Tenant only (multi-tenant deprecated). Webhook timeouts with slow LLM. |
| **Session management** | Built-in JSONL transcripts, auto-expiry, `/compact` command. No custom code needed. | Sessions stored on gateway host filesystem. Need DynamoDB adapter for multi-instance/HA deployment. |
| **Context compaction** | 3-layer (trim/flush/compact) built-in. Handles 200K+ conversations gracefully. | LLM calls for flush/compact cost money. Compaction quality depends on summarization model. |
| **Semantic memory** | Cross-session memory with daily logs + MEMORY.md. Hybrid BM25 + vector search. | Requires SQLite-vec (or pgvector adapter). Memory extraction adds latency and cost per conversation. |
| **Multi-channel** | 50+ platforms (Teams, Slack, Discord, WhatsApp, Telegram, Signal, etc.) via plugins. | Each channel plugin has unique quirks and limitations. Maintaining multiple channels increases ops burden. |
| **Model agnostic** | BYO API keys. Works with Claude (via Bedrock), GPT-4, local models. | Must configure each model provider. No unified cost tracking across providers. |
| **Skill system** | 100+ preconfigured AgentSkills. Our SKILL.md files port directly. | Skills are gateway-local. No built-in skill marketplace or version management. |
| **Open source (MIT)** | Full source access. No vendor lock-in. Community of 145K+ stars. | Security concerns with broad system permissions (email, files, calendars). Supply chain risk from community plugins. Must self-host and maintain. |
| **Multi-tenant** | Session key isolation provides natural per-user separation. | Not designed for organizational multi-tenancy. No built-in tenant concept, subscription tiers, or rate limits. All must be added as app-layer code. |
| **Cost tracking** | None built-in — clean slate to implement exactly what we need. | Must build all cost attribution from scratch. `ResultMessage.usage` data must be captured via hooks. |
| **Scaling** | Single daemon + worker pool is simple to operate. | Single gateway is a SPOF. No built-in horizontal scaling or load balancing. Need multiple gateways behind a router for HA. |

### Multi-Tenant Feature Matrix: Before vs After OpenClaw Integration

| Feature | Current (Bedrock Agent API) | After OpenClaw Integration | Change Impact |
|---|---|---|---|
| **Authentication** | | | |
| Cognito JWT verification | `auth.py` — decode JWT, extract `custom:tenant_id` + `custom:subscription_tier` | Retain `auth.py`. Map Cognito JWT to OpenClaw device token on first connect. | **Low** — adapter layer |
| Tenant ID extraction | From JWT `custom:tenant_id` claim | Same JWT claim, injected into OpenClaw session key as `tenant:<id>:user:<uid>` | **Low** — key format mapping |
| Role-based access (admin/user) | Cognito groups (`*-admins`) | Same Cognito groups. Admin flag passed to OpenClaw via session attributes. | **None** — unchanged |
| **Session Management** | | | |
| Session creation | `bedrock-agent-runtime.invoke_agent(sessionId=...)` | OpenClaw gateway auto-creates on first message. Session key: `agent:<id>:msteams:dm:<peerId>` or web equivalent. | **Improved** — no manual session ID management |
| Session persistence | Bedrock server-side (opaque) | JSONL files on gateway host (`~/.openclaw/agents/<id>/sessions/<sid>.jsonl`) | **Improved** — inspectable, portable |
| Session resume | Bedrock manages internally | Gateway auto-resumes from JSONL. Sessions reused until daily 4AM reset or idle timeout. | **Improved** — configurable expiry |
| Concurrent session limits | `subscription_service.py` — basic=1, advanced=3, premium=10 | Retain `subscription_service.py` check as pre-message middleware. OpenClaw has no built-in limit. | **None** — keep app-layer enforcement |
| Session duration limits | `subscription_service.py` — basic=30min, advanced=120min, premium=480min | Same app-layer enforcement. OpenClaw supports custom idle timeouts per session type. | **Low** — map tier timeout to OpenClaw config |
| Conversation branching | Not supported | Built-in JSONL tree structure (`parentId`). Premium tier feature. | **New capability gained** |
| Context compaction | Not available (Bedrock manages internally) | Built-in 3-layer: trim (free) → memory flush (1 LLM call) → compaction (1 LLM call). | **New capability gained** |
| **Subscription Tiers** | | | |
| Tier definition (basic/advanced/premium) | `models.py` — `SubscriptionTier` enum | Retain enum. Pass tier to OpenClaw via session attributes. | **None** — unchanged |
| Daily message limits | `subscription_service.py` — basic=50, advanced=200, premium=1000 | Retain `subscription_service.py`. Check before routing message to OpenClaw gateway. | **None** — keep app-layer enforcement |
| Monthly message limits | `subscription_service.py` — basic=1K, advanced=5K, premium=25K | Same app-layer enforcement. | **None** — unchanged |
| MCP tool gating by tier | `subscription_service.py` — basic=no MCP, advanced/premium=yes | Map to OpenClaw AgentSkills. Disable skills per session based on tier. | **Low** — skill enable/disable per session |
| Budget limits per query | Option C: `max_budget_usd` on `ClaudeAgentOptions` | Must implement as post-query check. OpenClaw has no built-in budget enforcement. | **Medium** — lose SDK-native budget limits |
| **Cost Attribution** | | | |
| Token tracking | `cost_attribution.py` — from Bedrock `modelInvocationOutput` | Capture from OpenClaw's post-query result. Token counts available in response metadata. | **Low** — different data source, same DynamoDB sink |
| Per-tenant cost calculation | `cost_attribution.py` — bedrock + weather API + runtime costs | Same calculation logic. Add OpenClaw gateway runtime cost category. | **Low** — add one cost category |
| Per-user cost breakdown | `cost_attribution.py` — user-level aggregation | Same logic. Map OpenClaw session `peerId` to our `user_id`. | **Low** — ID mapping |
| Admin cost reports | `admin_cost_service.py` — single-tenant and multi-tenant reports | Retain entirely. OpenClaw has no admin reporting. | **None** — unchanged |
| Real-time cost ticker | Option C: `ResultMessage.total_cost_usd` | Implement via post-query hook. Calculate from token counts + pricing table. | **Medium** — manual calculation vs SDK-provided |
| **Trace Visibility** | | | |
| Orchestration traces | `agentic_service.py` — parse `orchestrationTrace` dicts from Bedrock | OpenClaw provides typed messages (TextBlock, ToolUseBlock, ThinkingBlock). Same as Claude SDK. | **Improved** — typed vs untyped dicts |
| Real-time streaming | Not available (Bedrock returns complete response) | OpenClaw gateway streams via WebSocket. Events arrive as they happen. | **Improved** — real-time vs batch |
| Subagent traces | Not available in Bedrock Agent API | OpenClaw tracks `parent_tool_use_id` for subagent context. | **New capability gained** |
| Tool use visualization | Flat action group traces | Structured ToolUseBlock with tool name, ID, input, and parent context. | **Improved** — structured vs flat |
| **Channel Support** | | | |
| Web UI | Custom frontend (vanilla HTML/JS) | Retain custom frontend. Connect via OpenClaw WebSocket API (port 18789). | **Low** — change transport |
| Microsoft Teams | Not supported | `@openclaw/msteams` plugin. DMs, group chats, channels. Azure Bot registration. | **New capability gained** |
| Slack | Not supported | `@openclaw/slack` plugin available. | **New capability gained** |
| WhatsApp | Not supported | `@openclaw/whatsapp` plugin available. | **New capability gained** |
| Other channels | Not supported | 50+ channel plugins (Discord, Telegram, Signal, etc.) | **New capability gained** |
| **Memory & Knowledge** | | | |
| Within-session memory | Bedrock session state (opaque) | JSONL transcript — full conversation history, inspectable. | **Improved** — transparent vs opaque |
| Cross-session memory | Not available | Daily .md logs + MEMORY.md + hybrid search (BM25 + vector). Premium tier only. | **New capability gained** |
| Knowledge base integration | Bedrock KB (action group) | MCP tool calling Bedrock KB API, or OpenClaw skill wrapping KB search. | **Equivalent** — different mechanism, same result |
| **Security** | | | |
| Tenant data isolation | App-layer: 403 on tenant mismatch | Session key prefix isolation + app-layer checks. | **Equivalent** — defense in depth |
| Content filtering | Bedrock Guardrails | Must implement via OpenClaw hooks (PreToolUse/PostToolUse). | **Medium** — lose Bedrock Guardrails, gain hook flexibility |
| Audit logging | DynamoDB usage metrics | Retain DynamoDB logging. Add OpenClaw gateway logs. | **Low** — additional log source |
| Permission model | Cognito groups + IAM | Cognito groups (unchanged) + OpenClaw device pairing + gateway token auth. | **Low** — additional auth layer |

### Integration Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CHANNELS                                                                 │
│                                                                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Web UI   │  │ MS Teams │  │ Slack    │  │ WhatsApp │  │ Other     │ │
│  │ (custom) │  │ (plugin) │  │ (plugin) │  │ (plugin) │  │ channels  │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬─────┘ │
│        │             │             │             │             │         │
│        └──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘         │
│               │             │             │             │                 │
│               ▼             ▼             ▼             ▼                 │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  OpenClaw Gateway (TypeScript/Node.js daemon)                    │    │
│  │  Port 18789 (WebSocket API) + Port 3978 (Teams webhook)         │    │
│  │                                                                  │    │
│  │  Session routing: tenant:<id>:user:<uid>:session:<sid>           │    │
│  │  JSONL transcripts: ~/.openclaw/agents/<id>/sessions/*.jsonl     │    │
│  │  Context: 3-layer trim/flush/compact                             │    │
│  │  Memory: daily .md + MEMORY.md + hybrid search                   │    │
│  └──────────────────────────┬───────────────────────────────────────┘    │
│                              │                                           │
│  ┌───────────────────────────┴──────────────────────────────────────┐    │
│  │  NCI App Layer (FastAPI middleware — RETAINED)                    │    │
│  │                                                                  │    │
│  │  Pre-message:                                                    │    │
│  │    1. Validate Cognito JWT (auth.py)                             │    │
│  │    2. Extract tenant_id + tier from JWT claims                   │    │
│  │    3. Check rate limits (subscription_service.py)                │    │
│  │    4. Map JWT → OpenClaw device token                            │    │
│  │                                                                  │    │
│  │  Post-message:                                                   │    │
│  │    1. Capture token usage from response                          │    │
│  │    2. Record cost attribution (cost_attribution.py)              │    │
│  │    3. Increment tier usage counters (subscription_service.py)    │    │
│  │    4. Stream traces to Web UI via WebSocket                      │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                              │                                           │
│  ┌───────────────────────────┴──────────────────────────────────────┐    │
│  │  AWS Services (RETAINED)                                         │    │
│  │                                                                  │    │
│  │  Bedrock (Layer 1)  │  Cognito  │  DynamoDB  │  CloudWatch      │    │
│  │  Model inference    │  Auth     │  Sessions  │  Monitoring       │    │
│  │  via OpenClaw       │  JWTs     │  Usage     │  Logs             │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

### OpenClaw-First Integration Path (Recommended if Gateway Already Running)

If OpenClaw is already running in a container (ECS, EC2, or external host), the integration simplifies dramatically. Instead of building the SDK orchestrator service from Phase 1 of the multi-tenant spec (`sdk_orchestrator.py`, `websocket_manager.py`, `sdk_tools.py`, `sdk_agents.py`), the NCI app layer connects directly to the existing gateway.

**What you skip building entirely:**

| Planned Component | Status | Why Skipped |
|---|---|---|
| `sdk_orchestrator.py` | **Not needed** | OpenClaw gateway IS the orchestrator |
| `websocket_manager.py` | **Not needed** | Gateway manages all WebSocket connections natively (port 18789) |
| `sdk_tools.py` | **Not needed** | Port tools as OpenClaw AgentSkills or MCP servers |
| `sdk_agents.py` | **Not needed** | Define agents in `openclaw.json` agent config |
| `query(resume=session_id)` loop | **Not needed** | Gateway owns session lifecycle, auto-resume from JSONL |
| Context compaction code | **Not needed** | Built-in 3-layer trim/flush/compact |
| Vue frontend WebSocket client | **Simplified** | Connect to existing gateway WebSocket API instead of building custom transport |

**What you keep (NCI app layer as reverse proxy middleware):**

```
┌─────────────────────────────────────────────────────────────┐
│  NCI Middleware (FastAPI or Express)                          │
│                                                              │
│  Incoming request from Web UI / Teams / Slack:               │
│    1. Validate Cognito JWT (auth.py — unchanged)             │
│    2. Extract tenant_id + tier from JWT claims               │
│    3. Check rate limits (subscription_service.py — unchanged)│
│    4. Map JWT → OpenClaw gateway token                       │
│    5. Forward to OpenClaw gateway (ws://localhost:18789)     │
│                                                              │
│  Response from OpenClaw gateway:                             │
│    6. Capture token usage from response metadata             │
│    7. Record cost attribution (cost_attribution.py)          │
│    8. Increment tier usage counters                          │
│    9. Forward response to client                             │
└─────────────────────────────────────────────────────────────┘
```

**OpenClaw gateway connection details:**

- **WebSocket API**: `ws://127.0.0.1:18789` (loopback when co-located, or internal ALB when on separate ECS task)
- **REST endpoint**: `POST http://127.0.0.1:18789/tools/invoke` (tool invocation only, 2MB max payload)
- **Auth**: Gateway token via `Authorization: Bearer <OPENCLAW_GATEWAY_TOKEN>` or WebSocket connect handshake
- **Wire protocol**: JSON messages with `type: "req"/"res"/"event"`, `method`, `params`, `payload`

**Connect handshake:**
```json
{
  "type": "connect",
  "role": "client",
  "capabilities": [],
  "auth": { "token": "<OPENCLAW_GATEWAY_TOKEN>" }
}
```

**Integration effort comparison:**

| Approach | Files to Create | Files to Modify | New Dependencies | Complexity |
|---|---|---|---|---|
| Option C (SDK Orchestrator) | 6 new Python files + Vue frontend (17 files) | 2 existing files | `claude-agent-sdk`, `websockets`, Vue/Vite/Pinia | **High** |
| OpenClaw-First | 1 proxy middleware file | 2 existing files | `websockets` (proxy only) | **Low** |

The OpenClaw-first path reduces Phase 1 from 6 new backend files to 1 proxy middleware file. Phase 2 (Vue frontend) simplifies because the WebSocket protocol is already defined by OpenClaw — the frontend just speaks the gateway's wire protocol directly.

**Agent configuration** moves from Python code to `openclaw.json`:

```json
{
  "agents": {
    "nci-oa-intake": {
      "model": {
        "primary": "bedrock/anthropic.claude-sonnet-4-20250514"
      },
      "systemPrompt": "You are an NCI Office of Acquisitions intake assistant...",
      "tools": ["mcp__kb__search", "mcp__inventory__lookup"],
      "sandbox": {
        "mode": "non-main",
        "docker": {
          "network": "none",
          "readOnlyRoot": true,
          "memory": "1g"
        }
      }
    }
  }
}
```

**Tenant context injection** uses session attributes on the gateway's WebSocket API rather than `system_prompt` in `ClaudeAgentOptions`. The NCI middleware injects tenant context into the message before forwarding to the gateway.

### AWS Service Mapping

Every OpenClaw component maps to an AWS service. This table shows the production deployment architecture.

Sources: [Pulumi OpenClaw AWS Guide](https://www.pulumi.com/blog/deploy-openclaw-aws-hetzner/), [DEV Community AWS Setup](https://dev.to/brayanarrieta/how-to-set-up-openclaw-ai-on-aws-3a0j), [OpenClaw Docker Docs](https://docs.openclaw.ai/install/docker), [OpenClaw Gateway Docs](https://docs.openclaw.ai/gateway)

| OpenClaw Component | AWS Service | Configuration Details |
|---|---|---|
| **Gateway daemon** | **ECS Fargate Task** | Long-running container from ECR image. 2 vCPU / 4 GB minimum. Runs as non-root `node` user (UID 1000). Set `NODE_ENV=production`. Restart policy: always. |
| **WebSocket API** (port 18789) | **ALB** (Application Load Balancer) | HTTPS listener (443) → target group on port 18789. Enable WebSocket support (native in ALB). Sticky sessions enabled. Idle timeout: 3600s for long-lived connections. Connection draining: 300s. Configure `gateway.trustedProxies` to trust ALB CIDR. |
| **Teams webhook** (port 3978) | **ALB** (second listener/target group) | Separate target group on port 3978 for `/api/messages` endpoint. Public-facing for Azure Bot Service callbacks. Can share the same ALB with a path-based routing rule. |
| **JSONL session files** (`~/.openclaw/agents/<id>/sessions/`) | **EFS** (Elastic File System) | Mount to container at `~/.openclaw/`. Access point with UID/GID 1000:1000. Encryption at rest enabled. Elastic throughput mode. Stores session transcripts, agent configs, workspace files. |
| **SQLite-vec memory index** (`~/.openclaw/memory/<agentId>.sqlite`) | **EFS** (same mount) | Stored alongside sessions on EFS. Uses `sqlite-vec` extension for vector embeddings. **Limitation**: SQLite file locking prevents multi-instance horizontal scaling — single gateway instance only. |
| **Plugin system** (`~/.openclaw/extensions/`) | **ECR image layers + EFS** | Static plugins: bake into Docker image at build time. Dynamic plugins: install to EFS-backed `extensions/` directory. Pre-install `@openclaw/msteams` and other required plugins in Dockerfile. |
| **openclaw.json** config | **SSM Parameter Store + EFS** | Base config on EFS. Non-sensitive overrides in Parameter Store. Supports `${VAR_NAME}` env var substitution. JSON5 format (supports comments). Override location via `OPENCLAW_CONFIG_PATH` env var. |
| **Agent credentials** (API keys, OAuth tokens) | **Secrets Manager** | All API keys (`ANTHROPIC_API_KEY`, AWS creds, Azure Bot credentials) in Secrets Manager. Injected as environment variables into ECS task definition. Gateway reads from env vars (precedence: process env → `.env` → config). Never store in plaintext `openclaw.json`. |
| **Health monitoring** | **CloudWatch + ALB Health Checks** | ALB target group health check on port 18789 `/` endpoint. Container-level: `openclaw health` command. CloudWatch Container Insights for CPU/memory/network metrics. Custom CloudWatch metrics for token usage and cost. |
| **Gateway scaling** | **ECS Service** (desired count: **1**) | **Not horizontally scalable** — SQLite file locking and single channel session ownership prevent multiple instances. Vertical scaling only: increase task CPU/memory. ECS auto-recovery restarts failed tasks. For HA: ECS service with min=1, max=1, health check grace period. |
| **DNS/routing** | **Route 53** | A record alias to ALB (e.g., `openclaw.nci.nih.gov`). Optional: health check routing policy for failover. Certificate validation via Route 53 DNS records. |
| **SSL/TLS** | **ACM** (Certificate Manager) | Free public certificate attached to ALB HTTPS listener. ALB terminates TLS, forwards HTTP to ECS tasks. Auto-renewal managed by ACM. |
| **Logs** | **CloudWatch Logs** | ECS task definition `awslogs` driver → CloudWatch log group `/ecs/openclaw-gateway`. Gateway logs to stdout/stderr. Set log retention policy (30/90/365 days). Optional: structured JSON logging for CloudWatch Insights queries. |
| **Container image** | **ECR** (Elastic Container Registry) | Private repository. Base: `node:22-bookworm-slim` or official `alpine/openclaw`. Pre-install plugins, system packages. Image scanning enabled. Lifecycle policy for old images. |
| **Sandbox containers** (agent execution) | **ECS Task** (nested, or shared host Docker) | OpenClaw spawns sandbox containers for agent code execution. Sandboxes run with `network: none`, `readOnlyRoot: true`, `capDrop: ALL`. Requires Docker socket access or ECS host mode (not Fargate-compatible for nested containers). **Note**: Fargate does not support Docker-in-Docker — use EC2 launch type or disable sandboxing. |
| **NCI middleware** (auth, tiers, cost) | **ECS Fargate Task** (separate service) | FastAPI or Express service on its own ECS task. Connects to OpenClaw gateway via internal ALB or service discovery. Accesses Cognito, DynamoDB, Secrets Manager via IAM task role. |
| **User auth** | **Cognito** (existing) | No change. NCI middleware validates JWTs. Maps Cognito `custom:tenant_id` to OpenClaw session key prefix. |
| **Usage/session tracking** | **DynamoDB** (existing) | No change. NCI middleware records usage metrics. Cost attribution per tenant/user stored in existing tables. |

### AWS Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  INTERNET                                                                     │
│                                                                               │
│  Users (Web) ──┐                                                              │
│  MS Teams ─────┤                                                              │
│  Slack ────────┤                                                              │
│                ▼                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  Route 53: openclaw.nci.nih.gov                                      │    │
│  │  ACM Certificate (auto-renew)                                        │    │
│  └──────────────────────────┬───────────────────────────────────────────┘    │
│                              │                                               │
│  ┌──────────────────────────┴───────────────────────────────────────────┐    │
│  │  ALB (Application Load Balancer)                                      │    │
│  │                                                                       │    │
│  │  Listener :443 (HTTPS/WSS)                                           │    │
│  │    ├─ /api/messages → Target Group: Teams Webhook (port 3978)        │    │
│  │    └─ /* → Target Group: Gateway WebSocket (port 18789)              │    │
│  │                                                                       │    │
│  │  Idle timeout: 3600s │ Sticky sessions: enabled                      │    │
│  └──────────┬────────────────────────┬──────────────────────────────────┘    │
│             │                         │                                       │
│  ┌──────────┴──────────┐  ┌──────────┴──────────────────────────────────┐   │
│  │  ECS Service:        │  │  ECS Service: OpenClaw Gateway              │   │
│  │  NCI Middleware      │  │                                              │   │
│  │  (FastAPI/Express)   │  │  Task: 2 vCPU / 4 GB RAM                    │   │
│  │                      │  │  Image: ECR (openclaw:latest)               │   │
│  │  - Cognito JWT auth  │  │  Ports: 18789, 3978                         │   │
│  │  - Rate limit check  │  │  Desired count: 1 (not horizontally         │   │
│  │  - Cost attribution  │  │    scalable due to SQLite file locking)     │   │
│  │  - Tier enforcement  │  │                                              │   │
│  │                      │  │  Env vars from Secrets Manager:             │   │
│  │  Connects to gateway │  │    OPENCLAW_GATEWAY_TOKEN                   │   │
│  │  via internal ALB or │  │    AWS_ACCESS_KEY_ID (for Bedrock)          │   │
│  │  service discovery   │  │    AWS_SECRET_ACCESS_KEY                    │   │
│  └──────────────────────┘  │    MSTEAMS_APP_ID                           │   │
│                             │    MSTEAMS_APP_PASSWORD                     │   │
│                             │    MSTEAMS_TENANT_ID                        │   │
│                             │                                              │   │
│                             │  Volume: EFS mount at ~/.openclaw/          │   │
│                             └──────────┬─────────────────────────────────┘   │
│                                         │                                     │
│  ┌──────────────────────────────────────┴────────────────────────────────┐   │
│  │  EFS (Elastic File System)                                            │   │
│  │  Access Point: UID 1000 / GID 1000 │ Encryption: at rest             │   │
│  │                                                                       │   │
│  │  ~/.openclaw/                                                         │   │
│  │    ├── openclaw.json              (gateway config)                    │   │
│  │    ├── memory/<agentId>.sqlite    (vector memory index)               │   │
│  │    ├── agents/<id>/sessions/*.jsonl (session transcripts)             │   │
│  │    ├── extensions/                (installed plugins)                  │   │
│  │    └── workspace/                 (agent working files)               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │  Supporting AWS Services                                                │  │
│  │                                                                         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐ │  │
│  │  │ Bedrock  │  │ Cognito  │  │ DynamoDB  │  │ Secrets  │  │ Cloud  │ │  │
│  │  │ Runtime  │  │          │  │           │  │ Manager  │  │ Watch  │ │  │
│  │  │ (Layer1) │  │ User     │  │ Sessions  │  │          │  │        │ │  │
│  │  │          │  │ Pool +   │  │ Usage     │  │ API keys │  │ Logs   │ │  │
│  │  │ Claude   │  │ Groups   │  │ Cost      │  │ OAuth    │  │ Metrics│ │  │
│  │  │ via IAM  │  │ JWTs     │  │ Tracking  │  │ Tokens   │  │ Alarms │ │  │
│  │  └──────────┘  └──────────┘  └───────────┘  └──────────┘  └────────┘ │  │
│  │                                                                         │  │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────┐                            │  │
│  │  │ ECR      │  │ SSM      │  │ Route 53  │                            │  │
│  │  │          │  │ Param    │  │           │                            │  │
│  │  │ Container│  │ Store    │  │ DNS       │                            │  │
│  │  │ Images   │  │ Config   │  │ Records   │                            │  │
│  │  └──────────┘  └──────────┘  └───────────┘                            │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Fargate vs EC2 Launch Type

OpenClaw has a sandbox feature that spawns nested Docker containers for agent code execution. This creates a deployment constraint:

| Launch Type | Sandbox Support | Tradeoffs |
|---|---|---|
| **Fargate** | **No** — Fargate does not support Docker-in-Docker | Simpler ops, no instance management. Must disable sandboxing (`sandbox.mode: "off"`) or run agents in-process. |
| **EC2** (with Docker socket) | **Yes** — container can spawn sibling containers via host Docker socket | Requires instance management, patching, AMI updates. Supports full sandbox isolation (`network: none`, `readOnlyRoot: true`, `capDrop: ALL`). |
| **EC2 + ECS Exec** | **Yes** — same as EC2 | Adds SSH-like access for debugging. |

**Recommendation**: Start with **Fargate** (sandbox disabled) for simplicity. NCI agents don't execute arbitrary user code — they call Bedrock and MCP tools. Sandboxing is more relevant for general-purpose coding agents. If sandboxing is later needed, migrate to EC2 launch type.

### Decision Factors

**Choose OpenClaw-first (recommended when gateway is already running):**
- OpenClaw is already deployed in a container — skip building SDK orchestrator entirely
- Teams integration is a hard requirement — `@openclaw/msteams` plugin is near-trivial
- Multi-channel support (Slack, WhatsApp, etc.) is on the roadmap
- Long conversations need context compaction (200K+ tokens)
- Cross-session memory is a user requirement
- Reduces Phase 1 from 6 new files to 1 proxy middleware file

**Stay with Option C (Claude SDK) when:**
- No existing OpenClaw deployment to leverage
- Web-only UI is sufficient
- Teams integration can be built separately (Bot Framework SDK)
- SDK-native features are needed (budget enforcement, `@tool` decorator, subagent definitions in Python)
- The team prefers Python over TypeScript for agent configuration
- Horizontal scaling is required (OpenClaw is single-instance due to SQLite)

**Hybrid approach:**
- Use OpenClaw gateway for channel routing (Teams, Slack, web) and session management
- Use Claude via Bedrock as the model backend (OpenClaw is model-agnostic, configure in `openclaw.json`)
- Retain all NCI app-layer code (auth, tiers, cost attribution, admin reports) as middleware
- NCI middleware sits between ALB and OpenClaw gateway, enforcing business rules

### AWS Compatibility Audit

Not every OpenClaw component is AWS-native. This table identifies each non-AWS component and its AWS-native replacement path.

| Component | What It Is | AWS Problem | AWS-Native Replacement | Migration Effort |
|---|---|---|---|---|
| **OpenClaw Gateway** | Node.js daemon (the core runtime) | Self-hosted OSS — not an AWS managed service. AWS has no equivalent managed agent gateway. | No direct replacement. Runs ON AWS (ECS) but is not an AWS service. This is the core value proposition of the integration. | **N/A** — accepted |
| **SQLite-vec** | Local vector DB for memory search at `~/.openclaw/memory/<agentId>.sqlite` | Not an AWS service. Runs on EFS which is a poor fit for SQLite — network filesystem latency + file locking. This is the root cause of the single-instance scaling limitation. | **RDS PostgreSQL + pgvector** (already in NCI stack). OpenClaw's `memorySearch.store.path` config would need a custom adapter to point to RDS instead of local SQLite. Alternatively, **Amazon OpenSearch Serverless** with k-NN vector search. | **Medium** — custom store adapter |
| **JSONL session files** | Append-only session transcripts at `~/.openclaw/agents/<id>/sessions/*.jsonl` | File-based storage on EFS. Not queryable via SQL. EFS + SQLite locking = why gateway can't scale horizontally. | **DynamoDB** with partition key `tenant_id#session_id` and sort key `msg_id`. Or **S3** at `s3://bucket/tenants/{tid}/sessions/{sid}.jsonl` for cold storage. OpenClaw would need a custom session store adapter. | **Medium** — custom session adapter |
| **Device pairing auth** | OpenClaw's native auth: device identity + gateway token + challenge-nonce signing | Not IAM or Cognito compatible. Gateway uses its own token system (`OPENCLAW_GATEWAY_TOKEN`), not JWT verification. | **Cognito JWT → gateway token adapter**. NCI middleware validates Cognito JWT, maps claims to a gateway token, and forwards. The gateway token acts as a service-to-service credential, not user identity. User identity comes from JWT claims injected by middleware. | **Low** — adapter in NCI middleware |
| **Docker-in-Docker** (sandboxes) | OpenClaw spawns nested containers for agent code execution with `network: none`, `readOnlyRoot: true` | Fargate does not support Docker-in-Docker. Would require EC2 launch type with Docker socket bind-mount. | **Disable sandboxing** (`sandbox.mode: "off"`). NCI agents call Bedrock and MCP tools — they don't execute arbitrary user code. Sandboxing is for coding agents, not acquisition intake. If later needed, switch to EC2 launch type. | **None** — disable |
| **Tailscale** | VPN overlay for secure remote gateway access. Referenced in Pulumi deployment guide. | Third-party service, not AWS-native. Requires Tailscale account and coordination servers outside AWS. | **SSM Session Manager** (free with ECS, already available). For admin access: `aws ecs execute-command`. For network isolation: **VPC + Security Groups + NACLs**. For remote desktop: **AWS Client VPN** or **Systems Manager Fleet Manager**. | **None** — don't use Tailscale, use SSM |
| **EFS for SQLite** | EFS mount provides persistent storage across container restarts | EFS is AWS-native, but SQLite on a network filesystem is an anti-pattern. POSIX file locking over NFS has known latency and reliability issues. Works for JSONL append-only writes but risky for SQLite concurrent reads/writes. | Accept for low-concurrency single-instance use (NCI scale). If issues arise, migrate SQLite to **RDS PostgreSQL** and JSONL to **DynamoDB/S3**. Monitor EFS `PercentIOLimit` and `BurstCreditBalance` in CloudWatch. | **Low** — monitor, migrate if needed |

**Summary**: The gateway itself and the Teams/Slack plugins are the value — they run on AWS but aren't AWS services. The storage layer (SQLite-vec + JSONL files) is the main AWS compatibility concern. For NCI's scale (internal acquisition teams, not consumer traffic), running SQLite on EFS with a single gateway instance is acceptable. If scaling beyond one instance becomes necessary, replace SQLite-vec with RDS pgvector and JSONL with DynamoDB — this eliminates the file locking constraint and enables horizontal scaling.

### Security Considerations

Source: [JFrog Security Analysis](https://jfrog.com/blog/giving-openclaw-the-keys-to-your-kingdom-read-this-first/), [OpenClaw Security Docs](https://docs.openclaw.ai/gateway/security)

OpenClaw's broad permission model has drawn scrutiny:
- The agent can access email, files, calendars, and messaging platforms
- Community plugins introduce supply chain risk
- NCI deployment should: pin plugin versions, audit all installed plugins, run gateway in a locked-down container with minimal host access, disable unnecessary channels, and enforce allowlist-only access policies
- The `@openclaw/msteams` plugin requires Azure Bot credentials — store in AWS Secrets Manager, not in `openclaw.json` on disk
- Run as non-root user (UID 1000, default in official image)
- Set `gateway.bind.host: "127.0.0.1"` (loopback) — let ALB handle public traffic
- Require `OPENCLAW_GATEWAY_TOKEN` for all API access, stored in Secrets Manager
- Sandbox disabled (Fargate) — agents run in-process, controlled via tool policies and allowed_tools config
- EFS encryption at rest for session transcripts and memory databases
- Secrets Manager rotation for API keys and OAuth tokens
- Use **SSM Session Manager** (not Tailscale) for admin access to gateway container

## Key Takeaway

If OpenClaw is already running in a container, the integration path simplifies from a multi-week SDK orchestrator build (6 new Python files + 17 Vue component files) to a single proxy middleware file that validates JWTs, checks rate limits, and forwards to the existing gateway. OpenClaw handles session management, context compaction, memory, and channel routing — the NCI app layer only handles business rules (auth, tiers, cost attribution).

The **Teams requirement** remains the strongest argument: `@openclaw/msteams` provides production-ready Teams support (DMs, group chats, channels) that would otherwise require significant custom Bot Framework SDK development. The AWS service mapping shows a clean deployment on ECS Fargate (gateway) + EFS (sessions/memory) + ALB (WebSocket/TLS termination), with all existing AWS services (Cognito, DynamoDB, Bedrock, CloudWatch) retained unchanged.

**AWS compatibility**: The gateway and plugins run on AWS but are not AWS-managed services. The storage layer (SQLite-vec + JSONL files on EFS) is the main compatibility concern. For NCI's scale (internal acquisition teams), single-instance on EFS is acceptable. To go fully AWS-native on storage, replace SQLite-vec with RDS pgvector and JSONL with DynamoDB — both already in the NCI stack. No third-party services (Tailscale, Composio, etc.) are required — use SSM Session Manager for admin access and Secrets Manager for credentials.

**Key constraint**: OpenClaw is **not horizontally scalable** due to SQLite file locking. The gateway runs as a single instance (ECS desired count: 1). For NCI's use case, this is acceptable. If scaling beyond one instance becomes necessary, migrating the storage layer to AWS-native services (pgvector + DynamoDB) eliminates the file locking constraint.
