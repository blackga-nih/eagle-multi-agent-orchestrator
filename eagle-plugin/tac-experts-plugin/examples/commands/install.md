---
description: Agentic install wrapper — reads hook log, analyzes, reports
argument-hint: [mode: "true" for interactive]
---

# Install (Agentic Wrapper)

Supervise the deterministic install hook by reading its log, analyzing results, and reporting status. This command does NOT perform installation — the Setup hook does that. This command adds intelligence on top.

## Variables

MODE: $1

## Instructions

- The Setup hook (`setup_init.py`) has already run before this command executes
- Your job is to READ the log, ANALYZE results, and REPORT status
- If MODE="true", delegate to `/install-hil` for interactive questions
- Never re-run installation commands — the hook already did that
- Write results to `app_docs/install_results.md`

## Workflow

1. Execute `/prime` — understand the codebase
2. Check if MODE="true"
   - If yes: delegate to `/install-hil` (interactive mode) and stop
3. Read `.claude/hooks/setup.init.log` (the hook's output)
4. Parse each line:
   - `[OK]` lines = successes
   - `[FAIL]` lines = failures (include error details)
5. Write analysis to `app_docs/install_results.md`:
   - Timestamp
   - Summary (X succeeded, Y failed)
   - Each action with status
   - Failure details with recommended fixes
6. Report to user:
   - **Status**: PASS or FAIL
   - **What Worked**: List successful actions
   - **What Failed**: List failures with fix suggestions
   - **Next Steps**: What to do next (run backend, open browser, etc.)
