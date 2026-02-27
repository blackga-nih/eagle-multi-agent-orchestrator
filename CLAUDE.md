# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

EAGLE is a multi-tenant AI acquisition assistant for NCI (National Cancer Institute). It helps contracting officers navigate federal procurement — intake, FAR/DFARS guidance, document generation (SOW, IGCE, AP). Built with TAC methodology: supervisor orchestrates specialist subagents via Claude Agent SDK, streamed over SSE to a Next.js frontend.

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Next.js (App Router) | Frontend — chat UI, admin dashboard, Playwright E2E |
| FastAPI | Backend — SSE streaming, tool dispatch, Cognito auth |
| Claude Agent SDK | Supervisor → subagent orchestration (primary path) |
| Anthropic API | Direct fallback when SDK subprocess fails |
| AWS CDK (TypeScript) | Infrastructure — ECS Fargate, Cognito, DynamoDB, S3 |
| DynamoDB single-table | Sessions, messages, usage, costs, subscriptions |

---

## Commands

```bash
# Frontend (client/)
npm run dev                              # → localhost:3000
npx tsc --noEmit                         # Type check
npx playwright test                      # E2E tests

# Backend (server/)
uvicorn app.main:app --reload --port 8000
ruff check app/                          # Lint
python -m pytest tests/ -v              # Unit + eval tests

# Infrastructure (infrastructure/cdk-eagle/)
npm run build && npx cdk synth --quiet
```

---

## Project Structure

```
/
├── client/              ← Next.js frontend
├── server/              ← FastAPI + Claude SDK backend
│   └── app/             ← Routes, services, stores
├── eagle-plugin/        ← Agent + skill definitions (source of truth)
│   ├── plugin.json      ← Active agents + skills manifest
│   ├── agents/          ← supervisor + 7 specialists
│   └── skills/          ← 5 skill definitions
├── infrastructure/
│   └── cdk-eagle/       ← CDK stacks (Core, Compute, CiCd, Eval)
├── .claude/
│   ├── commands/experts/ ← 9 expert domains
│   └── specs/           ← Implementation plans
└── docs/                ← Architecture, meeting notes
```

---

## Architecture

**Flow**: `POST /api/chat/stream` → `sdk_query()` → supervisor (Task tool) → specialist subagents (each gets a fresh context window via `AgentDefinition`). Falls back to direct Anthropic API when the SDK subprocess can't start (e.g. nested Claude Code session).

**Streaming**: `StreamingResponse` → `asyncio.Queue` → `MultiAgentStreamWriter` → SSE events (`text`, `tool_use`, `complete`, `error`) → `use-agent-stream.ts` hook.

**Plugin loading**: `eagle_skill_constants.py` auto-discovers `eagle-plugin/agents/*/agent.md` + `skills/*/SKILL.md` via YAML frontmatter. Never put agent content in `server/app/` — modify `eagle-plugin/` only.

---

## Code Patterns

**Naming**
- Artifacts: `{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.{ext}` (scan dest dir for highest `vN`, never overwrite)
- DynamoDB keys: `SESSION#`, `MSG#`, `USAGE#`, `COST#`, `SUB#`
- Session IDs: `{tenant_id}-{tier}-{user_id}-{session_id}`

**Rules**
- Subscription tiers gate features: `basic` / `advanced` / `premium`
- Never edit `expertise.md` files manually — run `/experts:{domain}:self-improve`
- Specs go in `.claude/specs/` with validation commands included

---

## Validation

```bash
ruff check app/          # Level 1 — Python lint
npx tsc --noEmit         # Level 1 — TypeScript check
python -m pytest tests/  # Level 2 — Unit + eval
npx playwright test      # Level 3 — E2E
npx cdk synth --quiet    # Level 4 — Infra compile
```

| Change type | Minimum |
|-------------|---------|
| Backend logic | 1 + 2 |
| Frontend UI | 1 + 3 |
| CDK change | 1 + 4 |
| Production deploy | 1–4 + docker compose |

---

## Key Files

| File | Purpose |
|------|---------|
| `server/app/sdk_agentic_service.py` | Claude SDK orchestration — supervisor + subagents |
| `server/app/streaming_routes.py` | SSE endpoint + fallback to direct API |
| `server/app/stream_protocol.py` | SSE event format (`MultiAgentStreamWriter`) |
| `server/eagle_skill_constants.py` | Auto-discovery of plugin content |
| `eagle-plugin/plugin.json` | Active agents + skills manifest |
| `client/hooks/use-agent-stream.ts` | Frontend SSE consumer |
| `client/components/chat-simple/simple-chat-interface.tsx` | Active chat UI |
| `infrastructure/cdk-eagle/lib/` | CDK stacks (Core, Compute, CiCd) |

---

## On-Demand Context

| Need | Where |
|------|-------|
| Frontend patterns | `/experts:frontend:question` |
| Backend patterns | `/experts:backend:question` |
| AWS / CDK | `/experts:aws:question` |
| Claude SDK | `/experts:claude-sdk:question` |
| Deployment | `/experts:deployment:question` |
| Eval suite | `/experts:eval:question` |
| Architecture diagrams | `docs/architecture/` |
| Implementation specs | `.claude/specs/` |

**Expert system**: `.claude/commands/experts/{domain}/` — 9 domains: `frontend` · `backend` · `aws` · `claude-sdk` · `deployment` · `cloudwatch` · `eval` · `git` · `tac`. Run `/experts:{domain}:plan` to plan, `/experts:{domain}:self-improve` after significant changes.

---

## Notes

### Artifact Naming

| Type | Destination | Example |
|------|-------------|---------|
| `plan` | `.claude/specs/` | `20260217-143000-plan-sdk-signing-v1.md` |
| `pbi` | `.claude/specs/` | `20260217-143000-pbi-frontend-dark-mode-v1.md` |
| `eval` | `server/tests/` | `20260217-160000-eval-sdk-patterns-v1.md` |
| `arch` | `docs/architecture/` | `20260222-150000-arch-streaming-v1.excalidraw.md` |
| `report` | `docs/development/` | `20260222-160000-report-cost-v1.md` |
| `meeting` | `docs/development/meeting-transcripts/` | `20260217-170000-meeting-sprint-planning-v1.md` |
