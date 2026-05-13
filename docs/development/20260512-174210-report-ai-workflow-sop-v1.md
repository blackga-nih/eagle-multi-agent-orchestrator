# EAGLE — AI-Leveraged Workflow SOP

**Audience**: NCI EAGLE team (devs + PMs + leadership) — two reading tracks per section
**Author**: Greg Black
**Date**: 2026-05-12

---

> **How to read this document.** Every section opens with a 2-3 sentence **TL;DR** for leadership, followed by a **Deep-Dive** subsection for devs/ops. If you only have 5 minutes, read the TL;DRs and skip to §7 (the time-savings table). Glossary in §10.

---

## §1 — Executive Narrative

### TL;DR
Our team builds **EAGLE**, the multi-tenant AI acquisition assistant. EAGLE is one of two AI layers I use every day. The second layer is **how I operate EAGLE** — Claude Code + 15 expert domains + 50+ named skills + a spec-driven plan→build→review→ship loop + 5 self-improving overnight flywheels. The two compound: faster code → faster EAGLE → faster team output. This document is the playbook.

### Deep-Dive
The team sees EAGLE outputs (chat answers, generated SOWs/IGCEs/APs, dashboards) but doesn't see the *system that produces them*. That system has three observable surfaces:

1. **Application layer** (what users touch): EAGLE the deployed product — supervisor agent + 9 specialists, Cognito-gated, SSE-streamed.
2. **Operational layer** (the Justfile): one entry point for dev/test/deploy/eval — `just registry` is the discovery surface.
3. **Cognitive layer** (Claude Code + experts + skills): the AI-native tooling that *amplifies the human operator*.

The keystone insight: **the cognitive layer compounds.** Each new expert mental model (`expertise.md`), each new named skill, each nightly triage report makes tomorrow's session faster than today's.

```
┌────────────────────────────────────────────────────────────┐
│  APPLICATION LAYER — EAGLE the product                     │
│  Supervisor → 9 specialists → SOWs/IGCEs/APs/J&As          │
└─────────────────────────┬──────────────────────────────────┘
                          │ produces logs, traces, feedback
                          ▼
┌────────────────────────────────────────────────────────────┐
│  OPERATIONAL LAYER — Justfile (75 recipes)                 │
│  dev-local • smoke • deploy • eval • langfuse-* • registry │
└─────────────────────────┬──────────────────────────────────┘
                          │ commands invoked by humans + agents
                          ▼
┌────────────────────────────────────────────────────────────┐
│  COGNITIVE LAYER — Claude Code + experts + skills          │
│  /plan /build /review /ship /triage /mvp1-eval /handoff    │
│  /experts:{aws,backend,frontend,eval,...}:{plan|question}  │
└────────────────────────────────────────────────────────────┘
```

---

## §2 — Application Layer: What EAGLE Does Today

### TL;DR
EAGLE is a multi-tenant FastAPI + Next.js app that helps NCI contracting officers navigate federal procurement. A supervisor agent routes user questions to 9 specialist agents (legal, market intel, policy, compliance, tech, finance, public interest). The app produces ~10 document types (SOW, IGCE, AP, J&A, EVAL, 508, COR, CTJ, FUND) and is tier-gated (basic/advanced/premium subscription tiers).

### Deep-Dive

**Architecture flow** (file references at the bottom):
```
User → Next.js (chat-simple/) → POST /api/chat (FastAPI)
                                       ↓
                              strands_agentic_service.py
                                       ↓
                              Supervisor agent (Strands SDK + Bedrock)
                                       ↓
                ┌──────────────────────┴──────────────────────┐
                ↓                  ↓                  ↓        ↓
        legal-counsel      market-intelligence   policy-*   tech-translator
        compliance-strategist  financial-advisor  public-interest
                                       ↓
                              Tool dispatch (oa-intake, document-generator,
                                             ingest-document, compliance,
                                             tech-review, s3-knowledge-base-sync)
                                       ↓
                              SSE stream → use-agent-stream.ts → chat UI
```

**Specialist roster** (`eagle-plugin/agents/`):

