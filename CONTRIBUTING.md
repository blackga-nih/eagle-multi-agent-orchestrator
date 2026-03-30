# Contributing to EAGLE

## Prerequisites

- **Python 3.11+** and **Node.js 20+**
- **Docker Desktop**
- **[just](https://github.com/casey/just)** task runner
- **AWS CLI** configured with SSO profile `eagle`

## Development Setup

See the [Local Development checklist](README.md#checklist-a-local-development) in the README.

```bash
cp .env.example .env    # configure environment
just dev                # start full stack via Docker Compose
```

## Branch Naming

```
dev-{name}-{YYYYMMDD}    # feature/fix branches
main                      # production — PRs required
```

## Commit Messages

- Use imperative mood: "Add feature" not "Added feature"
- Keep subject line under 72 characters
- Reference Jira ticket when applicable: `EAGLE-42: Add PDF export`

## Validation Before PR

Run the validation ladder before opening a pull request:

| Level | Command | When |
|-------|---------|------|
| L1 — Lint | `just lint` | Every change |
| L2 — Unit | `just test` | Backend changes |
| L3 — Smoke | `just smoke mid` | Frontend changes |
| L4 — Infra | `just cdk-synth` | CDK changes |
| L5 — Integration | `just validate` | Before any PR |

```bash
just validate       # runs L1-L5 in sequence
```

## Code Style

| Language | Tool | Command |
|----------|------|---------|
| Python | ruff (lint + format) | `just lint-py` / `just format-py` |
| TypeScript | ESLint + Prettier | `just lint-ts` / `just format-ts` |

Run `just format` to auto-format all code before committing.

## Plugin Content

Agent and skill definitions live in `eagle-plugin/`, not `server/app/`. The server auto-discovers plugin content at runtime via `server/eagle_skill_constants.py`.

- **Agents**: `eagle-plugin/agents/{name}/agent.md`
- **Skills**: `eagle-plugin/skills/{name}/SKILL.md`
- **Manifest**: `eagle-plugin/plugin.json`

## AI-Assisted Development

This project uses Claude Code for development. See `CLAUDE.md` for conventions, artifact naming, and expert system usage.

## License

Internal NCI use only. See [LICENSE](LICENSE).
