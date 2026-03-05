---
description: Scan session log (or provided expert list) to launch expert self-improve AND maintenance subagents in parallel.
argument-hint: [optional space-separated expert domains, e.g. `eval git tac`]
---

# Parallel Expert Self-Improve + Maintenance

Use this command at the end of a substantial coding session to automatically identify which domain experts were involved and trigger both their `self-improve` and `maintenance` routines in parallel. Self-improve updates the expert's mental model; maintenance validates the live system state.

## Variables

- ARGS: Optional space-separated list of expert domains provided by the user (e.g., `eval git tac`)
- SESSION_LOG: The current workspace session transcript (latest agent transcript for this repo)
- EXPERTS_DIR: `.claude/commands/experts/`

## Workflow

1. Parse Optional Expert Arguments
   - Read ARGS from the command invocation
   - If ARGS is non-empty:
     - Split on whitespace to get a candidate DOMAIN list (e.g., `["eval", "git", "tac"]`)
     - Normalize each domain string (trim, lowercase)
   - If ARGS is empty:
     - Defer domain selection to the session-log inference in step 3

2. Discover Available Experts
   - List subdirectories in EXPERTS_DIR to determine available domains (e.g., `frontend`, `backend`, `aws`, `deployment`, `claude-sdk`, `cloudwatch`, `eval`, `git`, `tac`, `hooks`, `test`)
   - For each domain, check that **both** `self-improve.md` and `maintenance.md` commands exist
   - Build a set AVAILABLE_DOMAINS of domains that support both commands
   - Also track domains that only support one of the two (report these to the user)

3. Select Relevant Domains
   - If ARGS was provided (non-empty):
     - INTERSECT the requested domains with AVAILABLE_DOMAINS
     - Drop any unknown or unsupported domains, but record them so they can be reported back to the user
     - If the intersection is empty, abort with a clear message that none of the requested experts support both commands
   - If no ARGS were provided:
     - Locate and Load Session Log
       - Identify the most recent session transcript associated with this workspace
       - Load enough of the transcript to capture:
         - User goals and high-level tasks
         - Files that were read or modified
         - Commands that referenced experts or domains (e.g., `/experts:frontend:plan`)
     - Infer Relevant Domains from the Session:
       - Analyze SESSION_LOG to detect which domains were actually exercised this session
       - Use multiple signals:
         - Files touched (e.g., `client/` → `frontend`, `server/` → `backend`, `infrastructure/cdk-eagle/` → `aws`/`deployment`)
         - Explicit expert commands mentioned (e.g., `/experts:backend:plan_build_improve`)
         - Domain-specific keywords (e.g., "FastAPI", "DynamoDB" → `backend` / `aws`; "Next.js", "Tailwind" → `frontend`; "CDK", "stack", "Fargate" → `aws` / `deployment`)
       - Build a unique set of DOMAIN values (e.g., `{frontend, backend, aws}`)
       - Filter this set to only domains that are in AVAILABLE_DOMAINS

4. Design Expert Prompts
   - For each relevant DOMAIN, construct two concise, self-contained prompts:

   **Self-Improve Prompt** — summarizing:
     - What changed in that domain during this session (files, features, refactors, fixes)
     - Any tests, linting, or validation that were run
     - Open questions or edge cases discovered
     - Instruct the expert to:
       - Validate its current `expertise.md` against the latest code and patterns
       - Update or refine examples, heuristics, and anti-patterns
       - Capture new workflows or pitfalls observed in this session

   **Maintenance Prompt** — summarizing:
     - The current state of the domain's infrastructure/builds/services
     - Instruct the expert to:
       - Run its standard health checks and validation routines
       - Report pass/fail status for each check
       - Flag any drift, broken builds, stale configs, or missing resources

5. Launch Parallel Expert Subagents
   - For each relevant DOMAIN, spawn **two** subagents using the Agent tool:
     - One executing `/experts:{DOMAIN}:self-improve` with the self-improve prompt
     - One executing `/experts:{DOMAIN}:maintenance` with the maintenance prompt
   - Launch **all** subagents in a single parallel batch so they run concurrently
   - Example: 3 domains = 6 parallel subagents (3 self-improve + 3 maintenance)

6. Collect and Summarize Results
   - Wait for all subagents to complete
   - Produce a **combined summary table** with columns:

     | Domain | Self-Improve | Maintenance | Notes |
     |--------|-------------|-------------|-------|
     | frontend | Updated 3 rules | Build OK, mappings OK | New slash-command patterns added |
     | backend | Updated 2 heuristics | Lint OK, 3 tools validated | Admin CRUD handlers documented |

   - For each DOMAIN, capture:
     - **Self-Improve**: Whether it succeeded, key updates to expertise (new rules, revised heuristics, added examples)
     - **Maintenance**: Whether checks passed, any failures or drift detected, recommended actions
   - Highlight any **cross-domain issues** (e.g., frontend expects an API that backend doesn't serve)
   - If any subagent failed, report the error and suggest re-running that specific expert