| Specialist | Domain | When supervisor routes here |
|---|---|---|
| legal-counsel | FAR authority, J&A justifications, protest procedures | Legal questions, J&A drafts |
| market-intelligence | Vendor research, BPA/IDIQ/GSA Schedule lookups | Sourcing, market research |
| policy-supervisor | Workflow coordination (orchestrator peer) | Multi-step intake flows |
| policy-librarian | FAR/HHS/OAM document fetching + citation | Regulation lookups |
| policy-analyst | Acquisition method determination | Method selection |
| compliance-strategist | Checklist enforcement, threshold validation | PMR/compliance gates |
| tech-translator | IT security requirements, FedRAMP/FISMA | Cloud/IT procurement |
| financial-advisor | Cost estimation, pricing, indirect costs | IGCE drafts |
| public-interest | Public benefit, minority/8(a) set-asides | Set-aside analysis |

**Document outputs**:
AP (Acquisition Plan) · SOW (Statement of Work) · IGCE (Independent Government Cost Estimate) · J&A (Justification & Approval) · EVAL (Evaluation Plan) · SEC (Security) · 508 (Accessibility) · COR (Contracting Officer's Representative) · CTJ (Cost/Technical Justification) · FUND (Funding documentation)

**Key files** (for the curious):
- `eagle-plugin/plugin.json` — active agents + skills manifest
- `eagle-plugin/agents/*/agent.md` — agent prompts (source of truth)
- `server/app/strands_agentic_service.py` — Strands SDK supervisor + subagent orchestration
- `server/app/streaming_routes.py` — SSE endpoint + fallback to direct Anthropic API
- `server/app/stream_protocol.py` — `MultiAgentStreamWriter` (SSE event shape)
- `client/components/chat-simple/simple-chat-interface.tsx` — active chat UI
- `client/hooks/use-agent-stream.ts` — frontend SSE consumer

---

## §3 — Operational SOP: The Justfile

### TL;DR
**One file orchestrates 75 commands.** Run `just --list` to see them all, `just registry` for a categorized map. 12 recipes cover 80% of daily work. The `Justfile` is the canonical operating surface for both humans and AI agents picking up this codebase.

### Deep-Dive

**The daily-driver 12** — print this, tape it to your monitor:

| Recipe | What it does | When |
|---|---|---|
| `just dev-local` | Local backend + frontend, hot reload, kills stale processes first | Start every day |
| `just lint` | ruff + tsc | Before commit |
| `just test` | Backend pytest in docker | Before commit |
| `just smoke` | Playwright integration (base / mid / full levels) | Before push |
| `just dev-smoke` | Stack + smoke one-shot | Quick sanity |
| `just deploy-ci main` | Trigger GH Actions deploy | Ship to dev |
| `just dev-smoke-deployed <scenario>` | Post-deploy validation via EC2 devbox | After deploy |
| `just eval` / `just eval-aws` | 142-test eval suite (full / AWS subset) | After agent changes |
| `just status` | ECS health + ALB URLs | Quick check |
| `just langfuse-report-today` | Daily analytics rollup → HTML | Standup prep |
| `just check-aws` | 8-resource AWS health probe | Diagnose AWS issues |
| `just kill-stale` | Emergency port cleanup | When dev-local hangs |

**The new discovery surface** (added 2026-05-12 as part of this initiative):

```
just registry        # Categorized map of recipes, skills, experts, flywheels, source files
just docs            # Documentation tree map
just smoke-list      # Available post-deploy smoke scenarios
just handoff agent   # Onboarding checklist for a new AI agent
just handoff human   # Bundle env for a new human (invokes /claude-handoff)
```

If you forget a command, **run `just registry` first.** It exists specifically so the next dev/agent doesn't have to grep this repo to figure out what's available.

**Validation Ladder** (referenced everywhere in this codebase):

| Level | What | Time | Required for |
|---|---|---|---|
| **L1** | Lint (`ruff check` + `npx tsc --noEmit`) | ~30s | Every commit |
| **L2** | Unit tests (`pytest tests/`) | ~2 min | Backend logic changes |
| **L3** | Integration smoke (`just smoke mid`) | ~25s | Frontend UI changes |
| **L4** | CDK synth (`npx cdk synth --quiet`) | ~10s | Infra changes |
| **L5** | Docker integration (full smoke against running stack) | ~5 min | Pre-PR |
| **L6** | Full eval suite (`just eval`) | ~30 min | Agent changes, supervisor routing changes |

**Recipe inventory by category** (75 total post-§3a):

- **Setup** (2): `setup`, `create-users`
- **Dev** (12): `dev`, `dev-sso`, `dev-up`, `dev-up-sso`, `dev-down`, `dev-local`, `dev-local-sso`, `dev-backend`, `dev-frontend`, `dev-local-8001`, `dev-smoke`, `dev-smoke-ui`, `kill-stale`
- **Discovery** (3): `registry`, `docs`, `smoke-list` ← new
- **Format + Lint** (6): `format`, `format-py`, `format-ts`, `format-check`, `lint`, `lint-py`, `lint-ts`
- **Test** (4): `test`, `test-e2e`, `test-e2e-ui`, `e2e`
- **Smoke** (7): `smoke`, `smoke-ui`, `dev-smoke-deployed`, `qa-smoke-deployed`, `dev-smoke-triage`, `smoke-prod`, `devbox-smoke`
- **Eval** (3): `eval`, `eval-quick`, `eval-aws`
- **MVP1 ladder** (4): `mvp1`, `mvp1-quick`, `mvp1-full`, `mvp1-visual` ← new
- **Baseline** (2): `baseline`, `baseline-list` ← new
- **Build** (3): `build`, `build-backend`, `build-frontend`
- **Deploy** (10): `deploy`, `deploy-backend`, `deploy-frontend`, `deploy-ci`, `deploy-watch`, `deploy-status`, `deploy-cancel`, `deploy-qa`, `deploy-qa-ci`, `deploy-backend-qa`, `deploy-frontend-qa`
- **CDK** (5): `cdk-install`, `cdk-synth`, `cdk-diff`, `cdk-deploy`, `cdk-deploy-storage`
- **Devbox** (7): `devbox-start`, `devbox-stop`, `devbox-deploy`, `devbox-tunnel`, `devbox-health`, `devbox-logs`, `devbox-teardown`, `devbox-ship`
- **Operations** (6): `status`, `status-qa`, `logs`, `logs-qa`, `urls`, `urls-qa`, `check-aws`, `check-sso`, `aws-login`
- **Diagnostics** (4): `triage-session`, `check-cloudwatch`, `check-langfuse`, `check-envs` ← new
- **KB Ops** (2): `kb-sync`, `kb-regenerate` ← new
- **Visual QA** (1): `e2e-judge` ← new
- **Onboarding** (1): `handoff` ← new
- **Health** (2): `on-track`, `morning-report` ← new
- **Debug** (3): `debug-on`, `debug-off`, `debug-status`
- **Analytics** (7): `langfuse-report*` × 4, `langfuse-post-teams`, `langfuse-post-teams-dry`
- **Validation** (3): `validate`, `validate-full`, `smoke-prod`
- **Composite** (2): `ci`, `ship`

---

## §4 — Cognitive Layer: Experts + Skills + Spec Workflow

### TL;DR
Three building blocks: **15 experts** (frozen mental models in `expertise.md` files — I never have to re-explain context), **50+ skills** (named workflows invoked as `/skill-name` inside Claude Code), and a **plan → build → review → ship** loop that writes its own specs to `.claude/specs/`. As of today there are 70+ dated planning artifacts in that folder — a permanent record of every decision.

### Deep-Dive

#### 15 Expert Domains

Each expert lives at `.claude/commands/experts/{domain}/` and exposes 4 commands:

| Command | Purpose |
|---|---|
| `/experts:{domain}:question` | Query without modifying — fastest way to get context |
| `/experts:{domain}:plan` | Plan a change in that domain using the expertise |
| `/experts:{domain}:maintenance` | Run health checks, validate state |
| `/experts:{domain}:self-improve` | Update `expertise.md` after a successful change |

The 15 domains:

| Tier | Experts |
|---|---|
| Core | aws · backend · frontend · deployment · git |
| Specialized | cloudwatch · test · eval · claude-sdk · strands · sse · hooks · tac |
| Playground | playground · document-playground |

**Why this matters:** `expertise.md` is a frozen mental model. Mentioning `/experts:backend:question` auto-loads ~50 KB of backend architecture (tool dispatch, session store, Bedrock routing) without re-reading code. The expertise files are append-only and updated by `self-improve` after successful changes.

#### 50+ Skills (Grouped)

Located at `.claude/skills/*/SKILL.md` (project-scoped) and `~/.claude/skills/*/SKILL.md` (user-global).

- **Operations**: `sync`, `pull-remote`, `check-aws`, `check-cloudwatch-logs`, `check-langfuse-logs`, `check-envs`, `pid`
- **QA / Eval**: `baseline-questions`, `mvp1-eval`, `e2e-judge`, `agent-browser`, `triage`, `e2e-test`
- **Reports**: `scribe`, `langfuse-analytics`, `excalidraw`, `document-generator`, `playground`
- **Knowledge**: `s3-knowledge-base-sync`, `kb-regenerate`, `obsidian-vault`, `jira-commit-matcher`, `jira-story-writer`, `jira-sync`, `jira`
- **Workflow**: `plan`, `build`, `review`, `ship`, `fix`, `test`, `on-track`, `simplify`, `loop`, `schedule`, `parallel_subagents`
- **Handoff**: `claude-handoff` (built 2026-05-08 — sanitized environment bundling)
- **Planning (GSD)**: `gsd-add-todo`, `gsd-discuss-phase`, `gsd-plan-phase`, `gsd-execute-phase`, `gsd-audit-fix`, `gsd-debug`, `gsd-ship`, ... (30+ GSD skills)

#### The Plan → Build → Review → Ship Loop

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   /plan     │──▶│   /build    │──▶│   /review   │──▶│   /ship     │
│             │   │             │   │             │   │             │
│ Writes spec │   │ Reads spec, │   │ Reads diff, │   │ Lint+push+  │
│ to          │   │ implements, │   │ flags risks │   │ Jira sync+  │
│ .claude/    │   │ validates   │   │ + fixes     │   │ CI monitor  │
│ specs/      │   │ locally     │   │             │   │             │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
        │
        ▼ (70+ dated artifacts as of 2026-05-12)
  20260225-plan-cdk-multi-account-portability-v1.md
  20260302-plan-strands-poc-v1.md
  20260310-plan-skills-optimization-v1.md
  20260427-plan-triage-fixes-v1.md
  20260505-plan-doc-registry-ssot-v1.md
  (... 65 more)
```

**Filename convention** (canonical): `{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.md` where `type` ∈ `plan` · `pbi` · `eval` · `report` · `meeting` · `arch`.

---

## §5 — Flywheel Architectures (KEYSTONE)

### TL;DR
Five self-improving loops run on a schedule and produce evidence overnight. Mornings start with **diagnoses, not investigations**. Each loop closes back on itself: yesterday's bugs become tonight's fix plans become tomorrow's commits.

### Deep-Dive — five flywheels

#### Flywheel 1 — Nightly Triage (`0 9 * * *` UTC = 1 AM PST)

```
              ┌──────────────────────────────────┐
              │  GitHub Actions cron 0 9 * * *   │
              └──────────────┬───────────────────┘
                             │ matrix [dev, qa]
                             ▼
       ┌─────────────────────────────────────────┐
       │  Claude Code CLI → /triage full         │
       └─────┬──────────────┬──────────────┬─────┘
             │              │              │
             ▼              ▼              ▼
   DynamoDB feedback   CloudWatch     Langfuse traces
   (24h window)        error logs      (failures)
             │              │              │
             └──────────────┴──────────────┘
                            ▼
                ┌───────────────────────────┐
                │  Root-cause classification│
                │  (5 levers)               │
                └─────────────┬─────────────┘
                              ▼
              ┌────────────────────────────────┐
              │ docs/development/              │
              │   {ts}-report-triage-*.html    │  ← diagnostic
              │ .claude/specs/                 │
              │   {ts}-plan-triage-fixes-*.md  │  ← actionable
              └─────────────┬──────────────────┘
                            │
                            ▼ (human implements next day)
                       git commit → next night's run learns
```

- **Trigger**: GitHub Actions cron `0 9 * * *` (`.github/workflows/nightly-triage.yml`)
- **Inputs**: DynamoDB user feedback, CloudWatch `/eagle/ecs/backend-dev` + `/eagle/ecs/frontend-dev`, Langfuse trace failures (last 24h)
- **Process**: `/triage full` (defined in `.claude/commands/triage.md`) — correlation across 3 sources, classification by root cause
- **Output**: HTML diagnostic + markdown fix plan, committed to repo
- **Learning loop**: today's fix plans become tomorrow's commits → next night's triage learns from yesterday's changes
- **Evidence**: 15+ dated triage plans in `.claude/specs/` over the past 6 weeks

#### Flywheel 2 — Eval + Expert Self-Improve (`0 6 * * *` UTC = 2 AM ET)

```
   cron 0 6 * * * (eval.yml)
            │
            ▼
   server/tests/test_strands_eval.py (142 tests, haiku model)
            │
            ▼
   Failure classification by 5 levers:
     ┌──────────────────────────────────────┐
     │ Lever 1: Agent prompts                │ → edit eagle-plugin/agents/*/agent.md
     │ Lever 2: Skill workflows              │ → edit eagle-plugin/skills/*/SKILL.md
     │ Lever 3: Supervisor routing           │ → edit supervisor agent
     │ Lever 4: Trigger patterns (YAML)      │ → edit frontmatter keyword matching
     │ Lever 5: Context budget               │ → edit MAX_SKILL_PROMPT_CHARS
     └──────────────────────────────────────┘
            │
            ▼
   /experts:eval:self-improve --fix
            │
            ▼ (writes code, not docs)
   Re-run affected tests → validate fix
            │
            ▼
   eval_aws_publisher.py → S3 + Langfuse
            │
            ▼ (knowledge persists)
   expertise.md updated (cumulative learnings)
```

- **Closed-loop**: eval failures directly drive code edits (not just docs). Fix → re-validate → publish results.
- **Files**: `.github/workflows/eval.yml`, `server/tests/test_strands_eval.py`, `.claude/commands/experts/eval/self-improve.md`

#### Flywheel 3 — Morning Report (`0 13 * * 1-5` UTC = 8 AM ET weekdays)

```
   cron 0 13 * * 1-5 (morning-report.yml)
            │
            ▼
   git log --since="24h ago" (parsed for authors, files, Jira keys)
            │
            ▼
   Langfuse 24h aggregation (if LANGFUSE_* env set)
            │
            ▼
   scripts/morning_report.py → Teams Adaptive Card
            │
            ├─→ POST to qa-channel webhook
            └─→ jira-commits-sync-agentic.yml (parallel)
            │
            ▼
   Standup-ready: velocity, hot files, linked issues
```

- **Local equivalent**: `just morning-report`
- **Visibility flywheel**: daily snapshot drives standup planning, bug prioritization, capacity insights

#### Flywheel 4 — Post-Deploy Smoke

```
   workflow_run "Deploy EAGLE Platform" → success
   OR manual workflow_dispatch
            │
            ▼
   post-deploy-smoke.yml selects scenario from:
     - research_source_transparency  (default)
     - jefo_q4                        (FAR 16.507-6 citations)
     - sbir_q5                        (SBIR protest)
     - uc21_microscope                (micro-purchase)
     - kb_inventory_diagnostic        (KB retrieval)
     - qasp_orphan_unlock             (QASP orphan doc types)
            │
            ▼
   SSM into eagle-ec2-dev (VPC-internal)
            │
            ▼
   POST /api/chat → validate SSE wire shape
            │
            ▼
   Playwright walks UI → 4-5 screenshots
            │
            ▼
   Upload to s3://eagle-eval-artifacts-{acct}-{env}/smoke/{scenario}/{ts}/
            │
            ▼
   Exit 0 (PASS) or 1 (FAIL → rollback signal)
```

- **Safety valve**: ensures triage scenarios remain functional post-deploy
- **Run locally**: `just dev-smoke-deployed <scenario>` or `just qa-smoke-deployed <scenario>` or `just dev-smoke-triage` (all 5 in sequence)
- **Scenario registry**: `just smoke-list` or `server/tests/post_deploy_smoke.py` SCENARIOS dict

#### Flywheel 5 — Expert Self-Improve (Multi-Domain)

```
   Manual trigger: /experts:{domain}:self-improve [args]
            │
            ▼ (after each meaningful change)
   Reads: implementation files, debug notes, test results
            │
            ▼
   Updates expertise.md:
     - patterns_that_work
     - patterns_to_avoid
     - common_issues
     - tips_and_tricks
            │
            ▼ (cumulative knowledge)
   Next session: anyone invoking /experts:{domain}:question
                 gets the updated mental model automatically
```

- **Community learning**: shared expertise across the team, embedded in the agent system
- **All 15 experts have this loop** — patterns accrete over time

---

## §6 — HTML Report Gallery (See Companion Folder)

### TL;DR
A curated 12-artifact gallery showing concrete examples of what AI-amplified workflows produce. Located at `docs/development/20260512-174210-gallery-ai-workflow-v1/`. Open `index.html` and click through.

### Deep-Dive
The gallery is intentionally diverse:

| # | Artifact | Purpose | Generator (AI skill) |
|---|---|---|---|
| 01 | `eagle-presentation-builder.html` | Meta-tool / design template | `/playground` |
| 02 | `langfuse-24h-dashboard.html` | KPI grid (requests, errors, P95, cost) | `/langfuse-analytics` |
| 03 | `retrieval-3layer-audit.html` | Search/Rank/Read efficiency audit | `scripts/retrieval_report.py` |
| 04 | `kb-regenerate-status.html` | "Where we stand on /kb-regenerate" memo | `/kb-regenerate` |
| 05 | `jira-full-project-status.html` | 319-issue snapshot vs git commits | `/jira-commit-matcher` |
| 06 | `jira-qa5-epic-status.html` | QA5 epic (EAGLE-291) snapshot | `/jira` |
| 07 | `playground-document-schema.html` | Interactive NCI document schema explorer | `/document-playground` |
| 08 | `compliance-matrix-flow.html` | Interactive NCI/NIH compliance flow | `/document-playground` |
| 09 | `contract-requirements-matrix.html` | FAR clause browser + compliance mapping | `/document-playground` |
| 10 | `eagle-usage-dashboard.html` | Dev activity (Chart.js) | `scripts/morning_report.py` |
| 11 | `q4-q5-rerun-langfuse.html` | Q4 vs Q5 eval comparison | `/langfuse-analytics` |
| 12 | `trace-viewer-template.html` | Langfuse trace spatial visualizer | `/experts:playground:trace-viewer` |

**Design language**: dark navy `#0b0f17` + accent blue `#5aa0ff` + accent orange `#ffb454`. This palette emerged organically from `eagle_presentation_builder.html` and was reused across artifacts for visual consistency.

**Each artifact saved 30 min - 2 hr** vs hand-assembly. Total estimated time savings from the 12 artifacts: ~15 hours.

---

## §7 — Concrete Productivity Multipliers

### TL;DR
Measurable 4x-120x speedups on real tasks I do every week. The compounding comes from the second AI layer (Claude Code + skills + experts), not from EAGLE itself.

### Deep-Dive

| Task | Manual approach | AI-amplified | Speedup | Real evidence |
|---|---|---|---|---|
| **Session triage** (1 session, cross-source) | Grep CloudWatch, query DynamoDB, filter Langfuse, correlate by timestamp | `just triage-session <id>` → `/triage <id>` runs all three in parallel and writes a prioritized fix plan | **15-22x** | 15+ plans in `.claude/specs/` from past 6 weeks |
| **Baseline eval** (14 questions + judge + report) | Hand-run questions, copy responses, manually score, format HTML | `just baseline v6` → all 14 questions, auto-judged, HTML report generated | **12-24x** | `Use Case List.xlsx` columns v1-v6+ |
| **MVP1 ladder** (unit → integration → eval → visual) | Run each tier separately, switch contexts | `just mvp1-full` → all 4 tiers in sequence with Langfuse correlation | **6-10x** | `.claude/skills/mvp1-eval/config.json` |
| **Deploy with validation** (lint, test, CI, Jira, push, monitor) | Manual validation, manual Jira updates, manual CI watching | `/ship` Claude skill OR `just ship` (deploy variant) | **4-7x** | GH Actions run history |
| **Expert context transfer** (onboarding) | Read docs, explore code, ask senior dev questions | Read `expertise.md` for relevant domain — 50KB of curated context | **60-120x** | 15 `expertise.md` files |
| **Multi-session diagnosis** (5 sessions in parallel) | Serial: triage one, then next | `/parallel_subagents` launches 5 triage agents simultaneously | **12-15x** | Parallel transcript examples |
| **Generate operational report** (Langfuse → HTML dashboard) | Query Langfuse API, write Python, format HTML, commit | `just langfuse-report-html 24h all` → HTML + markdown + JSON in one shot | **30-60x** | 12 reports in gallery (deliverable C) |
| **Compose acquisition document** (SOW/IGCE/AP draft) | Look up template, write boilerplate, fill in details | EAGLE itself: chat → routes to document-generator skill → NCI-compliant draft | **5-10x** | Documents in `eagle-documents-*` S3 bucket |

**The compounding insight**: Each row above is independent. But the second AI layer makes EAGLE faster to build, which makes EAGLE better, which makes the team faster. Over weeks, this stacks.

---

## §8 — Handoff, Onboarding, Team Adoption

### TL;DR
The system is designed to be transferable. **Two new entry points**: `just handoff human` (bundle environment for a new co-worker) and `just handoff agent` (onboarding checklist for a new AI agent). The cognitive layer's `expertise.md` files mean a new dev gets 50KB of curated context per domain without reading code.

### Deep-Dive

#### For a new human teammate

1. **`just handoff human`** prints the bundle instructions. Inside Claude Code: `/claude-handoff` bundles:
   - `~/.claude/` config (sanitized — no API keys)
   - Session JSONLs scrubbed via `.claude/skills/claude-handoff/scrub-jsonl.py`
   - Readable HTML transcripts
   - Auto-generated setup guide
2. Recipient: `cd <bundle> && just setup` (CDK bootstrap → CDK deploy → containers → users → verify)
3. First-day reading list: README.md → CLAUDE.md → 5-10 most recent `.claude/specs/`
4. Pair on first PR using `/plan` → `/build` → `/review` → `/ship`

#### For a new AI agent (e.g., a fresh Claude Code session)

The `just handoff agent` recipe prints this checklist:

```
1. Read CLAUDE.md                  # operational guide, validation ladder
2. Run: just registry              # full command + skill + expert map
3. Run: just docs                  # doc tree map
4. Read expertise.md for relevant domains
5. Skim recent .claude/specs/ (last 5-10 dated entries)
6. Run: just status                # see deployed state
7. Run: just check-aws             # verify AWS access
```

This is **deliberately short** — 7 steps. The agent ends up oriented in <2 minutes vs ~30 minutes of unguided exploration.

#### For the team to start writing their own skills

`.claude/skills/skill-creator/skill-creator.md` is the meta-skill that scaffolds a new skill with proper YAML frontmatter, trigger keywords, and script structure. Anyone on the team can run `/skill-creator` to add automation.

---

## §9 — Live Demo Recipe (6 minutes)

> A scripted walkthrough for a team presentation. See companion file `*-runbook-ai-workflow-demo-v1.md` for the standalone runbook with failsafes.

| Step | Time | Command | What it shows |
|---|---|---|---|
| 1 | 0:00-0:30 | `just status` | Deployed ECS state + ALB URLs |
| 2 | 0:30-1:00 | `just registry` | The new discovery surface — operational entry points |
| 3 | 1:00-1:30 | `just langfuse-report-today` | One command → live HTML rollup (open in browser) |
| 4 | 1:30-3:00 | `/triage <recent session ID>` in Claude Code | The 30-min → 2-min triage flywheel (show the speech bubble interface) |
| 5 | 3:00-3:30 | Open the generated `.claude/specs/{ts}-plan-triage-*.md` | The fix plan written by AI |
| 6 | 3:30-4:30 | `just mvp1-quick` | Tier 1 unit tests in ~30s |
| 7 | 4:30-5:30 | Open the HTML gallery `index.html` in browser | 12 example artifacts |
| 8 | 5:30-6:00 | Q&A pivot | "What would you automate if you had this system?" |

**Failsafe alternates** in the runbook.

---

## §10 — Appendices

### A. Glossary (every term first used in this doc)

| Term | Plain English |
|---|---|
| **EAGLE** | The multi-tenant AI acquisition assistant we build for NCI |
| **Supervisor agent** | The Claude-powered router that decides which specialist handles a user question |
| **Specialist** | One of 9 focused agents (legal, market intel, policy, etc.) that the supervisor delegates to |
| **Strands SDK** | AWS's boto3-native SDK for orchestrating multi-agent flows over Bedrock |
| **Bedrock** | AWS's managed LLM hosting (Claude, Llama, Titan models) |
| **SSE (Server-Sent Events)** | The streaming protocol that pushes chat tokens from FastAPI → Next.js |
| **MultiAgentStreamWriter** | EAGLE's SSE event-formatting class (`server/app/stream_protocol.py`) |
| **Justfile** | A modern Makefile-like task runner. Recipes are called `just <name>` |
| **Expert** | A Claude Code abstraction — a `domain/expertise.md` + 4 commands (`plan`, `maintenance`, `question`, `self-improve`). 15 exist in this repo. |
| **Skill** | A named workflow invokable as `/skill-name` in Claude Code. 50+ exist. |
| **Spec** | An implementation plan in `.claude/specs/` written by `/plan`, consumed by `/build` |
| **Flywheel** | A self-improving loop — runs on a schedule, produces evidence, learns from yesterday |
| **L1-L6 validation** | The 6-level test ladder (lint → unit → e2e → CDK → docker → eval) |
| **Tenant** | A logical customer in the multi-tenant system (e.g., `nci`). Affects scoping. |
| **Tier** | Subscription tier (basic / advanced / premium). Gates features. |
| **PMR** | Procurement Management Review — the NCI compliance matrix that gates document generation |
| **FAR** | Federal Acquisition Regulation — the federal procurement rulebook |
| **DFARS** | DoD supplement to FAR |
| **OAG** | Office of Acquisition Guide (NIH) |
| **J&A** | Justification & Approval (single-source procurement document) |
| **SOW** | Statement of Work |
| **IGCE** | Independent Government Cost Estimate |
| **AP** | Acquisition Plan |
| **Cognito** | AWS's managed user-auth service. EAGLE uses it for tenant/tier identity. |
| **ECS Fargate** | AWS's serverless container runtime |
| **CDK** | AWS Cloud Development Kit — Infrastructure-as-Code in TypeScript |
| **Langfuse** | LLM observability platform. We use it for tracing, cost tracking, eval correlation. |
| **OIDC** | Federated auth pattern (no static AWS keys in CI) |
| **GH Actions** | GitHub Actions — CI/CD pipeline |
| **SSM** | AWS Systems Manager — used here to connect into the VPC-internal EC2 devbox |

### B. Full Justfile Recipe Inventory (75 recipes)

See `just --list` for the alphabetical listing or `just registry` for the categorized one. Inventory by category is in §3.

### C. All 15 Expert Domains

```
.claude/commands/experts/
├── aws/                  (expertise.md + 4 commands + cdk-scaffold)
├── backend/              (expertise.md + 4 commands)
├── claude-sdk/           (expertise.md + 4 commands + add-tool + cheat-sheet)
├── cloudwatch/           (expertise.md + 4 commands)
├── deployment/           (expertise.md + 4 commands)
├── document-playground/  (templates: acquisition-doc)
├── eval/                 (expertise.md + 4 commands + add-test + e2e-judge)
├── frontend/             (expertise.md + 4 commands + fix-next-cache)
├── git/                  (expertise.md + 4 commands + workflow-scaffold)
├── hooks/                (expertise.md + plan + question + self-improve)
├── playground/           (trace-viewer-template.html)
├── sse/                  (expertise.md + 4 commands + diagrams)
├── strands/              (expertise.md + 4 commands + add-tool + cheat-sheet)
├── tac/                  (expertise.md + 4 commands)
└── test/                 (expertise.md + 4 commands + add-test + parallel + run-all + use-case-builder + validate-uc)
```

### D. Scheduled GitHub Actions Workflows

| Workflow | Cron | Purpose |
|---|---|---|
| `nightly-triage.yml` | `0 9 * * *` | Daily cross-source triage → fix plans |
| `eval.yml` | `0 6 * * *` | Daily eval suite + Bedrock test |
| `morning-report.yml` | `0 13 * * 1-5` | Weekday standup card to Teams |
| `post-deploy-smoke.yml` | on `workflow_run` | Post-deploy validation |
| `jira-commits-sync-agentic.yml` | parallel to morning-report | Jira issue auto-transitions |
| `claude-code-assistant.yml` | on PR | Automated PR review |
| `deploy.yml` | on push to main (+ manual) | CDK + container deploy |

### E. Key File Quick-Reference

```
Justfile                                              ← 75 recipes (run `just registry`)
README.md                                             ← Quickstart
CLAUDE.md                                             ← Operational guide for agents
eagle-plugin/plugin.json                              ← Active agents + skills manifest
eagle-plugin/agents/*/agent.md                        ← Agent prompts (source of truth)
server/app/strands_agentic_service.py                 ← Strands SDK supervisor
server/app/streaming_routes.py                        ← SSE endpoint
server/app/stream_protocol.py                         ← MultiAgentStreamWriter
client/components/chat-simple/simple-chat-interface.tsx  ← Active chat UI
client/hooks/use-agent-stream.ts                      ← Frontend SSE consumer
infrastructure/cdk-eagle/lib/                         ← 6 CDK stacks
.claude/commands/experts/*/expertise.md               ← 15 frozen mental models
.claude/skills/*/SKILL.md                             ← 50+ named workflows
.claude/specs/                                        ← 70+ dated implementation plans
.github/workflows/                                    ← 7+ scheduled + on-event flywheels
docs/architecture/diagrams/                           ← 45+ Excalidraw/Mermaid diagrams
docs/development/                                     ← Timestamped reports + memos
```

---

## Companion Artifacts

| Artifact | Path |
|---|---|
| HTML deck | `docs/development/20260512-174210-deck-ai-workflow-v1.html` |
| HTML gallery | `docs/development/20260512-174210-gallery-ai-workflow-v1/index.html` |
| Demo runbook | `docs/development/20260512-174210-runbook-ai-workflow-demo-v1.md` |
| Plan that produced this | `~/.claude/plans/ok-so-now-we-jiggly-catmull.md` |

---

*Generated 2026-05-12. Re-generate any section by re-running the appropriate skill (see §6 Generator column) or `just <recipe>`.*
