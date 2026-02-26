# TAC Experts Plugin

**Tactical Agentic Coding (TAC)** — a methodology for agent-first software development with Claude Code.

TAC treats the AI agent as the primary developer and the human as an architect/director. This plugin provides the complete methodology, expert system framework, and reusable patterns.

---

## What's Inside

```
tac-experts-plugin/
├── plugin.json                          ← Plugin manifest
├── justfile                             ← Master recipes (60+ commands)
├── commands/experts/tac/                ← TAC methodology expert (ready to use)
│   ├── _index.md                        Expert overview
│   ├── expertise.md                     Practical patterns (hooks, SSVA, agent teams)
│   ├── tac-learning-expertise.md        Theory (8 tactics, lessons 9-27, frameworks)
│   ├── question.md                      Query TAC concepts (read-only)
│   ├── plan.md                          Plan with TAC principles
│   ├── plan_build_improve.md            Full ACT-LEARN-REUSE workflow
│   ├── self-improve.md                  Update expertise with learnings
│   └── maintenance.md                   Validate TAC compliance
├── templates/
│   ├── expert/                          ← 7-file expert template (parameterized)
│   ├── claude-md/                       ← 3 production CLAUDE.md styles
│   │   ├── option-a-enterprise.md       Identity-first, formal teams
│   │   ├── option-b-mission-control.md  Domain-first, regulated projects
│   │   └── option-c-fullstack-blueprint.md  Composable, multi-stack
│   ├── workflow-template.md             ← Agent Team Workflow template
│   └── spec-template.md                 ← Implementation spec template
├── docs/                                ← TAC reference documentation (9 docs)
│   ├── tactics.md                       The 8 Fundamental Tactics + memory aid
│   ├── advanced-lessons.md              Lessons 9-27 (Context → Domain Agents)
│   ├── workflow-patterns.md             7 workflow patterns + catalogs
│   ├── frameworks.md                    PITER, R&D, ACT-LEARN-REUSE, Core Four
│   ├── hooks-architecture.md            12 hook events, 7 patterns, dispatcher
│   ├── context-engineering.md           Context hierarchy, CLAUDE.md guidelines
│   ├── maturity-model.md               In-Loop → Out-Loop → Zero-Touch
│   ├── ecosystem.md                     Class 1/2/3 layer architecture
│   └── agentic-prompting.md            SSVA, block/retry, pipelines, validators
├── examples/
│   ├── commands/                        ← Real working slash commands
│   │   ├── plan.md                      Spec-driven planning
│   │   ├── build.md                     Build from plan
│   │   ├── review.md                    Risk-tiered code review
│   │   ├── fix.md                       Fix issues from review
│   │   ├── install.md                   Agentic install wrapper (reads hook log)
│   │   ├── install-hil.md              Interactive install (AskUserQuestion)
│   │   ├── maintenance-agentic.md      Agentic maintenance wrapper
│   │   └── prime.md                     Context priming (load all project files)
│   ├── agents/                          ← Real agent definitions
│   │   ├── hooks-expert-agent.md        Hooks specialist agent
│   │   ├── bowser-qa-agent.md           Browser QA agent
│   │   ├── docs-scraper.md             Documentation scraping specialist
│   │   └── ssva-csv-agent.md           SSVA with scoped hooks (block/retry)
│   ├── hooks/                           ← Hook scripts (all 4 event types)
│   │   ├── pretooluse_guard.py          PreToolUse: block dangerous commands
│   │   ├── posttooluse_validator.py     PostToolUse: CSV validation + block/retry
│   │   ├── stop_dispatcher.sh           Stop: dispatcher → domain handlers
│   │   ├── stop_test.sh                Stop handler: test file validation
│   │   ├── stop_memory.sh              Stop handler: turn-by-turn memory
│   │   ├── session_start.py             SessionStart: env var loading
│   │   ├── setup_init.py               Setup init: deterministic install
│   │   └── setup_maintenance.py        Setup maintenance: dep upgrades + DB
│   ├── experts/                         ← Domain expert extensions
│   │   ├── README.md                    Expert pattern guide
│   │   ├── aws/cdk-scaffold.md          5 CDK stack templates (core/compute/cicd/data/monitoring)
│   │   └── eval/add-test.md            8-registration checklist for new tests
│   ├── sdk/                             ← Claude Agent SDK examples
│   │   ├── orchestrator.py              Multi-agent supervisor + subagents + sessions
│   │   └── custom_tools.py             @tool decorator + MCP server + tier-gating
│   ├── justfile                         ← 4-layer browser automation recipes
│   └── agentic-prompting-justfile       ← SSVA pipeline recipes (finance review)
├── apps/
│   └── README.md                        ← Catalog of 44 reference apps (symlink to Desktop/tac/)
├── scripts/
│   ├── archive-repo.py                  ← Archive TAC repos into plugin catalog
│   ├── sync-to-obsidian.py              ← Sync components to AI-Agent-KB with MTG cards
│   ├── tac-pipeline-hook.sh             ← YouTube-TAC pipeline integration (Step 5.5)
│   └── agent-sync-hook.sh              ← PostToolUse hook for auto-sync to Obsidian
└── data/
    ├── frontmatter-schemas.md           ← All YAML frontmatter schemas
    ├── tags.md                          ← Canonical tag taxonomy
    └── kb-crossref.md                   ← AI-Agent-KB cross-reference mapping
```

