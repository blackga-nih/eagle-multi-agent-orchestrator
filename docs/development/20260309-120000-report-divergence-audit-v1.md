# EAGLE Branch Divergence & Architecture Audit

**Date**: 2026-03-09
**Branch Audited From**: `fix/fast-path-kb-tools`
**Repository**: CBIIT/sm_eagle

---

## Executive Summary

Three active feature branches diverge from `main`, collectively modifying 298 commits across 7 contributors since February 1. The highest risk surfaces in `server/app/agentic_service.py` and `server/app/strands_agentic_service.py`, which all three branches touch simultaneously. Alvi Hoque merged PR #20 on March 6 introducing five new backend modules and 1,161 lines of tests for a Canonical Package Document Flow, creating additional 3-way merge pressure on `strands_agentic_service.py`, `main.py`, and `streaming_routes.py`. A sequential merge strategy — fast-path first, sse-telemetry second, copilotkit-agui last — carries the lowest integration risk.

---

## 1. Branch Divergence Matrix

### Active Branches

| Branch | Commits Ahead | Files Changed | Lines +/- | Status |
|--------|:------------:|:-------------:|:---------:|--------|
| `fix/fast-path-kb-tools` | 3 | 5 | +92 / -15 | Pushed, no PR |
| `feat/copilotkit-agui` | 9 | 57 | +20,864 / -2,727 | Local only |
| `feat/sse-telemetry` | 8 | 51 | +15,573 / -1,611 | Pushed |

### Overlap Matrix

| File | fast-path | copilotkit | sse-telemetry | Risk |
|------|:---------:|:----------:|:-------------:|------|
| `server/app/agentic_service.py` | X | X | X | **HIGH** |
| `server/app/strands_agentic_service.py` | X | X | X | **HIGH** |
| `server/app/streaming_routes.py` | — | X | X | **HIGH** |
| `server/app/stream_protocol.py` | — | X | X | **HIGH** |
| `server/app/template_store.py` | — | X | X | MEDIUM |
| `eagle-plugin/agents/supervisor/agent.md` | — | X | X | MEDIUM |

### Per-Branch Changes by Area

**`fix/fast-path-kb-tools`** — 5 files, backend + plugin data only

| File | Change |
|------|--------|
| `server/app/agentic_service.py` | Delegated `search_far` to `compliance_matrix.py` |
| `server/app/compliance_matrix.py` | Multi-term scoring for FAR search |
| `server/app/strands_agentic_service.py` | Added `compliance_matrix` tool + fast-path prompt |
| `eagle-plugin/data/far-database.json` | Added FAR 16.5 entries |
| `eagle-plugin/data/thresholds.json` | Updated to FY2025 values |

**`feat/copilotkit-agui`** — 57 files (largest branch)

| Area | Changes |
|------|---------|
| Frontend | CopilotKit chat-v2 page, AG-UI protocol proxy, activity panel enhancements, tool-use display, DNA spinner, agent colors |
| Backend | AG-UI adapter (`agui_adapter.py`), `main.py` CopilotKit routes, streaming enhancements |
| Docs | 5 new Excalidraw diagrams + PNGs, chat UI recommendations report |
| Tests | Acquisition package spec, document pipeline test, feedback store test |
| .claude | Excalidraw skill overhaul, diagram hooks, new browser test skills |

**`feat/sse-telemetry`** — 51 files (subset of copilotkit)

| Area | Changes |
|------|---------|
| Frontend/Backend | Same streaming changes as `copilotkit-agui`, minus the AG-UI adapter |
| Docs / Tests / .claude | Same docs, tests, and `.claude` changes as copilotkit |

> Note: `feat/sse-telemetry` appears to be a parent/precursor of `feat/copilotkit-agui`. Merge order matters.

---

## 2. Alvi Hoque Contributions — PR #19 and PR #20

### PR #19: "fix tools" — March 5 (commit `c1d666b`)

- Fixed `_build_service_tools()` never being called; tools were invisible to the supervisor
- Added `template_registry.py` (204 lines) and `template_service.py` (529 lines)
- 432 lines of new tests

### PR #20: "Canonical Package Document Flow" — March 6

Theme: Consolidate two fragmented document paths into a single source of truth.

**New Backend Modules**

| Module | Lines | Purpose |
|--------|------:|--------|
| `server/app/document_service.py` | 499 | Canonical document lifecycle — create, version, S3 + DynamoDB atomic writes |
| `server/app/package_context_service.py` | 216 | Resolves active package from session |
| `server/app/health_checks.py` | 42 | Health endpoint covering chat, tools, KB |
| `server/app/template_registry.py` | 204 | Template management |
| `server/app/template_service.py` | 529 | Service tool orchestration |

**Migration Script**

`scripts/migrate-chat-s3-docs-to-package-records.py` — 380 lines — backfills existing S3 documents into versioned DynamoDB records.

**Tests**

1,161 lines across 6 new test modules.

