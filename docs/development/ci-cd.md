# EAGLE CI/CD and Deployment

GitHub Actions is the standard deployment path for EAGLE. Manual `just` deploy commands remain supported for operator use, troubleshooting, and exceptional cases, but the default release workflow should go through `.github/workflows/deploy.yml`.

## Deployment Paths

| Path | Use When | Primary Commands |
|------|----------|------------------|
| GitHub Actions (standard) | Normal dev and QA deployments | `gh workflow run deploy.yml ...`, merge to `main` |
| Local development | Iterating on code and tests | `just dev`, `just dev-local`, `just validate` |
| Manual operator deploy | Need to push directly from a trusted environment | `just deploy`, `just deploy-backend`, `just deploy-frontend` |
| EC2 runner manual deploy | Need an in-VPC manual deploy path with instance-role credentials | SSM session -> `just deploy` |

## Standard Release Pipeline

The canonical deploy workflow is [`deploy.yml`](../../.github/workflows/deploy.yml).

### Triggers

- Push to `main` deploys to `dev`
- `workflow_dispatch` can target `dev` or `qa`
- `qa` is manual-only in the workflow

### Deploy Modes

The workflow chooses a deploy mode in the `changes` job:

- `auto`: default for manual runs; resolves to `full` for significant changes and `mini` otherwise
- `full`: runs lint, unit tests, CDK synth, integration health check, and optional eval
- `mini`: runs lint and deploy steps only
- `qa` always resolves to `mini`

### Path-Based Deploy Decisions

The workflow uses changed-path filters to decide whether to deploy:

- `infrastructure/**` triggers infra deployment
- `server/**`, `eagle-plugin/**`, and backend Docker files trigger backend deployment
- `client/**` and frontend Docker files trigger frontend deployment

For manual `workflow_dispatch`, `deploy_infra` and `deploy_app` inputs can force those deploy stages on.

## Pipeline Stages

### 1. Setup

- Resolves target environment (`dev` or `qa`)
- Computes ECS service names, ECR repository names, and stack names

### 2. Change Detection

- Determines which parts of the repo changed
- Resolves deploy mode (`mini` or `full`)

### 3. Validation Gates

#### Always in scope

- `lint`: Ruff for backend code and TypeScript compilation for the client

#### Full mode only

- `unit-tests`: backend pytest suite
- `cdk-synth`: CDK compile/synth check
- `integration`: launches the backend with `uvicorn` and waits for `/api/health`
- `eval`: optional Bedrock-backed eval job when `run_eval=true`

Important: eval is **not** part of every merge-to-main deploy. It only runs when explicitly enabled on `workflow_dispatch`.

### 4. Infrastructure Deployment

If infra changes are detected, or manual dispatch requests infra deployment:

- Assumes the GitHub OIDC deploy role
- Runs `cdk deploy`
- Deploys core stacks and the environment-specific compute stack

### 5. Application Deployment

Backend and frontend deploy independently:

- Build Docker images
- Push images to ECR with both `:latest` and `${github.sha}` tags
- Register new ECS task definitions pinned to the commit SHA
- Update ECS services and wait for stabilization
- Frontend deploy also refreshes ALB target registration

### 6. Reporting

- Sends a Teams deploy report with job outcomes

## Environment Model

### Active deploy targets in GitHub Actions

- `dev`: automatic on merge/push to `main`, or manual
- `qa`: manual only

### Other environment configs

The CDK config file also contains `staging` and `prod` shapes, but the default GitHub deploy workflow currently targets `dev` and `qa` only.

## Manual GitHub Actions Operations

### Deploy to dev manually

```bash
gh workflow run deploy.yml --ref main -f environment=dev
gh run watch
```

### Deploy a branch to QA

```bash
gh workflow run deploy.yml --ref <branch> -f environment=qa
gh run watch
```

### Run a full manual deploy with eval

```bash
gh workflow run deploy.yml \
  --ref main \
  -f environment=dev \
  -f deploy_mode=full \
  -f run_eval=true
```

## `just` Commands and Their Role

The `Justfile` is still important, but it serves two different purposes:

- local development and validation
- manual operator workflows outside the standard GitHub Actions path

### Local validation

```bash
just lint
just test
just smoke mid
just validate
just validate-full
```

### Manual operator deploys

```bash
just deploy
just deploy-backend
just deploy-frontend
just deploy-qa
```

### GitHub Actions helpers from the Justfile

```bash
just deploy-ci main
just deploy-qa-ci <branch>
just deploy-watch
just deploy-status
```

## Why GitHub Actions Is the Standard Path

- Deployments are tied to a workflow run and commit SHA
- The workflow applies consistent gating and path-based decisions
- Backend and frontend task definitions are pinned to the exact commit image
- Teams reporting and auditability come for free with the workflow

Manual `just deploy` is still useful, but it should be treated as an operator tool rather than the primary release path.

## Related Docs

- [Local Development](../setup/local-development.md)
- [EC2 Runner Manual Deploy](../setup/ec2-runner-deployment.md)
- [GitHub Workflow](./github-workflow.md)
