---
description: "Validate {{DOMAIN}} health and compliance"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [--all | --quick | --structure | --freshness]
---

# {{DOMAIN_TITLE}} Expert - Maintenance Command

Validate {{DOMAIN}} health across structure, freshness, and compliance.

## Usage

```
/experts:{{DOMAIN}}:maintenance --all
/experts:{{DOMAIN}}:maintenance --quick
/experts:{{DOMAIN}}:maintenance --structure
/experts:{{DOMAIN}}:maintenance --freshness
```

## Presets

| Flag | Scope | Description |
|------|-------|-------------|
| `--all` | Everything | Full {{DOMAIN}} health audit |
| `--quick` | Smoke test | Fast connectivity/structure check |
| `--structure` | Files | Validate expert files and source structure |
| `--freshness` | Expertise | Check if expertise.md is up to date |

## Workflow

### Phase 1: Discovery

1. Scan expert files:
   ```
   Glob: .claude/commands/experts/{{DOMAIN}}/*.md
   ```
2. Scan source files:
   ```
   Glob: {{SOURCE_GLOB_PATTERN}}
   ```

### Phase 2: Structure Validation

- Required expert files present? (_index.md, expertise.md, question.md, plan.md, self-improve.md, plan_build_improve.md, maintenance.md)
- Frontmatter valid? (type, file-type, allowed-tools, description)
- Cross-references consistent?

### Phase 3: Freshness Check

- `last_updated` in expertise.md — how old?
- Recent source changes not reflected in expertise?
- Learnings section populated?

### Phase 4: Domain-Specific Checks

```bash
{{DOMAIN_VALIDATION_COMMAND}}
```

### Phase 5: Report

## Report Format

```markdown
## {{DOMAIN_TITLE}} Maintenance Report

**Date**: {timestamp}
**Scope**: {preset}
**Status**: HEALTHY | NEEDS_ATTENTION | STALE

### Expert Structure

| File | Status | Notes |
|------|--------|-------|
| _index.md | OK/MISSING | |
| expertise.md | OK/MISSING | last_updated: {date} |
| question.md | OK/MISSING | |
| plan.md | OK/MISSING | |
| self-improve.md | OK/MISSING | |
| plan_build_improve.md | OK/MISSING | |
| maintenance.md | OK/MISSING | |

### Freshness

| Check | Status | Notes |
|-------|--------|-------|
| Expertise age | OK/WARN | Last updated: {date} |
| Recent changes | OK/WARN | {N} source changes since last update |
| Learnings populated | OK/WARN | {N} entries |

### Domain Health

| Check | Status | Notes |
|-------|--------|-------|
| {{DOMAIN_CHECK_1}} | PASS/FAIL | {details} |
| {{DOMAIN_CHECK_2}} | PASS/FAIL | {details} |

### Issues Found

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | {HIGH/MED/LOW} | {description} | {suggested fix} |

### Next Steps

- {recommended actions}
```
