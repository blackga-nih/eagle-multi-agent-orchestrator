# TAC Apps Catalog

> Reference implementations from TAC methodology projects. Each app demonstrates patterns from a specific lesson.

**Source**: `C:\Users\gblac\OneDrive\Desktop\tac\{project}\apps\{app}`

---

## Quick Reference

| # | Lesson | Project | Apps | Key Pattern |
|---|--------|---------|------|-------------|
| 15 | Hooks Mastery | claude-code-hooks-mastery | 3 | Hook lifecycle + sub-agents |
| 16 | Multi-Agent Observability | claude-code-hooks-multi-agent-observability | 3 | Real-time event streaming |
| 17 | Damage Control | claude-code-damage-control | 1 | PreToolUse defense-in-depth |
| 18 | Install and Maintain | install-and-maintain | 2 | DAI pattern (Det + Agentic + Interactive) |
| 19 | SSVA | agentic-finance-review | 1 | Specialized Self-Validating Agents |
| 20 | Beyond MCP | beyond-mcp | 4 | MCP vs CLI vs Scripts vs Skills |
| 21 | Browser Automation | bowser | 0 | Commands/skills only (no apps/) |
| 22 | Agent Sandboxes | agent-sandboxes | 6 | E2B isolated sandbox forks |
| 23 | Fork Repository Skill | fork-repository-skill | 0 | Skill only (no apps/) |
| 24 | R&D Framework | rd-framework-context-window-mastery | 3 | Context window optimization |
| 25 | Prompt Formats | seven-levels-agentic-prompt-formats | 1 | 7-level prompt escalation |
| 26 | O-Agent Orchestration | multi-agent-orchestration-the-o-agent | 2 | Production orchestrator platform |
| 27 | Domain-Specific Agents | building-domain-specific-agents | 8 | Progressive agent specialization |
| -- | Agent Experts | agent-experts | 3 | ACT-LEARN-REUSE adaptive agents |
| -- | Orchestrator with ADWs | orchestrator-agent-with-adws | 7 | Multi-app orchestration showcase |

**Total**: 44 apps across 13 projects

---

## Lesson 15: Hooks Mastery

**Source**: `Desktop/tac/claude-code-hooks-mastery/apps/`
**Pattern**: Master all 13 Claude Code hook lifecycle events for deterministic/non-deterministic agent control.

### `hello.py` / `hello.ts`
**Type**: Script | **Stack**: Python / TypeScript

Minimal hook examples in both languages. Starting point for understanding hook event payloads and the exit code protocol (0=allow, 2=block, JSON=ask).

### `task-manager`
**Type**: Fullstack | **Stack**: Bun + TypeScript + SQLite

A CLI task manager (`add`, `list`, `complete`, `delete`, `stats`) that serves as the **target app** for the hooks mastery project. The parent repo wraps this app with demonstrations of all 13 hook events, UV single-file hook scripts, sub-agents, team-based validation, and the meta-agent pattern.

```bash
cd apps/task-manager && bun run src/index.ts
```

---

## Lesson 16: Multi-Agent Observability

**Source**: `Desktop/tac/claude-code-hooks-multi-agent-observability/apps/`
**Pattern**: Capture hook events across concurrent agents, stream to dashboard for real-time observability.

### `server`
**Type**: Backend | **Stack**: Bun + TypeScript + SQLite

Event capture server. Receives hook events via HTTP POST from multiple concurrent Claude Code agents, persists to SQLite, and broadcasts to all connected dashboard clients via WebSocket. Supports HITL (Human-in-the-Loop) response routing back to agents.

- `POST /events` — ingest hook events
- `GET /filter-options` — session/agent metadata for filtering
- WebSocket fan-out to all connected dashboards
- Theme CRUD endpoints (create, update, export, import)

```bash
cd apps/server && bun install && bun run index.ts
```

### `client`
**Type**: Frontend | **Stack**: Vue 3 + Vite + TypeScript

Real-time observability dashboard. Connects to the server via WebSocket and displays live hook events from all running agents.

- Live event stream with session/agent filtering
- Connection status indicator, event count
- HITL response UI for sending commands back to agents
- Dark/light theme toggle, responsive mobile layout

```bash
cd apps/client && bun install && bun run dev
```

### `demo-cc-agent`
**Type**: Config | **Stack**: Claude Code hooks (Python)

