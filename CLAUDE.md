# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview


EAGLE is a multi-tenant AI acquisition assistant for NCI (National Cancer Institute). It helps contracting officers navigate federal procurement — intake, FAR/DFARS guidance, document generation (SOW, IGCE, AP). Built with TAC methodology: supervisor orchestrates specialist subagents via Strands Agents SDK (boto3-native Bedrock), streamed over SSE to a Next.js frontend.

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Next.js (App Router) | Frontend — chat UI, admin dashboard, Playwright E2E |
| FastAPI | Backend — SSE streaming, tool dispatch, Cognito auth |
| Strands Agents SDK | Supervisor → subagent orchestration via BedrockModel (boto3-native) |
| Anthropic API | Direct fallback when Strands/Bedrock unavailable |
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
├── server/              ← FastAPI + Strands SDK backend
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

**Flow**: `POST /api/chat` (REST, primary) or `POST /api/chat/stream` (SSE) → `sdk_query()` / `sdk_query_streaming()` → Strands Agent with BedrockModel → specialist subagents via tool dispatch. Frontend proxy (`/api/invoke`) targets REST endpoint and wraps response in SSE. Falls back to direct Anthropic API when Strands/Bedrock unavailable.

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
| Production deploy | 1–4 + post-deploy smoke (see below) |

---

## Post-Deploy Smoke

After any deploy that touches the SSE/research/chat path, validate the
*deployed* environment with the devbox-driven smoke harness. Local pytest
proves the code; the smoke proves the deployed container behaves and the
frontend renders the wire shape.

**Run it:**

```bash
just dev-smoke-deployed                                    # default scenario
just dev-smoke-deployed research_source_transparency       # explicit
just qa-smoke-deployed research_source_transparency        # qa (with --auth)
```

**What it does:**

1. SSMs into the EC2 devbox (`eagle-ec2-dev`) — VPC-internal so the
   internal ALB DNS resolves.
2. POSTs a scenario query to `<backend ALB>/api/chat`, validates the
   response wire shape (lane/score/score_pct/rationale/read fields on
   research entries; `_meta.lane_breakdown`; cap-bump assertion).
3. Drives the chat UI on `<frontend ALB>` with Playwright, taking 4–5
   screenshots: `01-empty`, `02-typed`, `03-streaming`, `04-complete`,
   `05-sources-table`.
4. Uploads PNGs + structured `result.json` to
   `s3://eagle-eval-artifacts-{account}-{env}/smoke/{scenario}/{ts}/`.
5. Exits 0 on PASS, 1 on FAIL.

**Files:**

| File | Purpose |
|------|---------|
| `server/tests/post_deploy_smoke.py` | Devbox-side orchestrator (POST + Playwright + S3 upload). Add new scenarios to its `SCENARIOS` registry. |
| `scripts/_remote_post_deploy_smoke.py` | Laptop-side SSM driver — confirm devbox up, sync repo, stage orchestrator, run via SSM, pull JSON back. |
| `Justfile` recipes | `dev-smoke-deployed [SCENARIO]`, `qa-smoke-deployed [SCENARIO]`. |

**Adding a new scenario** — append to `SCENARIOS` in `post_deploy_smoke.py`:

```python
SCENARIOS["my_new_feature"] = {
    "label": "Short human title",
    "query": "the chat message that exercises the feature",
    "expects": {
        "research_packet_fields": ["lane", "score", ...],   # if it touches research
        "meta_fields": ["lane_breakdown", ...],
        "min_total_surfaced": 4,
    },
}
```

The `eagle-eval-artifacts-{account}-{env}` bucket (provisioned by
`EagleEvalStack`) is the canonical screenshots + smoke artifacts store.
365-day lifecycle, S3-managed encryption.

---

## Key Files

| File | Purpose |
|------|---------|
| `server/app/strands_agentic_service.py` | Strands SDK orchestration — supervisor + subagents (BedrockModel) |
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
| Hand off env to co-worker | `/claude-handoff` (bundles `~/.claude/` config + scrubbed session JSONLs into a portable folder; see `.claude/skills/claude-handoff/`) |
| Search/inspect session history | `/pp-claude-sessions` query CLI (stdlib Python, read-only over a handoff bundle's `session-history/jsonl/` or any `~/.claude/projects/<encoded>/`; see `.claude/skills/pp-claude-sessions/`) |

**Expert system**: `.claude/commands/experts/{domain}/` — 9 domains: `frontend` · `backend` · `aws` · `claude-sdk` · `deployment` · `cloudwatch` · `eval` · `git` · `tac`. Run `/experts:{domain}:plan` to plan, `/experts:{domain}:self-improve` after significant changes.

---

## Notes

### Artifact Naming

| Type | Destination | Example |
|------|-------------|---------|
| `plan` | `.claude/specs/` | `20260217-143000-plan-sdk-signing-v1.md` |
| `pbi` | `.claude/specs/` | `20260217-143000-pbi-frontend-dark-mode-v1.md` |
| `eval` | `server/tests/` | `20260217-160000-eval-sdk-patterns-v1.md` |
| `arch` | `docs/architecture/diagrams/excalidraw/` | `20260222-150000-arch-streaming-v1.excalidraw.md` |
| `report` | `docs/development/` | `20260222-160000-report-cost-v1.md` |
| `meeting` | `docs/development/meeting-transcripts/` | `20260217-170000-meeting-sprint-planning-v1.md` |
