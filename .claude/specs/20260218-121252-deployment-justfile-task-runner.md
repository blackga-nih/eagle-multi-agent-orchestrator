# Plan: Unified Justfile Task Runner

## Summary

Create a `Justfile` at project root that consolidates all build, test, deploy, and ops commands into a single entry point. Replaces fragmented scripts with a discoverable, composable task runner.

## Files to Create

| File | Purpose |
|------|---------|
| `Justfile` | Main task runner (project root) |

## Files to Update

None — additive only.

## Commands

### Development
| Command | What it does |
|---------|-------------|
| `just dev` | Start backend + frontend locally (docker compose) |
| `just dev-backend` | Start FastAPI dev server only |
| `just dev-frontend` | Start Next.js dev server only |

### Lint & Test
| Command | What it does |
|---------|-------------|
| `just lint` | Run ruff (Python) + tsc --noEmit (TypeScript) |
| `just lint-py` | Run ruff check on server/ |
| `just lint-ts` | Run tsc --noEmit on client/ |
| `just test` | Run pytest (backend) |
| `just test-e2e` | Run Playwright tests against Fargate URL |

### Eval
| Command | What it does |
|---------|-------------|
| `just eval` | Run full eval suite (28 tests, haiku) + publish |
| `just eval-quick TESTS` | Run specific tests (e.g. `just eval-quick 1,2,3`) |
| `just eval-aws` | Run AWS tool tests only (16-20) |

### Build & Deploy
| Command | What it does |
|---------|-------------|
| `just build` | Docker compose build (local) |
| `just build-backend` | Build backend Docker image |
| `just build-frontend` | Build frontend Docker image with Cognito args |
| `just deploy` | Full deploy: build → ECR push → ECS update → wait |
| `just deploy-backend` | Deploy backend only |
| `just deploy-frontend` | Deploy frontend only |

### Infrastructure
| Command | What it does |
|---------|-------------|
| `just cdk-synth` | Synthesize CDK stacks (validate) |
| `just cdk-diff` | Show pending CDK changes |
| `just cdk-deploy` | Deploy all CDK stacks |

### Operations
| Command | What it does |
|---------|-------------|
| `just status` | Show ECS service health + URLs |
| `just logs SERVICE` | Tail ECS logs (backend/frontend) |
| `just urls` | Print frontend + backend URLs |
| `just check-aws` | Verify AWS credentials + service connectivity |

### Composite
| Command | What it does |
|---------|-------------|
| `just ci` | Full CI: lint → test → eval-aws |
| `just ship` | Full ship: lint → build → deploy → status |

## Constants (top of Justfile)

```
REGION := "us-east-1"
CLUSTER := "eagle-dev"
BACKEND_SERVICE := "eagle-backend-dev"
FRONTEND_SERVICE := "eagle-frontend-dev"
BACKEND_REPO := "eagle-backend-dev"
FRONTEND_REPO := "eagle-frontend-dev"
ACCOUNT := `aws sts get-caller-identity --query Account --output text`
ECR_REGISTRY := ACCOUNT + ".dkr.ecr." + REGION + ".amazonaws.com"
```

## Validation

```bash
just --list     # Should show all commands
just lint       # Should run without errors
just status     # Should show ECS state
```

## Rollback

Delete `Justfile` — no other files affected.

## Cost Impact

None — local tooling only.
