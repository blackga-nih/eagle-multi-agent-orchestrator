---
description: "Query AWS infrastructure, CDK, DynamoDB, IAM, or S3 without making changes"
allowed-tools: Read, Glob, Grep, Bash
---

# AWS Expert - Question Mode

> Read-only command to query AWS infrastructure knowledge without making any changes.

## Purpose

Answer questions about AWS infrastructure, CDK stacks, DynamoDB table design, IAM policies, S3 configuration, and the EAGLE platform resources — **without making any code or infrastructure changes**.

## Usage

```
/experts:aws:question [question]
```

## Allowed Tools

`Read`, `Glob`, `Grep`, `Bash` (read-only commands only)

## Question Categories

### Category 1: Infrastructure State
Questions about what AWS resources exist and how they are configured.

**Resolution**: Read `expertise.md` -> Parts 1-2

### Category 2: CDK Patterns
Questions about infrastructure-as-code patterns, CDK constructs, stack structure.

**Resolution**: Read `expertise.md` -> Part 3

### Category 3: DynamoDB Design
Questions about table design, key schemas, GSIs, access patterns.

**Resolution**: Read `expertise.md` -> Part 4

### Category 4: IAM Policies
Questions about permissions, roles, OIDC trust, least-privilege.

**Resolution**: Read `expertise.md` -> Part 5

### Category 5: Deployment Options
Questions about Next.js deployment (S3+CloudFront vs ECS Fargate).

**Resolution**: Read `expertise.md` -> Part 6

### Category 6: Docker
Questions about containerization, Dockerfile patterns, ECS configuration.

**Resolution**: Read `expertise.md` -> Part 7

### Category 7: CI/CD
Questions about GitHub Actions workflows, deployment pipelines.

**Resolution**: Read `expertise.md` -> Part 8

### Category 8: Troubleshooting
Questions about deployment failures or infrastructure issues.

**Resolution**: Read `expertise.md` -> Part 9

---

## Workflow

1. Read `.claude/commands/experts/aws/expertise.md`
2. Classify the question into one of the categories above
3. Read the relevant section(s)
4. If needed, check source files for implementation details
5. Provide formatted answer with code examples

## Report Format

```markdown
## Answer

{Direct answer to the question}

## Details

{Supporting information from expertise.md or source files}

## Source

- expertise.md -> {section}
- {source file}:{line} (if referenced)
```

## Instructions

1. **Read expertise.md first** - All knowledge is stored there
2. **Never modify files** - This is a read-only command
3. **Be specific** - Reference exact sections and provide code examples
4. **Suggest next steps** - If appropriate, suggest what command to run next