A preconfigured Claude Code agent demonstrating hooks integration (PreToolUse, PostToolUse, blocking, TTS). Used as the source of hook events that flow into the server/client pipeline.

**Full architecture**: `Claude Agents -> Hook Scripts -> HTTP POST -> Bun Server -> SQLite -> WebSocket -> Vue Client`

---

## Lesson 17: Damage Control

**Source**: `Desktop/tac/claude-code-damage-control/apps/`
**Pattern**: PreToolUse hook defense-in-depth — block dangerous commands, protect sensitive files.

### `mock_db`
**Type**: Utility | **Stack**: Python + SQLite

Mock database system used as a test target for PreToolUse guard hooks. The parent project's hooks demonstrate pattern-based blocking rules (exit 0=allow, exit 2=block, JSON=ask) that protect this database and other sensitive files from dangerous bash/edit/write operations.

---

## Lesson 18: Install and Maintain

**Source**: `Desktop/tac/install-and-maintain/apps/`
**Pattern**: DAI (Deterministic + Agentic + Interactive) — three progressive execution modes for living documentation.

### `backend`
**Type**: Backend | **Stack**: Python + FastAPI + SQLite

A "Starter API" with task CRUD endpoints that serves as the **target app** for the DAI pattern. Three run modes via the parent Justfile:
- `just cldi` — Deterministic: hook-only install, CI/CD friendly
- `just cldii` — Agentic: hook + prompt reads install log, analyzes, reports
- `just cldit` — Interactive: hook + AskUserQuestion, adapts to user answers

Includes `init_db.py` for SQLite setup, CORS for frontend at `:5173`.

```bash
cd apps/backend && uv run uvicorn main:app --reload
```

### `frontend`
**Type**: Frontend | **Stack**: Vue 3 + Vite + TypeScript

Companion frontend for the Starter API. SFC (Single File Component) template paired with the backend to demonstrate full-stack DAI install flows.

```bash
cd apps/frontend && npm install && npm run dev
```

---

## Lesson 19: SSVA (Specialized Self-Validating Agents)

**Source**: `Desktop/tac/agentic-finance-review/apps/`
**Pattern**: Focused Agent + Scoped Hooks = Trusted Automation with block/retry self-correction.

### `agentic-finance-review`
**Type**: Data Pipeline | **Stack**: Python + Claude Code hooks

Processes raw bank CSV exports (checking, savings, credit card) through a multi-agent pipeline into structured financial reports. Each agent has **specialized hooks embedded per-agent** (not global), making this the canonical SSVA example.

**Agent pipeline**:
1. CSV agents — parse and normalize bank exports, validated by `csv-validator` hook (checks column structure)
2. Build agents — merge year-to-date data, validated by `ruff-validator` and `ty-validator` hooks
3. Report agents — generate HTML reports, validated by `html-validator` hook
4. Graph agents — produce balance visualizations, validated by `graph-validator` hook

**Key insight**: Each hook fires only for its agent's operations. When a hook blocks (`exit 2`), the block reason becomes the agent's next correction task — this is the block/retry self-correction loop.

**Produces**: Merged YTD CSVs, normalized balance data, HTML reports, balance graphs.

---

## Lesson 20: Beyond MCP

**Source**: `Desktop/tac/beyond-mcp/apps/`
**Pattern**: Four approaches to building reusable agent toolsets — MCP, CLI, file scripts, skills — compared side by side.

### `1_mcp_server`
**Type**: MCP Server | **Stack**: Python + FastMCP

