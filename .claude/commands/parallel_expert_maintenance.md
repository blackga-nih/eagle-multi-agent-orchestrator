---
description: "Run maintenance health checks across all (or selected) expert domains in parallel"
argument-hint: [optional space-separated expert domains, e.g. `strands backend frontend`]
---

# Parallel Expert Maintenance

Run `maintenance` health checks across multiple expert domains simultaneously. Reports a consolidated pass/fail dashboard.

## Variables

- ARGS: Optional space-separated list of expert domains (e.g., `strands backend frontend`)
- EXPERTS_DIR: `.claude/commands/experts/`

## Workflow

### 1. Parse Optional Expert Arguments

- If ARGS is non-empty:
  - Split on whitespace to get candidate DOMAIN list
  - Normalize each (trim, lowercase)
- If ARGS is empty:
  - Run ALL experts that have a `maintenance.md` command

### 2. Discover Available Experts

- List subdirectories in EXPERTS_DIR
- For each domain, check that `maintenance.md` exists
- Build set AVAILABLE_DOMAINS
- Known domains (as of 2026-03-10): `aws`, `backend`, `claude-sdk`, `cloudwatch`, `deployment`, `eval`, `frontend`, `git`, `hooks`, `sse`, `strands`, `tac`, `test`
- Skip domains marked STALE in their `_index.md` (e.g., `claude-sdk`) unless explicitly requested

### 3. Select Domains

- If ARGS provided: intersect with AVAILABLE_DOMAINS, report unknowns
- If no ARGS: use all AVAILABLE_DOMAINS minus stale domains
- Report selected domains to user before launching

### 4. Launch Parallel Maintenance Subagents

For each selected DOMAIN, spawn a subagent using the Agent tool:

- **Prompt**: Run the maintenance command for this domain and report results
- **Command**: Execute the checks defined in `/experts:{DOMAIN}:maintenance`
- **Flag**: Use `--full` for comprehensive checks, or the most thorough preset available

Launch **all** subagents in a **single parallel batch** so they run concurrently.

Example: 5 domains = 5 parallel subagents.

**Subagent prompt template**:

```
You are the {DOMAIN} expert. Run the maintenance health checks defined in
.claude/commands/experts/{DOMAIN}/maintenance.md using the --full preset.

Execute all validation commands. Report each check as PASS or FAIL with details.
Return a structured report with:
- Domain name
- Overall status (HEALTHY / DEGRADED / FAILED)
- Individual check results
- Any issues found and recommended fixes
```

### 5. Collect and Summarize Results

Wait for all subagents to complete. Produce a consolidated dashboard:

```markdown
## Expert Maintenance Dashboard

**Date**: {timestamp}
**Domains Checked**: {N}

### Summary

| Domain | Status | Checks | Issues |
|--------|--------|--------|--------|
| strands | HEALTHY | 5/5 pass | — |
| backend | HEALTHY | 4/4 pass | — |
| frontend | DEGRADED | 3/4 pass | TSC warning in chat component |
| aws | HEALTHY | 3/3 pass | — |
| eval | FAILED | 2/4 pass | 2 tests failing |

### Issues Requiring Attention

| Domain | Issue | Severity | Recommended Fix |
|--------|-------|----------|-----------------|
| frontend | TSC warning | Low | Fix type annotation in simple-chat-interface.tsx |
| eval | Test 14 failing | Medium | Knowledge fetch timeout — check S3 connectivity |

### Domains Skipped

- `claude-sdk` — STALE (replaced by `strands`)
- `hooks` — No maintenance.md found

### Cross-Domain Observations

- {Any patterns across multiple domains, e.g., "3 domains report Bedrock connectivity OK"}
```

### 6. Recommend Follow-Up Actions

Based on results:
- If any domain is FAILED: suggest specific fix commands
- If any domain is DEGRADED: suggest investigation
- If all HEALTHY: suggest running `/parallel_expert_self_improve` to update expertise

## Presets

| Usage | Effect |
|-------|--------|
| `/parallel_expert_maintenance` | All non-stale domains |
| `/parallel_expert_maintenance strands backend` | Only strands + backend |
| `/parallel_expert_maintenance --all` | All domains including stale |

## Notes

- Each subagent runs in its own context — no cross-contamination
- Typical runtime: 30-90 seconds depending on domain count
- AWS-dependent checks (bedrock, deployment, cloudwatch) require active credentials
- If a subagent fails to launch or times out, report it and continue with others
