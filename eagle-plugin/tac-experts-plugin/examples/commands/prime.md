---
description: Load full project context at session start
allowed-tools: Read, Glob, Grep, Bash
---

# Prime

Quick-start agent understanding by loading all project context. Run this at the beginning of any session where you need full project awareness.

## Instructions

- Read all project context files in order
- Do NOT modify any files
- Report what you loaded and key takeaways

## Workflow

1. `git ls-files` — list all tracked files for project overview
2. Read `README.md` — understand project purpose
3. Read `justfile` — understand available recipes and patterns
4. Read `.claude/settings.json` — understand hooks, permissions, model config
5. Read all `.claude/hooks/*` files — understand automated behavior
6. Read all `.claude/commands/*` files — understand available commands
7. Read all `.claude/agents/*` files — understand available agents
8. Read `CLAUDE.md` — understand project conventions
9. Read `ai_docs/README.md` — understand cached external docs (if exists)

## Report

```
Project context loaded. Ready.

Key files: X tracked files
Commands: /install, /maintenance, ...
Agents: @docs-scraper, ...
Hooks: session_start, setup_init, setup_maintenance, ...
```
