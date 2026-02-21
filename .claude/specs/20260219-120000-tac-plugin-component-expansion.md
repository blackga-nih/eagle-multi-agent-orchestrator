# Plan: TAC Plugin Super-Enhanced Refactor

## Summary

Split the monolithic expertise.md into two focused files, add 13 post-14 project lessons, replace ADW terminology with agent teams, and update all 27 referencing files. Goal: TAC plugin becomes a comprehensive methodology + practical coding patterns reference.

## Agent Team Results

| Agent | Task | Findings |
|-------|------|----------|
| Scout 1 | Desktop/tac directories | 23 directories: 8 numbered lessons + 15 named projects. Richest: hooks-mastery (15 hooks), multi-agent-observability (17 hooks), orchestrator-agent-with-adws (12 hooks). Total: 123 hooks, 26 skills, 16 agents across all projects. |
| Scout 2 | Obsidian TAC Learning System | 14 lessons mapped (8 core + 6 specialized). 550+ catalog items: 130+ ADWs, 16 agents, 388+ commands, 80+ hooks, 21 skills. No content beyond lesson 14. |
| Playground Builder | Knowledge graph HTML | 45-node interactive force-directed graph with 7 clusters, 36 edges, search/filter/zoom. File: data/tac-knowledge-graph.html |
| Plan Agent | Expertise split design | 27-file refactor plan: 2 new, 18 modified, 3 renamed, 4 patterns identified for ADW→agent teams replacement. |

---

## The Split: Two Expertise Files

### `tac-learning-expertise.md` (NEW) — "What is TAC"
```
Part 1: The 8 Fundamental Tactics (from current Parts 1)
Part 2: Advanced Lessons 9-14 (from current Part 2)
Part 3: Post-14 Project Lessons (NEW — Lessons 15-27)
  - L15: Hooks Mastery (claude-code-hooks-mastery)
  - L16: Multi-Agent Observability (claude-code-hooks-multi-agent-observability)
  - L17: Damage Control (claude-code-damage-control)
  - L18: Install & Maintain (install-and-maintain)
  - L19: SSVA Finance Review (agentic-finance-review)
  - L20: Beyond MCP (beyond-mcp)
  - L21: Bowser (bowser)
  - L22: Agent Sandboxes (agent-sandboxes)
  - L23: Fork Repository (fork-repository-skill)
  - L24: R&D Deep Dive (rd-framework-context-window-mastery)
  - L25: 7 Prompt Levels (seven-levels-agentic-prompt-formats)
  - L26: The O-Agent (multi-agent-orchestration-the-o-agent)
  - L27: Software Delivery (software-delivery-adw)
Part 4: Core Frameworks (PITER, ACT-LEARN-REUSE, R&D, Core Four)
Part 5: Maturity Model (In-Loop → Out-Loop → Zero-Touch)
```
~400-450 lines estimated.

### `expertise.md` (REWRITTEN) — "How to code with TAC"
```
Part 1: Hooks Architecture (from current Parts 5+6)
Part 2: SSVA — Specialized Self-Validating Agents (from agentic-prompting.md)
Part 3: Agentic Prompting Patterns (expanded with post-14 learnings)
Part 4: Claude Code Ecosystem Graph (from current Part 7, updated)
Part 5: Agent Team Patterns (REPLACES ADW Patterns)
Part 6: Reference Catalogs (agents, commands, hooks, scale)
Learnings: patterns_that_work, patterns_to_avoid, common_issues, tips (expanded)
```
~500-550 lines estimated.

---

## Full File Change Manifest (27 files)

### Phase 1: Core Split (2 files)
| Action | File | Description |
|--------|------|-------------|
| CREATE | `commands/experts/tac/tac-learning-expertise.md` | TAC theory, lessons 1-27, frameworks, maturity |
| REWRITE | `commands/experts/tac/expertise.md` | Practical patterns: hooks, SSVA, ecosystem, agent teams |

