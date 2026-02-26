---
description: Interactive install with human-in-the-loop questions (onboarding)
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Install — Human-in-the-Loop

Interactive installation for new engineers. Uses `AskUserQuestion` to adapt the setup flow based on user preferences. The deterministic hook has already run — this command adds interactive configuration.

## Instructions

- The Setup hook has already installed base dependencies
- Use `AskUserQuestion` for each configuration decision
- SECURITY: NEVER read, log, or display environment variable values
- Only validate env var existence via pattern matching: `grep -q "^VAR=.\+" .env`
- Write final status to `app_docs/install_results.md`

## Workflow

### Step 1: Database Setup

Ask: "How should we handle the database?"
Options:
- **Fresh install** — Drop existing database and recreate with seed data
- **Keep existing** — Run migrations only, preserve data
- **Skip** — Don't touch the database

Execute based on choice:
- Fresh: `rm -f apps/backend/starter.db && uv run python init_db.py`
- Keep: Run any pending migrations
- Skip: No action

### Step 2: Installation Mode

Ask: "What installation scope do you need?"
Options:
- **Full** — All dependencies (backend + frontend)
- **Minimal** — Only what's changed since last install
- **Skip** — Dependencies already installed

Execute based on choice (verify with `ls apps/backend/.venv` etc.)

### Step 3: Environment Check

Ask: "Should we validate your .env file?"
Options:
- **Yes** — Check all required variables exist (NOT their values)
- **No** — Skip environment validation

If yes:
1. Read `.env.sample` for required variable names
2. For each variable, check: `grep -q "^VAR_NAME=.\+" .env`
3. Report which are set vs missing (NEVER show values)

### Step 4: Environment Variables

Ask: "Do you need to configure environment variables?"
Options:
- **Yes, guide me** — Ask about each missing variable (what it's for, not the value)
- **Skip** — User will configure manually

If yes:
- For each missing var from Step 3, explain what it's for
- Instruct user to set it manually: "Add YOUR_KEY=<value> to .env"
- NEVER ask the user to type a secret value into the chat

### Step 5: Documentation Scraping

Read `ai_docs/README.md` for the list of external docs.

Ask: "Should we fetch external documentation for offline access?"
Options:
- **Yes, all** — Scrape all listed docs
- **Choose** — Let me pick which docs to fetch
- **Skip** — Don't fetch docs

If yes:
1. For each doc in the list, check freshness: `find ai_docs/ -name "filename.md" -mtime -1`
2. Skip docs modified in the last 24 hours
3. For stale/missing docs, spawn `@docs-scraper` agent to fetch
4. Report which were scraped, skipped, or failed

### Step 6: Report

Write `app_docs/install_results.md` with:
- Configuration chosen (each question's answer)
- What worked (with details)
- What failed (with suggested fixes)
- Environment variable status (set/missing — NEVER values)
- Documentation status (scraped/cached/skipped)
- Next steps

Report summary to user.