Kalshi prediction market MCP server. Wraps the CLI (app #2) and exposes 15 MCP tools for LLMs. Tools cover markets, prices, orderbooks, trades, search, events, and series. No auth required (read-only public API). Calls CLI via subprocess.

```bash
cd apps/1_mcp_server && uv sync && uv run server.py
```

### `2_cli`
**Type**: CLI | **Stack**: Python + httpx

Direct HTTP API client for Kalshi in a single 552-line file. 13 commands with dual output modes (human-readable or `--json`). Smart caching for fast repeated searches. This is the **foundation layer** — the MCP server wraps it, the skill references it.

```bash
cd apps/2_cli && uv sync && uv run kalshi markets --limit 10
```

### `3_file_system_scripts`
**Type**: Scripts | **Stack**: Python (zero dependencies)

Self-contained, zero-dependency scripts for Kalshi data. Demonstrates the "file system scripts" approach — no installation, no SDK, just drop a `.py` file and run it. Progressive disclosure pattern.

### `4_skill`
**Type**: Skill | **Stack**: SKILL.md

Claude Code skill wrapping the Kalshi tools. Auto-detected by Claude Code when relevant keywords appear. Demonstrates the "skill" approach — minimal token cost, context-preserving, agent-native.

**Comparison takeaway**: MCP adds context-loss overhead at scale. CLI gives full control. File scripts need zero setup. Skills integrate natively.

---

## Lesson 22: Agent Sandboxes

**Source**: `Desktop/tac/agent-sandboxes/apps/`
**Pattern**: E2B isolated sandbox forks for parallel agent execution with full environment control.

### `sandbox_cli`
**Type**: CLI | **Stack**: Python + Click + E2B SDK

Full-featured E2B sandbox management CLI. Unified `exec` command for all operations.

- `sbx init` — create sandbox, save ID to `.sandbox_id`
- `sbx files ls/read/write/upload/download` — SDK-based file operations with binary support
- `sbx exec` — run shell commands in sandbox
- `sbx kill` — terminate sandbox
- Custom template support (`--template claude-code`)
- Environment variable injection

```bash
cd apps/sandbox_cli && uv sync && uv run sbx --help
```

### `sandbox_fundamentals`
**Type**: Examples | **Stack**: Python + E2B SDK

13 progressive numbered scripts teaching E2B SDK patterns:

| Script | Topic |
|--------|-------|
| `01-04` | Basic sandbox, file listing, file ops, command execution |
| `05-08` | Env vars, background commands, sandbox reuse, pause/resume |
| `09` | Claude Code agent running inside a sandbox |
| `10-12` | Package installation, git operations, custom templates |
| `13` | Expose web servers (simple HTTP + Vite/Vue) from sandbox |

```bash
cd apps/sandbox_fundamentals && uv run 01_basic_sandbox.py  # requires E2B_API_KEY
```

### `sandbox_mcp`
**Type**: MCP Server | **Stack**: Python + FastMCP

MCP server exposing 19 tools that map 1:1 to `sandbox_cli` commands. Enables LLMs to create, manage, and operate E2B sandboxes through the MCP protocol. Supports text and binary file operations.

```bash
cd apps/sandbox_mcp && uv sync && uv run server.py
```

### `sandbox_workflows`
**Type**: CLI | **Stack**: Python + UV + E2B SDK

Parallel multi-agent git experimentation system. Forks a git repo into 1-100 parallel E2B sandboxes, each with an independent Claude Code agent on a unique branch.

- Thread-safe logging (one log file per fork)
- Model selection per fork (Opus / Sonnet / Haiku)
- 6 hook types for full observability
- Hook-based path security preventing local filesystem access
- GitHub token support for automated push/PR
- Cost tracking per fork and total
- Slash commands: `/plan`, `/build`, `/wf_plan_build`

```bash
cd apps/sandbox_workflows && uv sync && cp .env.sample .env && uv run python main.py
```

### `cc_in_sandbox`
**Type**: Script | **Stack**: Python + E2B SDK

Single script demonstrating how to run Claude Code agents inside E2B sandbox isolation. The starting point for understanding agent-sandbox integration.

### `sandbox_agent_working_dir`
**Type**: Template | **Stack**: —

Empty working directory template used as the initial filesystem for sandbox agents.

---

## Lesson 24: R&D Framework — Context Window Mastery

**Source**: `Desktop/tac/rd-framework-context-window-mastery/apps/`
**Pattern**: Measure -> Reduce -> Delegate -> Agentic — find the optimal context sweet spot.

### `cc_ts_wrapper`
**Type**: CLI | **Stack**: Bun + TypeScript

TypeScript wrapper for Claude Code that enables reusable, named prompt commands with pre-configured system prompts, tool allowlists, and max-turn settings.

- Register named commands: `/analyze`, `/refactor` (extensible)
- Ad-hoc prompts with `--prompt`
- Reusable prompt configs with variable substitution
- CLI flags: `--command`, `--prompt`, `--max-turns`, `--system-prompt`, `--tools`, `--list`
- Built on `core.ts` with `register_prompt`, `adhoc_prompt`, `reusable_prompt`

```bash
cd apps/cc_ts_wrapper && bun install && bun run cli.ts --list
bun run cli.ts --command /analyze --prompt "look at src/"
```

### `hello_cc_1.ts` / `hello_cc_2.ts`
**Type**: Script | **Stack**: TypeScript

Minimal context engineering examples showing the difference between bloated context (example 1) and optimized context (example 2). Used to demonstrate the R&D framework's "Measure" and "Reduce" phases.

---

## Lesson 25: Seven Levels of Agentic Prompt Formats

**Source**: `Desktop/tac/seven-levels-agentic-prompt-formats/apps/`
**Pattern**: Match prompt complexity to task complexity across 7 escalating levels.

### `prompt_tier_list`
**Type**: Frontend | **Stack**: Vue 3 + Vite + TypeScript

Interactive 2D drag-and-drop tier list for ranking prompt engineering components.

- **5x5 grid** with two axes: skill level (Beginner -> Expert) and usefulness (Useful -> Useless)
- **Three entity types**: H1 Headers (dark), H2 Sections (purple), Prompt Format files (sky blue)
- **19 prompt sections** + **7 prompt format files** (high_level, workflow, higher_order, control_flow, delegate, agent, skill)
- Purple gradient intensifies toward Expert + Useful quadrant
- Persistent state in localStorage, reset button

```bash
cd apps/prompt_tier_list && npm install && npm run dev
```

---

## Lesson 26: Multi-Agent Orchestration — The O-Agent

**Source**: `Desktop/tac/multi-agent-orchestration-the-o-agent/apps/`
**Pattern**: Central orchestrator + specialized workers + shared state store with full observability.

### `orchestrator_3_stream`
**Type**: Fullstack | **Stack**: FastAPI + Vue 3 + PostgreSQL + WebSocket

Production-ready web interface for multi-agent orchestration. Chat with a natural-language orchestrator that creates, dispatches to, and monitors specialized Claude Code subagents in real time.

- **3-column UI**: agents panel (status, model), events panel (task dispatch, completions), chat panel (streaming responses)
- **Real-time WebSocket** streaming of agent responses with typing indicators and auto-scroll
- **PostgreSQL persistence** for chat history, sessions, agent state
- **Cost tracking**: tokens used + USD per interaction
- **CLI params**: `--session` (resume), `--cwd` (working directory)
- **Tested**: 5/5 pytest backend tests, E2E tested with Playwright MCP

```bash
# Backend
cd apps/orchestrator_3_stream/backend && uv run uvicorn main:app --port 8000
# Frontend
cd apps/orchestrator_3_stream/frontend && npm run dev  # Port 5173
```

### `orchestrator_db`
**Type**: Backend | **Stack**: Python + SQLAlchemy

Shared database schema, Pydantic models, and migration runner for all orchestrator apps. Defines the table structure for sessions, messages, agents, and cost records.

```bash
cd apps/orchestrator_db && uv run python run_migrations.py
```

---

## Lesson 27: Building Domain-Specific Agents

**Source**: `Desktop/tac/building-domain-specific-agents/apps/`
**Pattern**: Progressive agent specialization — 8 levels from "pong" to production fullstack agent.

### `custom_1_pong_agent`
**Type**: Agent (CLI) | **Stack**: Python + TS + Claude Agent SDK | **Level**: 0.1

The simplest possible agent. Responds with "pong" to any input. Dual implementation in Python and TypeScript. Starting point for understanding the Claude Agent SDK interaction model.

```bash
uv run python pong_agent.py  # or: bun run pong_agent.ts
```

### `custom_2_echo_agent`
**Type**: Agent (CLI) | **Stack**: Python + Claude Agent SDK | **Level**: 1.0

Custom tool creation with parameters. Agent echoes user input back. Demonstrates how to define and register a tool with the SDK.

### `custom_3_calc_agent`
**Type**: Agent (REPL) | **Stack**: Python + Claude Agent SDK | **Level**: 1.2

Interactive calculator with true session continuity. Custom math tools (trig, logarithms, precision control, safe eval), unit conversions (length, weight, temperature), Rich terminal UI, session cost tracking. Uses `resume=session_id` for conversation persistence.

```bash
cd apps/custom_3_calc_agent && uv sync && uv run python calc_agent.py
```

### `custom_4_social_hype_agent`
**Type**: Agent (CLI) | **Stack**: Python + Claude Agent SDK + Bluesky API | **Level**: 1.3

Real-time social media monitoring. Connects to the Bluesky WebSocket firehose, filters posts by keywords, uses the Claude Agent SDK for sentiment analysis and summarization. Outputs to CSV with continuous appending. Rich CLI progress tracking.

```bash
cd apps/custom_4_social_hype_agent && uv sync && uv run python social_hype_agent.py coding python
```

### `custom_5_qa_agent`
**Type**: Agent (REPL) | **Stack**: Python + Claude Agent SDK | **Level**: 2.0

Codebase Q&A agent with parallel Task subagents, controlled tool access, and MCP integration. Demonstrates agent-to-agent delegation and restricted tool scoping. Includes inline hooks testing with pytest.

### `custom_6_tri_copy_writer`
**Type**: Fullstack | **Stack**: FastAPI + Vue 3 + Claude Agent SDK | **Level**: 3.0

Professional copywriting agent generating 1-10 variations per request. Structured JSON responses with `primary_response` + `multi_version_copy_responses[]`. Drag-and-drop file context (text/markdown), copy-to-clipboard per variation, real-time cost tracking (duration + API cost).

```bash
# Backend: uv run uvicorn main:app --port 8000 --versions 3
# Frontend: npm run dev  # Port 5173
```

### `custom_7_micro_sdlc_agent`
**Type**: Fullstack | **Stack**: FastAPI + Vue 3 + SQLite + Claude Agent SDK | **Level**: 4.0

Kanban board orchestrating a mini SDLC through three specialized agents: **Planner** (creates plan), **Builder** (implements), **Reviewer** (reviews). Real-time WebSocket updates with agent message tracking (tool calls, thinking). Model choice per ticket (Sonnet for speed, Opus for quality). SQLite persistence.

```bash
# Backend: uv run uvicorn main:app --reload
# Frontend: npm run dev
```

### `custom_8_ultra_stream_agent`
**Type**: Fullstack | **Stack**: FastAPI + Vue 3 + SQLite + Claude Agent SDK | **Level**: 5.0

Dual-agent system for real-time JSONL log stream processing:
- **Stream Agent**: continuous JSONL processing in batches, auto-summarization, severity classification, high-severity alerts, context window management for infinite operation
- **Inspector Agent**: natural language queries against the processed data, user-specific investigation, pattern detection, team notifications (Engineering & Support)

Dual-panel Vue.js interface, real-time stats via WebSocket, session continuity with resume.

```bash
# Backend: uv run uvicorn main:app --reload
# Frontend: npm run dev
```

---

## Bonus: Agent Experts

**Source**: `Desktop/tac/agent-experts/apps/`
**Pattern**: ACT-LEARN-REUSE as a runtime pattern — agents that learn from user behavior and improve recommendations.

### `nile`
**Type**: Fullstack | **Stack**: Vue 3 + FastAPI + SQLAlchemy + SQLite + Claude Agent SDK

"Nile Adaptive Shopping" — AI-powered shopping app demonstrating the Product Agent Expert pattern:
- **ACT**: User views products, adds to cart, checks out (100 seeded products via `seed_data.py`)
- **LEARN**: System updates user expertise as JSONB in the database after each action
- **REUSE**: Agent reads expertise to generate a personalized home page with 7 adaptive UI component types

Configurable model (defaults to Haiku for speed).

```bash
cd apps/nile/server && uv sync && uv run python seed_data.py
uv run uvicorn src.main:app --port 8000
# Frontend: npm install && npm run dev
```

### `orchestrator_3_stream`
**Type**: Fullstack | **Stack**: FastAPI + Vue 3 + PostgreSQL

Same production orchestrator as Lesson 26. Shared codebase demonstrating cross-project reuse.

### `orchestrator_db`
**Type**: Backend | **Stack**: Python + SQLAlchemy

Shared database schema for orchestrator apps. Same as Lesson 26.

---

## Bonus: Orchestrator with ADWs

**Source**: `Desktop/tac/orchestrator-agent-with-adws/apps/`
**Pattern**: Multi-app orchestration showcase — an orchestrator agent building diverse apps as demonstrations.

### `orchestrator_3_stream`
**Type**: Fullstack | **Stack**: FastAPI + Vue 3 + PostgreSQL

Production orchestrator variant. Same core as Lesson 26.

### `orchestrator_db`
**Type**: Backend | **Stack**: Python + SQLAlchemy

Shared database schema. Same as Lesson 26.

### `pomodoro_timer`
**Type**: CLI | **Stack**: Python + Click + Rich + SQLite

Minimal Pomodoro timer with beautiful terminal UI. Used as a **target app built by the orchestrator agent** to demonstrate ADW-driven development.

- `start` — 25-min default session (configurable via `--duration`)
- Full-width Rich panels, colored progress bars, countdown display
- Cross-platform desktop notifications on completion
- Persistent SQLite session tracking
- `stats` — total sessions, focus time, recent activity
- Graceful Ctrl+C cancel

```bash
cd apps/pomodoro_timer && uv run python main.py start
uv run python main.py start --duration 45
uv run python main.py stats
```

### `interactive_file_tree`
**Type**: Frontend | **Stack**: Vue 3 + TypeScript + Pinia + Vite

Interactive file tree component **built by the orchestrator agent**. Complex frontend demonstrating agent capability on UI tasks.

- Hierarchical file/folder navigation with expand/collapse
- Drag-and-drop reorganization
- CRUD: create files/folders, delete (Delete key support)
- File type icons via Lucide (auto-assigned by extension)
- Description panel for selected file details
- Export/import tree as JSON
- Responsive, system-preference dark mode

```bash
cd apps/interactive_file_tree && ./start_fe.sh  # Port 5180
```

### `markdown_preview`
**Type**: Frontend | **Stack**: Vue 3 + Vite + TypeScript

Browser markdown renderer with marked.js and highlight.js syntax highlighting. Built by the orchestrator agent as a utility app.

### `nile`
**Type**: Frontend | **Stack**: HTML/JS

MTG cards rendering demo. Visual showcase of product rendering capabilities.

### `simple-html-file`
**Type**: Frontend | **Stack**: HTML/CSS

Modern static website with hero section and two-column layout using CSS custom properties. Minimal orchestrator demo.

---

## Technology Stack Summary

| Technology | Count | Used In |
|------------|-------|---------|
| Python + FastAPI | 8 | L18, L19, L20, L22, L26, Agent Experts, Orch-ADW |
| Vue 3 + Vite + TS | 7 | L15, L16, L18, L25, L26, Agent Experts, Orch-ADW |
| Claude Agent SDK | 8 | L27 (all custom agents), Agent Experts (nile) |
| PostgreSQL | 4 | L26, Agent Experts, Orch-ADW orchestrators |
| SQLite | 5 | L15, L17, L27 (micro-sdlc, ultra-stream), Orch-ADW (pomodoro) |
| E2B Sandboxes | 6 | L22 (all sandbox apps) |
| Bun + TypeScript | 3 | L16 (server), L24 (cc_ts_wrapper), L15 (task-manager) |
| MCP / FastMCP | 2 | L20 (kalshi), L22 (sandbox) |
| WebSocket | 5 | L16, L26, L27 (micro-sdlc, ultra-stream), Agent Experts |

---

## Using This Catalog

### Browse by lesson
Each section maps to a post-14 lesson in `tac-learning-expertise.md`.

### Navigate to source
All source paths are relative to `C:\Users\gblac\OneDrive\Desktop\tac\`.

### Create symlinks (optional)
```bash
# Windows (admin PowerShell)
New-Item -ItemType SymbolicLink -Path "tac-experts-plugin/apps/lesson-26-o-agent" -Target "C:\Users\gblac\OneDrive\Desktop\tac\multi-agent-orchestration-the-o-agent\apps"

# Git Bash / WSL
ln -s "/c/Users/gblac/OneDrive/Desktop/tac/multi-agent-orchestration-the-o-agent/apps" "tac-experts-plugin/apps/lesson-26-o-agent"
```

### Run an app
```bash
cd /c/Users/gblac/OneDrive/Desktop/tac/building-domain-specific-agents/apps/custom_1_pong_agent
uv run python pong_agent.py
```

### Progressive learning path
Start with Lesson 27's agents in order (custom_1 through custom_8) for a structured ramp-up from simple to production-grade agents.
