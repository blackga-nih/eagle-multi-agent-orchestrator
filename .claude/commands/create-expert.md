---
description: "Create a new expert domain — scaffolds all 8 standard command files from an existing expert as template"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
argument-hint: [domain-name] [one-line description of what this expert covers]
model: opus
---

# Create New Expert Domain

> Scaffold a complete expert domain with all 8 standard command files, expertise mental model, and index.

## Variables

- `TASK`: $ARGUMENTS

## Instructions

- **CRITICAL**: You ARE creating files. Scaffold the full expert domain.
- If no `TASK` is provided, STOP and ask the user: domain name and what the expert covers.
- Parse `TASK` to extract:
  - `DOMAIN`: the domain slug (e.g., `strands`, `security`, `testing`)
  - `DESCRIPTION`: one-line scope description

---

## Step 1: Validate Domain Name

1. Check that `.claude/commands/experts/{DOMAIN}/` does not already exist
2. Domain name rules: lowercase, alphanumeric + hyphens only, no spaces
3. If domain exists, ask user: update existing or pick a new name?

## Step 2: Discover Template Expert

1. List all existing expert domains:
   ```
   ls .claude/commands/experts/
   ```
2. Pick the best template based on similarity to the new domain's scope:
   - For SDK/tool domains: use `strands` as template
   - For infrastructure domains: use `aws` or `deployment`
   - For code domains: use `backend` or `frontend`
   - For process domains: use `tac` or `git`
   - Default fallback: use `strands` (newest, cleanest structure)

3. Read the template's `_index.md` to understand the standard structure

## Step 3: Scaffold All 9 Files

Create `.claude/commands/experts/{DOMAIN}/` with these files:

### 3.1 `_index.md` — Domain Index

```markdown
---
type: expert-file
file-type: index
domain: {DOMAIN}
tags: [expert, {DOMAIN}, {relevant-tags}]
---

# {Title} Expert

> {DESCRIPTION}

## Domain Scope
- bullet list of what this expert covers

## Available Commands
| Command | Purpose |
|---------|---------|
| `/experts:{DOMAIN}:question` | Answer questions without coding |
| `/experts:{DOMAIN}:plan` | Plan changes using expertise |
| `/experts:{DOMAIN}:self-improve` | Update expertise after sessions |
| `/experts:{DOMAIN}:plan_build_improve` | Full ACT-LEARN-REUSE workflow |
| `/experts:{DOMAIN}:maintenance` | Health checks and validation |
| `/experts:{DOMAIN}:cheat-sheet` | Quick-reference with code samples |

## Key Files
| File | Purpose |
|------|---------|
| `expertise.md` | Complete mental model |
| `question.md` | Read-only query command |
| `plan.md` | Planning command |
| `self-improve.md` | Expertise update command |
| `plan_build_improve.md` | Full workflow command |
| `maintenance.md` | Validation and health checks |
| `cheat-sheet.md` | Quick reference |

## Key Source Files
| File | Content |
|------|---------|
| {relevant source files for this domain} |

## ACT-LEARN-REUSE Pattern
ACT -> Write {DOMAIN} integrations
LEARN -> Update expertise.md with behaviors and gotchas
REUSE -> Apply patterns to future {DOMAIN} work
```

### 3.2 `expertise.md` — Mental Model

Structure with:
- YAML frontmatter (type, file-type, domain, last_updated, tags)
- Part 1: Overview & key concepts
- Part 2-N: Domain-specific sections (read source files to populate)
- Learnings section with subsections: patterns_that_work, patterns_to_avoid, common_issues, tips

**CRITICAL**: Read the actual source code files relevant to this domain and populate the expertise with real patterns, not placeholders. The expertise should be immediately useful.

### 3.3 `question.md` — Read-Only Query

```yaml
---
description: "Query {DOMAIN} features, patterns, or get answers without making changes"
allowed-tools: Read, Glob, Grep, Bash
---
```

Categories should match the domain's key areas. Always:
1. Read expertise.md first
2. Never modify files
3. Include code samples
4. Reference exact sections

### 3.4 `plan.md` — Planning Command

```yaml
---
description: "Plan {DOMAIN} changes — {specific actions} — using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature or change to plan]
---
```

Phases: Load Context -> Analyze Current State -> Generate Plan -> Save Plan

### 3.5 `self-improve.md` — Expertise Update

```yaml
---
description: "Update {DOMAIN} expertise with learnings from implementations and debugging"
allowed-tools: Read, Write, Edit, Grep, Glob
argument-hint: [component] [outcome: success|failed|partial]
---
```

Phases: Gather Information -> Analyze Outcome -> Update expertise.md -> Update timestamp

### 3.6 `plan_build_improve.md` — Full Workflow

```yaml
---
description: "Full ACT-LEARN-REUSE workflow: plan {DOMAIN} changes, implement them, validate, and update expertise"
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: [feature to implement]
---
```

Steps: PLAN -> VALIDATE (baseline) -> BUILD -> VALIDATE (post) -> REVIEW -> IMPROVE

### 3.7 `maintenance.md` — Health Checks

```yaml
---
description: "Check {DOMAIN} health — {specific checks}"
allowed-tools: Bash, Read, Grep, Glob
argument-hint: [--import | --full | specific check flag]
---
```

Domain-specific validation commands. Always include:
- Import/dependency checks
- Configuration validation
- Cross-reference integrity checks

### 3.8 `cheat-sheet.md` — Quick Reference

```yaml
---
description: "Quick-reference cheat sheet for {DOMAIN} with copy-pasteable code samples"
allowed-tools: Read
---
```

Concise, numbered sections with working code from the actual codebase.

## Step 4: Populate Expertise from Source Code

1. Search the codebase for files relevant to this domain
2. Read key files and extract patterns
3. Write real, actionable content into `expertise.md` — not boilerplate
4. Include actual file paths, line references, and working code samples

## Step 5: Validate

```bash
# Verify all 8 files exist
ls .claude/commands/experts/{DOMAIN}/

# Verify frontmatter is valid (no YAML errors)
for f in .claude/commands/experts/{DOMAIN}/*.md; do
  head -1 "$f" | grep -q "^---" && echo "OK: $f" || echo "MISSING FRONTMATTER: $f"
done
```

## Step 6: Report

```markdown
## New Expert Created: {DOMAIN}

### Files Created
| File | Lines | Status |
|------|-------|--------|
| _index.md | {N} | Created |
| expertise.md | {N} | Created |
| question.md | {N} | Created |
| plan.md | {N} | Created |
| self-improve.md | {N} | Created |
| plan_build_improve.md | {N} | Created |
| maintenance.md | {N} | Created |
| cheat-sheet.md | {N} | Created |

### Available Commands
/experts:{DOMAIN}:question
/experts:{DOMAIN}:plan
/experts:{DOMAIN}:add-tool (if applicable)
/experts:{DOMAIN}:self-improve
/experts:{DOMAIN}:plan_build_improve
/experts:{DOMAIN}:maintenance
/experts:{DOMAIN}:cheat-sheet

### Next Steps
- Run `/experts:{DOMAIN}:maintenance --full` to validate
- Run `/experts:{DOMAIN}:self-improve` after first usage to refine
```
