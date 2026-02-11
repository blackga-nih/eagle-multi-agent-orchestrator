# Expert System Expansion: AWS Expert + Git/CI-CD Expert + Integration

## Overview

Expand the expert ecosystem from 7 to 9 experts by:
1. **Upgrading** `deployment` expert → `aws` expert (broader scope: CDK, DynamoDB table design, AWS docs crawling)
2. **Creating** new `git` expert (Git operations, GitHub Actions, CI/CD pipelines, release management)
3. **Integrating** both with existing experts (eval, cloudwatch, backend, frontend)

---

## Plan 1: AWS Expert (Upgrade from Deployment)

### Rationale

The current `deployment` expert already covers CDK, Docker, CI/CD, and AWS resources. Rather than creating a separate CDK expert, we **upgrade and rename** it to `aws` — a broader expert that adds:
- CDK stack authoring (not just reference patterns)
- DynamoDB table design and GSI planning
- AWS documentation crawling via Context7 MCP server
- IAM policy generation
- CloudFormation template analysis

### File Changes

| File | Action | Description |
|------|--------|-------------|
| `experts/aws/_index.md` | CREATE | New index replacing deployment |
| `experts/aws/expertise.md` | CREATE | Expanded mental model (CDK authoring, DDB design, IAM) |
| `experts/aws/question.md` | CREATE | Updated question command with AWS docs crawling |
| `experts/aws/plan.md` | CREATE | Planning with CDK synth validation |
| `experts/aws/plan_build_improve.md` | CREATE | Full workflow with CDK deploy steps |
| `experts/aws/self-improve.md` | CREATE | Learning from deployments |
| `experts/aws/maintenance.md` | CREATE | AWS health checks (carry forward from deployment) |
| `experts/aws/cdk-scaffold.md` | CREATE | New: scaffold CDK stacks from templates |
| `experts/deployment/*` | KEEP | Keep deployment as alias/redirect to aws |

### New Expertise Sections

The `expertise.md` expands with:

**Part 8: DynamoDB Table Design**
- Key schema patterns (PK/SK composition)
- GSI design patterns
- Access pattern → key schema mapping
- Capacity modes (on-demand vs provisioned)
- TTL configuration

**Part 9: IAM Policy Patterns**
- Least-privilege policy templates for each AWS service
- OIDC trust policy generation
- Service role patterns (ECS task role, Lambda execution role)
- Cross-account access patterns

**Part 10: AWS Documentation Crawling**
- Integration with Context7 MCP server for AWS docs
- Pattern: fetch CDK construct docs for specific services
- Pattern: look up CloudFormation resource properties
- Caching strategy for frequently-accessed docs

### New Command: `cdk-scaffold`

Scaffolds new CDK stacks from templates:
```
/experts:aws:cdk-scaffold storage    → S3 + DynamoDB stack
/experts:aws:cdk-scaffold compute    → ECS Fargate + ECR stack
/experts:aws:cdk-scaffold network    → VPC + ALB + CloudFront stack
/experts:aws:cdk-scaffold monitoring → CloudWatch dashboard + alarms stack
/experts:aws:cdk-scaffold pipeline   → CodePipeline + CodeBuild stack
```

### Skill Registration

Add to available skills list:
- `experts:aws:_index`
- `experts:aws:question`
- `experts:aws:plan`
- `experts:aws:plan_build_improve`
- `experts:aws:self-improve`
- `experts:aws:maintenance`
- `experts:aws:expertise`
- `experts:aws:cdk-scaffold`

---

## Plan 2: Git/CI-CD Expert (New)

### Rationale

Git operations, GitHub Actions workflows, branching strategy, and release management deserve a dedicated expert. Currently:
- `deploy.yml` uses static IAM keys (should use OIDC)
- `claude-merge-analysis.yml` exists but isn't documented in any expert
- No expert covers branch protection, PR workflows, or release tagging
- Git operations scattered across deployment expert

### File Structure

```
.claude/commands/experts/git/
  _index.md              — Expert overview
  expertise.md           — Complete Git/CI-CD mental model
  question.md            — Read-only Q&A about Git/CI-CD
  plan.md                — Plan Git/CI-CD changes
  plan_build_improve.md  — Full workflow
  self-improve.md        — Learn from CI/CD outcomes
  maintenance.md         — Validate workflows, check Actions status
  workflow-scaffold.md   — Scaffold new GitHub Actions workflows
```

### Expertise Sections