---

## Quick Start

### Option A: Full bootstrap (recommended)

```bash
cd tac-experts-plugin
just bootstrap /path/to/your/project
```

This creates the directory structure, installs the TAC expert, and walks you through CLAUDE.md selection.

### Option B: Step by step

```bash
# 1. Install TAC expert
just install /path/to/your/project

# 2. Choose a CLAUDE.md template
just install-claude-md /path/to/your/project

# 3. Create your first domain expert (auto-fills placeholders)
just scaffold-expert my-domain "My Domain" "What this expert covers"

# 4. Validate
just validate-all-experts
```

### Option C: Manual (no just)

```bash
cp -r tac-experts-plugin/commands/experts/tac/ .claude/commands/experts/tac/
cp tac-experts-plugin/templates/claude-md/option-c-fullstack-blueprint.md CLAUDE.md
```

You now have `/experts:tac:question`, `/experts:tac:plan`, etc.

---

## Justfile Recipes

The plugin ships with 60+ `just` recipes organized into 10 sections. Run `just --list` for the full menu.

```bash
# ─── Setup ─────────────────────────────────
just bootstrap                         # Full project setup
just install                           # TAC expert only
just install-claude-md                 # Choose CLAUDE.md template
just install-examples                  # All commands + agents

# ─── Expert Scaffolding ───────────────────
just scaffold-expert api "API" "REST endpoints"
just list-experts                      # Show all experts
just validate-expert api               # Check 7-file structure

# ─── TAC Expert ────────────────────────────
just tac-question "What is SSVA?"      # Ask TAC methodology
just tac-plan "Add auth"               # Plan with TAC
just tac-pbi "Add dark mode"           # Full ACT-LEARN-REUSE

# ─── Any Domain Expert ────────────────────
just question frontend "How do forms work?"
just plan backend "Add health check"
just plan-build-improve aws "Add S3 bucket"

# ─── Dev Workflow ──────────────────────────
just plan-feature "Add user auth"      # Plan → .claude/specs/
just build .claude/specs/plan.md       # Build from plan
just review "Validate auth" plan.md    # Risk-tiered review
just piter "Add caching"              # Full PITER cycle

# ─── SSVA Pipelines ───────────────────────
just run-agent normalize-csv "Clean data"
just run-agents-parallel "a,b" "prompt"
just pipeline "step1" "step2" "step3"  # Fail-fast

# ─── Docs & Reference ─────────────────────
just tactics                           # 8 TAC tactics
just frameworks                        # Core frameworks
just ssva                              # SSVA pattern
just hooks                             # Hook architecture
just cheatsheet                        # Full cheatsheet

# ─── Management ────────────────────────────
just info                              # Plugin version
just stats                             # File & line counts
just weekly-maintenance                # Full health check
just diff-expertise                    # Plugin vs project
```

---

## The 8 Tactics (S.A.T.S.F.O.Z.P)

| # | Tactic | One-Liner |
|---|--------|-----------|
| 1 | **Stop Coding** | Don't type code, type instructions |
| 2 | **Adopt Perspective** | Think like the agent, design for its constraints |
| 3 | **Template Engineering** | Encode patterns in reusable templates |
| 4 | **Stay Out of the Loop** | Let the agent work without interruption |
| 5 | **Feedback Loops** | Build validation into every workflow |
| 6 | **One Agent, One Prompt** | One focused prompt per agent |
| 7 | **Zero-Touch** | Automate from commit to deploy |
| 8 | **Prioritize Agentics** | Always choose the more agentic option |