**Conflict Risk with Active Branches**

| File | Alvi's Change | Our Change | Risk |
|------|--------------|-----------|------|
| `server/app/strands_agentic_service.py` | +313 lines for package context | Fast-path + streaming modifications | **HIGH** |
| `server/app/main.py` | +152 lines for doc endpoints | CopilotKit AG-UI routes | **HIGH** |
| `server/app/streaming_routes.py` | +56 lines for health | +134 lines for telemetry | MEDIUM |

---

## 3. Frontend Page Inventory — 22 Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `HomePage` | Landing page with feature cards |
| `/chat` | `SimpleChatInterface` | **Primary chat** — sidebar + SSE streaming |
| `/chat-advanced` | `ChatInterface` | Older chat variant with TopNav |
| `/workflows` | `Workflows` | Acquisition package management |
| `/documents` | Documents list | Browse, search, and filter generated docs |
| `/documents/[id]` | Document editor | View, edit, AI refinement, download |
| `/login` | Login form | Cognito auth (no AuthGuard) |
| `/admin` | Admin dashboard | Navigation hub |
| `/admin/agents` | Agent chat | Interactive agent chat with model selector |
| `/admin/analytics` | Analytics | Telemetry, traces, request counts |
| `/admin/costs` | Cost breakdown | Usage reporting by model/user/time |
| `/admin/eval` | Eval use cases | Test runner with diagram visualization |
| `/admin/expertise` | `ExpertiseManager` | How EAGLE learns from actions |
| `/admin/subscription` | Subscription | Usage limits, tier management |
| `/admin/diagrams` | Excalidraw + Chat | AI-powered diagram creation |
| `/admin/kb-reviews` | KB review queue | Approve/reject knowledge base updates |
| `/admin/skills` | Skill management | Browse, create, test, publish skills |
| `/admin/templates` | Template manager | SOW, IGCE, AP template CRUD |
| `/admin/tests` | Test runner | Execute E2E tests with filtering |
| `/admin/traces` | Trace viewer | Inspect spans, tokens, costs, tool calls |
| `/admin/users` | User directory | Roles, contact info, group membership |
| `/admin/workspaces` | Workspace manager | Multi-workspace with entity overrides |

### API Routes — 51 Total

| Group | Count | Coverage |
|-------|------:|---------|
| Core | 5 | health, user, feedback, invoke/chat, trace-logs |
| Sessions | 5 | CRUD + title generation |
| Conversations | 3 | Agent session sync |
| Documents | 5 | list, detail, upload, presign, export |
| Templates | 2 | list, by type |
| Admin | 9 | dashboard, costs, telemetry, users, KB reviews, traces |
| Plugin | 6 | Entity CRUD for agents/skills/templates |
| Workspace | 7 | list, active, activate, overrides |
| Skills | 4 | list, detail, submit, publish |
| Utilities | 5 | tools, diagrams, prompts, CopilotKit proxy |

---

## 4. Excalidraw Diagram Inventory — 25 Unique

All 25 diagrams are committed to `main`.

### Architecture Diagrams — 7 Markdown `.excalidraw.md`

| Date | Subject |
|------|---------|
| 2026-02-20 | AWS Architecture (light) |
| 2026-02-20 | AWS Architecture (dark) |
| 2026-02-26 | CDK Stack Architecture |
| 2026-02-26 | DevBox Deploy |
| 2026-02-26 | EAGLE Application |
| 2026-02-26 | GitHub Actions Deploy |
| 2026-02-26 | Validation & Just Workflow |

### Obsidian Vault Diagrams — 15 Raw `.excalidraw`

| Date | Subject |
|------|---------|
| 2026-02-16 | AI Provider Abstraction |
| 2026-02-16 | Auth Flow |
| 2026-02-16 | AWS Infrastructure |
| 2026-02-16 | Backend Services |
| 2026-02-16 | Bedrock (5 variants) |
| 2026-02-16 | Chat Message Flow |
| 2026-02-16 | Chat V2 Multi-Agent |
| 2026-02-16 | Database Schema |
| 2026-02-16 | Frontend Components |
| 2026-02-16 | NCI OA Agent Comparison |
| 2026-02-16 | System Overview |
| 2026-02-16 | Testing Architecture |
| 2026-02-16 | Tool Execution |
| 2026-02-17 | EAGLE Platform |

### UC Workflow Diagrams — 8 Raw `.excalidraw`

| Date | Use Case |
|------|---------|
| 2026-02-08 | UC01 Complex Agent Subrouting (happy path) |
| 2026-02-08 | UC01 Complex Agent Subrouting (full) |
| 2026-02-08 | UC02 Micro Purchase |
| 2026-02-08 | UC03 Option Exercise |
| 2026-02-08 | UC04 Contract Modification |
| 2026-02-08 | UC05 CO Package Review |
| 2026-02-08 | UC07 Contract Closeout |
| 2026-02-08 | UC09 Score Consolidation |

---