**Part 1: Repository Structure**
- Branch naming conventions (main, dev/*, feat/*, fix/*, release/*)
- Current branches and their purposes
- Protected branch rules
- Merge strategy (squash vs merge vs rebase)

**Part 2: GitHub Actions Workflows**
- Existing workflows inventory (deploy.yml, claude-merge-analysis.yml)
- Workflow trigger patterns (push, PR, schedule, dispatch)
- Action pinning conventions (SHA-based for security)
- Secrets management (${{ secrets.* }})
- OIDC authentication pattern

**Part 3: CI Pipeline Patterns**
- Lint + type-check + test pipeline
- Python backend: pytest + mypy + ruff
- Next.js frontend: npm ci + build + lint
- Parallel job execution for speed
- Caching strategies (npm cache, pip cache)

**Part 4: CD Pipeline Patterns**
- CDK deploy workflow (synth → diff → deploy)
- Docker build + ECR push workflow
- S3 static deploy + CloudFront invalidation
- ECS rolling update pattern
- Environment promotion (dev → staging → prod)

**Part 5: Release Management**
- Semantic versioning (MAJOR.MINOR.PATCH)
- Git tag creation and conventions
- Changelog generation
- GitHub Releases with notes
- Rollback procedures

**Part 6: Claude Code Action Integration**
- anthropics/claude-code-action@v1 patterns
- Merge analysis workflow (existing)
- PR review automation
- Issue triage automation
- Structured outputs → GitHub Actions outputs

**Part 7: Known Issues**
- Action SHA pinning vs version tags
- Secrets not available in fork PRs
- OIDC vs static credentials tradeoffs
- Workflow dispatch manual triggers

### New Command: `workflow-scaffold`

Scaffolds GitHub Actions workflows:
```
/experts:git:workflow-scaffold ci       → Lint + test pipeline
/experts:git:workflow-scaffold cd       → CDK/Docker deploy pipeline
/experts:git:workflow-scaffold pr       → PR checks + Claude review
/experts:git:workflow-scaffold release  → Tag + changelog + GitHub Release
```

---

## Plan 3: Integration Strategy

### Cross-Expert Workflows

| Workflow | Experts Involved | Trigger |
|----------|-----------------|---------|
| Deploy new CDK stack | aws → git (PR + CI) → cloudwatch (verify metrics) | `/experts:aws:plan_build_improve` |
| Add eval test + publish | eval → cloudwatch → aws (CDK update for new metrics) | `/experts:eval:plan_build_improve` |
| Frontend deploy | frontend → aws (CDK/S3) → git (CI/CD) | `/experts:frontend:plan_build_improve` |
| Backend update | backend → eval (test) → git (commit) → aws (deploy) | `/experts:backend:plan_build_improve` |
| Full release | git (tag) → aws (deploy) → cloudwatch (verify) → eval (smoke test) | `/experts:git:workflow-scaffold release` |

### Shared Expertise References

Each expert's `expertise.md` includes a cross-reference section:

```markdown
## Cross-References

| Related Expert | When to Use |
|---------------|-------------|
| aws | When changes require infrastructure updates |
| git | When changes need CI/CD pipeline modifications |
| eval | When changes need test coverage |
| cloudwatch | When changes affect telemetry |
```

### Integration Points

1. **aws ↔ git**: CDK deploy triggered by Git push via GitHub Actions
2. **aws ↔ cloudwatch**: CDK stacks include CloudWatch resources
3. **aws ↔ eval**: Eval stack (`infra/eval/`) managed by CDK
4. **git ↔ eval**: CI pipeline runs eval suite on PR
5. **git ↔ frontend**: CI pipeline builds + deploys frontend
6. **git ↔ backend**: CI pipeline deploys backend service

### Deployment Expert Transition

- Keep `experts/deployment/` directory with a redirect `_index.md` pointing to `experts/aws/`
- All `/experts:deployment:*` commands still work (redirect stubs)
- Update memory/MEMORY.md to reference new expert names

---

## Implementation Order

1. Create `experts/aws/` directory with all 8 files
2. Create `experts/git/` directory with all 8 files
3. Add cross-reference sections to existing experts (eval, cloudwatch, backend, frontend)
4. Add redirect stubs in `experts/deployment/` pointing to aws
5. Update MEMORY.md

## Verification

1. All new slash commands appear in skill list
2. `/experts:aws:question what CDK stacks exist?` — returns coherent answer
3. `/experts:git:question what GitHub Actions workflows exist?` — returns coherent answer
4. `/experts:aws:maintenance` — runs AWS health checks successfully
5. `/experts:git:maintenance` — validates workflow syntax