See `docs/tactics.md` for the full guide.

---

## Core Frameworks

| Framework | Cycle | When to Use |
|-----------|-------|-------------|
| **ACT-LEARN-REUSE** | Do → Capture → Apply | Every task (default) |
| **PITER** | Plan → Implement → Test → Evaluate → Refine | New features |
| **R&D** | Research → Develop | Exploration, bugs |
| **Core Four** | CLAUDE.md + commands/ + experts/ + settings.json | Project setup |

See `docs/frameworks.md` for details.

---

## Maturity Levels

```
In-Loop    →  Human directs every step
Out-Loop   →  Agent completes, human reviews
Zero-Touch →  Fully automated, human notified
```

**Graduation**: In-Loop (3+ successes) → Template → Add validation → Out-Loop → Zero-Touch

See `docs/maturity-model.md` for the full model.

---

## Expert System Pattern

Every domain expert has 7 standard files:

| File | Purpose | ACT-LEARN-REUSE |
|------|---------|-----------------|
| `_index.md` | Discovery and routing | — |
| `expertise.md` | Accumulated knowledge | REUSE |
| `question.md` | Read-only queries | REUSE |
| `plan.md` | Domain-aware planning | ACT |
| `plan_build_improve.md` | Full workflow | ACT + LEARN |
| `self-improve.md` | Update knowledge | LEARN |
| `maintenance.md` | Health validation | — |

Plus optional domain-specific extensions (e.g., `cdk-scaffold.md`, `add-test.md`).

**Note**: The TAC expert uniquely has TWO expertise files: `expertise.md` (practical patterns) and `tac-learning-expertise.md` (methodology theory). Other experts have one.

---

## Ecosystem Integration

The plugin integrates with the broader TAC ecosystem:

### Repo Archival (`scripts/archive-repo.py`)

Process new TAC repos into the plugin catalog:

```bash
# Archive a repo (auto-detects lesson number)
just archive-repo /path/to/tac/repo

# Dry run to preview changes
just archive-repo-dry /path/to/tac/repo

# Override lesson number
just archive-repo /path/to/tac/repo 28
```

Updates: `apps/README.md`, `docs/advanced-lessons.md`, `data/tags.md`, TAC expertise.

### AI-Agent-KB Sync (`scripts/sync-to-obsidian.py`)

Sync agents, commands, hooks, and experts to the Obsidian vault with MTG card assignment:

```bash
# Sync a single component
just sync-to-obsidian examples/agents/hooks-expert-agent.md

# Sync all plugin examples
just sync-all-to-obsidian

# Preview what would sync
just sync-all-to-obsidian-dry
```

### YouTube-TAC Pipeline

The plugin integrates with `consulting-co`'s youtube-tac-extract command as Step 5.5. When new repos are cloned from disler/IndyDevDan, the pipeline hook automatically archives them into the plugin catalog.

### Auto-Sync Hook

Configure `agent-sync-hook.sh` as a PostToolUse hook to automatically sync new agents/skills/hooks to Obsidian when they're created:

```json
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Write|Edit",
      "hooks": [{
        "type": "command",
        "command": "bash Desktop/tac/tac-experts-plugin/scripts/agent-sync-hook.sh"
      }]
    }]
  }
}
```

---

## Publishing as Official Claude Code Plugin

See **[PUBLISHING.md](PUBLISHING.md)** for the complete guide:

- Converting to official `.claude-plugin/` format
- Creating a marketplace (`marketplace.json`)
- Publishing to GitHub (public or private)
- Team auto-install via `extraKnownMarketplaces`
- Justfile recipes: `just plugin-init`, `just plugin-validate`, `just plugin-publish 1.2.0`

Quick start:

```bash
just plugin-init       # Create .claude-plugin/ with official manifests
just plugin-validate   # Check structure
just plugin-test       # Launch Claude Code with --plugin-dir
just plugin-publish 1.2.0  # Full pipeline: validate → build → tag
```

---

## For Pair Programming

When sharing this plugin with developers:

1. **Clone the plugin into your repo** (or reference as a submodule)
2. **Each dev copies the TAC expert** to their project's `.claude/commands/experts/tac/`
3. **Each dev creates domain experts** relevant to their project using the templates
4. **expertise.md files stay project-local** — they accumulate knowledge about THAT codebase
5. **Run `/experts:tac:maintenance --all`** weekly to catch drift

The TAC methodology expert is universal. Domain experts are project-specific.

---

## License

MIT
