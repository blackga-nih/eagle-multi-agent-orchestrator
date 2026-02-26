---
description: Agentic maintenance wrapper — reads hook log, analyzes trends, reports
---

# Maintenance (Agentic Wrapper)

Supervise the deterministic maintenance hook by reading its log, analyzing trends, and reporting status. Like `/install`, this command adds intelligence on top of the deterministic hook.

## Instructions

- The Setup maintenance hook (`setup_maintenance.py`) has already run
- Read the log, analyze results, and report
- Compare with previous maintenance runs if log has history
- Write results to `app_docs/maintenance_results.md`

## Workflow

1. Execute `/prime` — understand the codebase
2. Read `.claude/hooks/setup.maintenance.log`
3. Parse the latest run:
   - `[OK]` lines = successes
   - `[FAIL]` lines = failures
   - Database stats (table row counts)
4. If log has multiple runs, compare trends:
   - Did any dependency upgrade fail that previously succeeded?
   - Are database row counts growing as expected?
   - Any new failures vs last run?
5. Write analysis to `app_docs/maintenance_results.md`:
   - Timestamp
   - Summary
   - Dependency status (backend + frontend)
   - Database health (integrity, VACUUM, row counts)
   - Trend analysis (if history available)
6. Report to user:
   - **Status**: Healthy / Warning / Degraded
   - **Dependencies**: What was updated
   - **Database**: Health check results
   - **Trends**: Any concerning patterns
   - **Next Steps**: Recommended actions
