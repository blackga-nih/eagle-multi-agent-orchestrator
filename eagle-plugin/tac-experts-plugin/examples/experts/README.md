# Expert Examples

Real working expert patterns from the EAGLE project. These show how domain experts accumulate knowledge and provide specialized commands.

## AWS Expert (Full Domain)

The AWS expert demonstrates a mature expert with domain-specific extensions:

```
.claude/commands/experts/aws/
├── _index.md              ← Lists all commands + current infrastructure state
├── expertise.md           ← 9 Parts: infrastructure, resources, CDK, DynamoDB, IAM, Docker, CI/CD
├── question.md            ← 8 question categories matching 8 Parts
├── plan.md                ← 4 phases with CDK/DynamoDB/IAM plan templates
├── plan_build_improve.md  ← Inline boto3 connectivity checks in validation
├── self-improve.md        ← Updates resource inventory + CDK patterns on change
├── maintenance.md         ← boto3 smoke tests for each AWS service
└── cdk-scaffold.md        ← DOMAIN-SPECIFIC: 5 CDK stack templates (TypeScript)
```

**Key patterns**:
- `expertise.md` has 9 Parts covering every AWS concern, with actual resource IDs
- `maintenance.md` includes inline Python boto3 checks (not just file scanning)
- `cdk-scaffold.md` is a domain-specific extension with 5 stack type templates
- `self-improve.md` updates resource inventory when new infrastructure is discovered

## Hooks Expert (Newer Pattern)

The hooks expert shows the evolution — comprehensive but newer, still gaining learnings:

```
.claude/commands/experts/hooks/
├── expertise.md           ← 9 Parts: 12 events, 7 patterns, architecture, recipes
├── question.md            ← 6 categories: events, patterns, config, agents, observability
├── plan.md                ← Event/Pattern/Architecture decision tables
└── self-improve.md        ← Scans actual hooks vs documented, updates coverage
```

**Key patterns**:
- `expertise.md` sourced from multiple reference implementations
- Missing `_index.md`, `plan_build_improve.md`, `maintenance.md` (in progress)
- Shows that experts can be useful even when incomplete

## Eval Expert (Domain Extension)

The eval expert shows the `add-{thing}` scaffold pattern:

```
.claude/commands/experts/eval/
├── ... (standard 7 files)
└── add-test.md            ← 8-registration SOP with 3 tier templates
```

**Key pattern**: `add-test.md` encodes an exact checklist of 8 places to register a new test across 4 files. The agent follows this checklist and validates with `grep -c` that all 8 registrations exist.

## Git Expert (Workflow Extension)

```
.claude/commands/experts/git/
├── ... (standard 7 files)
└── workflow-scaffold.md   ← 4 GitHub Actions workflow templates (CI, CD, PR, Release)
```

**Key pattern**: `workflow-scaffold.md` takes a `$ARGUMENTS` type selector and generates the appropriate workflow from templates. SHA-pins all actions, includes OIDC patterns.

## Creating Your Own Domain Expert

1. Copy templates from `../templates/expert/`
2. Replace all `{{PLACEHOLDER}}` values
3. Fill `expertise.md` Part 1 with initial domain knowledge
4. Run `/experts:tac:maintenance --experts` to validate structure
5. Start using the expert — run `self-improve` after each significant task
6. Add domain-specific extensions as patterns emerge (like `cdk-scaffold`, `add-test`)
