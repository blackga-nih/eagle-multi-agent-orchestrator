---
description: Scan session log (or provided expert list) to launch expert self-improve subagents in parallel.
argument-hint: [optional space-separated expert domains, e.g. `eval git tac`]
---

# Parallel Expert Self-Improve

Use this command at the end of a substantial coding session to automatically identify which domain experts were involved and trigger their `self-improve` routines in parallel.

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
   - List subdirectories in EXPERTS_DIR to determine available domains (e.g., `frontend`, `backend`, `aws`, `deployment`, `claude-sdk`, `cloudwatch`, `eval`, `git`, `tac`, `hooks`)
   - For each domain, check that a `self-improve.md` command exists
   - Build a set AVAILABLE_DOMAINS of domains that support `self-improve`

3. Select Relevant Domains
   - If ARGS was provided (non-empty):
     - INTERSECT the requested domains with AVAILABLE_DOMAINS
     - Drop any unknown or unsupported domains, but record them so they can be reported back to the user
     - If the intersection is empty, abort with a clear message that none of the requested experts support `self-improve`
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

4. Design Expert Self-Improve Prompts
   - For each relevant DOMAIN:
     - Construct a concise, self-contained prompt summarizing:
       - What changed in that domain during this session (files, features, refactors, fixes)
       - Any tests, linting, or validation that were run
       - Open questions or edge cases discovered
     - The prompt should instruct the expert to:
       - Validate its current `expertise.md` against the latest code and patterns
       - Update or refine examples, heuristics, and anti-patterns
       - Capture new workflows or pitfalls observed in this session

5. Launch Parallel Expert Subagents
   - For each relevant DOMAIN, spawn a subagent using the Task tool
   - Each subagent should:
     - Execute the corresponding expert command `/experts:{DOMAIN}:self-improve`
     - Use the domain-specific summary from step 4 as input context
   - Launch all expert subagents in a single parallel batch so they run concurrently

6. Collect and Summarize Expert Updates
   - Wait for all expert subagents to complete
   - For each DOMAIN:
     - Capture whether `self-improve` succeeded
     - Note any key updates the expert reported (new rules, revised heuristics, added examples)
   - Produce a concise summary that includes:
     - The list of domains that ran `self-improve`
     - Any notable changes to expert guidance that future sessions should be aware of