## 5. Commit Timeline — February 1 through March 9, 2026

### Key Milestones

| Date | Milestone | Author |
|------|-----------|--------|
| Feb 8–9 | UC workflow Excalidraw diagrams created | gblack686 |
| Feb 16 | Obsidian vault — 15 architecture diagrams committed | gblack686-revstar |
| Feb 20 | AWS architecture diagrams (light + dark) | gblack686-revstar |
| Feb 23–27 | Strands Agents SDK migration — largest feature block | Black |
| Feb 26 | CDK + deployment architecture diagrams | Black |
| Mar 2–3 | SDK migration complete; session persistence wired | Black |
| Mar 5 | 7 PRs merged in one day — stabilization sprint | Black + Alvi |
| Mar 5 | PR #19: fix tools — service tools wired to supervisor | Alvee Hoque |
| Mar 5 | Model upgrade to Claude Sonnet 4.6 | Black |
| Mar 6 | PR #20: Canonical Package Document Flow | Alvee Hoque |
| Mar 6 | `feat/sse-telemetry` — activity panel + streaming | Black |
| Mar 6 | `feat/agui` — CopilotKit + AG-UI integration | Black |
| Mar 8 | `fix/fast-path-kb-tools` — FAR routing + FY2025 thresholds | Black |

### Author Summary — ~298 Commits

| Author | Commits | Primary Areas |
|--------|--------:|--------------|
| Black | 111 | Strands migration, CI/CD, streaming, model upgrades |
| gblack686 | 74 | Eval, smoke tests, CDK infrastructure |
| gblack686-revstar | 54 | Playwright tests, AWS SSO, Excalidraw diagrams |
| Alvee Hoque | 27 | Document viewer, package flow, tool dispatch |
| blackga-nih | 15 | PR merges, CI fixes |
| hoquemi | 6 | PR merges |
| Rene Pineda | 5 | Contributions |

### PR Merge History

| PR | Title | Author | Date |
|----|-------|--------|------|
| #20 | Canonical package document flow | Alvee Hoque | Mar 6 |
| #19 | Fix tools | Alvee Hoque | Mar 5 |
| #17 | Auto-sync ALB target group | Black | Mar 5 |
| #16 | Fix feedback field mismatch | Black | Mar 5 |
| #15 | SSE keepalive for ALB timeout | Black | Mar 5 |
| #13 | Fix frontend build errors | Black | Mar 5 |
| #12 | Hub sync 20260305 | Black | Mar 5 |

---

## 6. Merge Strategy Recommendation

### Recommended Order — Sequential (Lowest Risk)

| Step | Branch | Rationale |
|------|--------|-----------|
| 1 | `fix/fast-path-kb-tools` | 5 files, isolated KB/threshold changes, minimal conflict surface |
| 2 | `feat/sse-telemetry` | Streaming foundation that `copilotkit-agui` builds on |
| 3 | `feat/copilotkit-agui` | Largest branch; depends on both above; adds AG-UI layer |

### Pre-Merge Checklist (repeat for each branch)

- [ ] Rebase branch onto latest `main` (includes Alvi's PR #20)
- [ ] Run `ruff check app/` — no errors
- [ ] Run `npx tsc --noEmit` — no errors
- [ ] Run `python -m pytest tests/ -v` — Alvi's new test modules pass
- [ ] Test tool dispatch end-to-end (fast-path + deep-path)

### Critical Conflict Files

| File | Conflict Type | Branches Involved |
|------|--------------|------------------|
| `server/app/strands_agentic_service.py` | 3-way merge | fast-path, copilotkit, sse-telemetry + Alvi PR #20 |
| `server/app/agentic_service.py` | 3-way merge | fast-path, copilotkit, sse-telemetry |
| `server/app/streaming_routes.py` | 2-way merge | copilotkit, sse-telemetry + Alvi PR #20 |
| `server/app/main.py` | 2-way merge | copilotkit + Alvi PR #20 |

---

## 7. Action Items

| Priority | Item | Owner |
|----------|------|-------|
| HIGH | Create PR for `fix/fast-path-kb-tools` → `main` | Black |
| HIGH | Rebase `feat/sse-telemetry` onto `main` after fast-path merge | Black |
| HIGH | Rebase `feat/copilotkit-agui` onto `sse-telemetry` | Black |
| HIGH | Resolve 3-way conflict in `strands_agentic_service.py` | Black + Alvi |
| MEDIUM | Review `document_service.py` for streaming integration points | Black + Alvi |
| MEDIUM | Run full test suite after each branch merge | Black |
| LOW | Update Excalidraw diagrams to reflect post-Strands, post-AG-UI architecture | Black |
| LOW | Delete merged stale branches: `fix/auto-sync-alb-target`, `fix/feedback-field-mismatch`, `fix/streaming-keepalive`, `fix/frontend-build-errors` | Black |

---

*Scribe | 2026-03-09T12:00:00Z | Format: markdown | Type: report*