### Phase 2: Command Updates (6 files)
| Action | File | Key Changes |
|--------|------|-------------|
| MODIFY | `commands/experts/tac/question.md` | Dual-file routing, new categories for post-14 + SSVA |
| MODIFY | `commands/experts/tac/plan.md` | Load both files, ADW → workflow |
| MODIFY | `commands/experts/tac/plan_build_improve.md` | Dual-file load, self-improve targets expertise.md only |
| MODIFY | `commands/experts/tac/self-improve.md` | Note: only updates expertise.md, not learning file |
| MODIFY | `commands/experts/tac/maintenance.md` | Glob for both expertise files |
| MODIFY | `commands/experts/tac/_index.md` | Document two-file architecture |

### Phase 3: Docs (4 files)
| Action | File | Key Changes |
|--------|------|-------------|
| RENAME+MODIFY | `docs/adw-patterns.md` → `docs/workflow-patterns.md` | ADW → workflow/agent team |
| MODIFY | `docs/advanced-lessons.md` | Add post-14 lesson summaries |
| MODIFY | `docs/frameworks.md` | Minor ADW rename |
| MODIFY | `docs/maturity-model.md` | Minor ADW rename |

### Phase 4: Templates (4 files)
| Action | File | Key Changes |
|--------|------|-------------|
| RENAME+MODIFY | `templates/adw-template.md` → `templates/workflow-template.md` | ADW → workflow |
| MODIFY | `templates/claude-md/option-a-enterprise.md` | ADW → workflow (1 line) |
| MODIFY | `templates/claude-md/option-b-mission-control.md` | ADW → workflow (1 line) |
| MODIFY | `templates/claude-md/option-c-fullstack-blueprint.md` | ADW → workflow (1 line) |

### Phase 5: Infrastructure (4 files)
| Action | File | Key Changes |
|--------|------|-------------|
| MODIFY | `data/frontmatter-schemas.md` | ADW schema → workflow schema |
| MODIFY | `plugin.json` | adw → workflow in provides |
| MODIFY | `README.md` | New file tree, dual expertise, ADW → workflow |
| MODIFY | `justfile` | Dual-file sync, ADW recipes → workflow |

### Docs with NO changes needed (5 files)
- `docs/tactics.md`, `docs/hooks-architecture.md`, `docs/context-engineering.md`, `docs/ecosystem.md`, `docs/agentic-prompting.md`

---

## ADW → Agent Teams Replacement Strategy

All ADW-specific concepts are renamed, not deleted. The workflow patterns remain valid — only the framing changes:

| Old Term | New Term | Rationale |
|----------|----------|-----------|
| ADW | Workflow Pattern / Agent Team Workflow | ADWs superseded by Claude Agent SDK teams |
| `adw-template.md` | `workflow-template.md` | Template file rename |
| `adw-patterns.md` | `workflow-patterns.md` | Doc file rename |
| `create-adw` recipe | `create-workflow` recipe | Justfile recipe rename |
| "ADW Python scripts" | "Agent team orchestration" | Architecture description |

---

## Execution Order

1. Create `tac-learning-expertise.md` (new, no deps)
2. Rewrite `expertise.md` (core restructure)
3. Rename docs/templates (adw → workflow)
4. Update command files (dual-file routing)
5. Update docs (advanced-lessons post-14, minor ADW renames)
6. Update infrastructure (plugin.json, README, justfile)
7. Validate: grep for orphaned "ADW" refs, check all file paths

## Validation
```bash
# Check for orphaned ADW references (should be zero in non-example files)
grep -r "ADW" tac-experts-plugin/ --include="*.md" --include="*.json" -l | grep -v examples/

# Verify both expertise files exist
ls tac-experts-plugin/commands/experts/tac/*expertise*.md

# Verify renamed files
ls tac-experts-plugin/docs/workflow-patterns.md
ls tac-experts-plugin/templates/workflow-template.md
```
