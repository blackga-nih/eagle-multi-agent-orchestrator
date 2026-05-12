# AGENTS.md — sm_eagle

Lightweight pointer file for AI coding assistants (Claude Code, Cursor, etc.)
that look for `AGENTS.md` at the repo root. Authoritative project guidance
lives in [`CLAUDE.md`](./CLAUDE.md). This file just orients an agent in 30
seconds.

## What this repo is

EAGLE — multi-tenant AI acquisition assistant for NCI. Next.js frontend +
FastAPI backend + Strands Agents SDK orchestrating supervisor → specialist
subagents via Bedrock. Full architecture in [`CLAUDE.md`](./CLAUDE.md).

## Where AI agents live

| Layer | Location |
|-------|----------|
| Project-level Claude Code skills | `.claude/skills/` |
| Project-level subagents | `.claude/agents/` |
| Domain experts (`/experts:{domain}:*`) | `.claude/commands/experts/` — 9 domains: frontend, backend, aws, claude-sdk, deployment, cloudwatch, eval, git, tac |
| Implementation specs | `.claude/specs/` |
| EAGLE app agents + skills (runtime, not Claude Code) | `eagle-plugin/agents/` and `eagle-plugin/skills/` |

## Notable repo-level skills

| Skill | Purpose |
|-------|---------|
| `claude-handoff` | Bundle the originating dev's `~/.claude/` slice + scrubbed session JSONLs into a portable folder a co-worker can drop into their own machine. Co-located scrubber redacts AWS keys, GitHub PATs, Anthropic keys, and the originator's usernames before any bytes leave the host. |
| `pp-claude-sessions` | Printing-Press-shaped read-only CLI over Claude Code session JSONLs. Subcommands: `list`, `show`, `search`, `tools`, `stats`, `which`, `doctor`, `feedback`. Stdlib Python 3.10+ (no Go, no npm). Default source `./session-history/jsonl/`; override with `--src`. `--agent` flag expands to JSON+compact+no-prompt for piping. |

## Conventions an agent should follow

- **Validation ladder** (per [`CLAUDE.md`](./CLAUDE.md)): ruff → tsc → pytest → playwright → cdk synth. Backend changes need 1+2 minimum; CDK needs 1+4; production deploys need full ladder + post-deploy smoke.
- **Artifact naming**: `{YYYYMMDD}-{HHMMSS}-{type}-{slug}-v{N}.{ext}` — scan destination for highest `vN`, never overwrite.
- **Never edit `expertise.md`** under `.claude/commands/experts/{domain}/` by hand — run `/experts:{domain}:self-improve`.
- **Plugin source of truth**: `eagle-plugin/` — never put agent/skill content in `server/app/`, modify `eagle-plugin/` only.
- **Branch convention**: PRs against `main`, no direct pushes. See `memory/git-workflow.md` (loaded into auto-memory).

## When you need more

Read [`CLAUDE.md`](./CLAUDE.md) for the full picture — tech stack, architecture, project structure, code patterns, validation rules, and the post-deploy smoke harness.
