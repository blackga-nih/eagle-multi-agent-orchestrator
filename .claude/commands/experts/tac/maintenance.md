---
description: "Validate TAC compliance — check expert structure, hook patterns, command coverage, and methodology adherence"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [--all | --experts | --hooks | --commands | --compliance]
---

# TAC Expert - Maintenance Command

Validate TAC compliance across the project's agentic infrastructure.

## Purpose

Run TAC compliance checks to verify that experts, hooks, commands, and project structure follow TAC methodology. Identifies drift, missing files, broken patterns, and anti-patterns.

## Usage

```
/experts:tac:maintenance --all
/experts:tac:maintenance --experts
/experts:tac:maintenance --hooks
/experts:tac:maintenance --commands
/experts:tac:maintenance --compliance
```

## Presets

| Flag | Scope | Description |
|------|-------|-------------|
| `--all` | Everything | Full TAC compliance audit |
| `--experts` | Expert system | Validate expert directory structure and files |
| `--hooks` | Hook architecture | Check hooks follow TAC flat structure |
| `--commands` | Slash commands | Verify command coverage and frontmatter |
| `--compliance` | TAC principles | Check adherence to 8 tactics across project |

## Workflow

### Phase 1: Discovery

1. Scan the project for TAC components:
   ```
   Glob: .claude/commands/experts/*/_index.md
   Glob: .claude/commands/experts/*/expertise.md
   Glob: .claude/commands/experts/*/*.md
   Glob: .claude/commands/*.md
   Glob: .claude/hooks/*
   ```

2. Inventory what exists:
   - Number of experts
   - Commands per expert
   - Hooks registered
   - CLAUDE.md present and current

---

### Phase 2: Expert Structure Validation (--experts)

For each expert directory found:

**Required files check:**

| File | Required | Check |
|------|----------|-------|
| `_index.md` | Yes | Exists, has `type: expert-file` and `file-type: index` frontmatter |
| `expertise.md` | Yes | Exists, has `type: expert-file` and `file-type: expertise` frontmatter |
| `question.md` | Recommended | Has `allowed-tools:` frontmatter |
| `plan.md` | Recommended | Has `allowed-tools:` frontmatter |
| `self-improve.md` | Recommended | Has `allowed-tools:` with Edit |
| `plan_build_improve.md` | Recommended | Has `allowed-tools:` with full set |
| `maintenance.md` | Recommended | Has `allowed-tools:` frontmatter |

**Frontmatter validation:**
```
Grep: "^type: expert-file" in _index.md and expertise.md
Grep: "^file-type:" in _index.md and expertise.md
Grep: "^allowed-tools:" in command files
Grep: "^description:" in command files
```

**Cross-reference check:**
- Every command listed in `_index.md` has a corresponding file
- Every file in the directory is listed in `_index.md`

---

### Phase 3: Hook Architecture Validation (--hooks)

**Flat structure check:**
```
Glob: .claude/hooks/*
Glob: .claude/hooks/**/*
```
- PASS if no subdirectories found (flat structure per TAC Part 5)
- WARN if nested directories detected

**Dispatcher pattern check:**
```
Grep: "stop-dispatcher" in .claude/hooks/
```
- Check if a dispatcher exists for stop hooks
- Check if individual stop hooks are routed through the dispatcher

**Hook syntax check:**
```bash
bash -n .claude/hooks/*.sh 2>&1
```

**Hook conventions:**
- Named `{type}-{domain}.sh`
- Idempotent (check for guard clauses)
- Non-blocking (check for `exit 0` fallback)

---

### Phase 4: Command Coverage Validation (--commands)

**Standard command check per expert:**

| Command | Purpose | TAC Principle |
|---------|---------|---------------|
| `question` | Read-only Q&A | Tactic 2 (Adopt Perspective) |
| `plan` | Planning | Tactic 4 (Stay Out Loop) |
| `self-improve` | Learning | ACT-LEARN-REUSE |
| `plan_build_improve` | Full workflow | ACT-LEARN-REUSE |
| `maintenance` | Validation | Tactic 5 (Feedback Loops) |

For each expert, check which standard commands are present vs missing.

**Frontmatter consistency:**
```
Grep: "allowed-tools:" in .claude/commands/experts/*/*.md
```
- `question.md` should have read-only tools (Read, Grep, Glob)
- `self-improve.md` should include Edit
- `plan_build_improve.md` should include full tool set

---

### Phase 5: TAC Compliance Audit (--compliance)

**Core Four check:**

| Component | Path | Status |
|-----------|------|--------|
| CLAUDE.md | `CLAUDE.md` | Exists? |
| Commands | `.claude/commands/` | Has files? |
| Experts | `.claude/commands/experts/` | Has domains? |
| Settings | `.claude/settings.json` | Exists? |

**Self-improvement check:**
- Every expert with `expertise.md` also has `self-improve.md`?
- `expertise.md` files have `last_updated` in frontmatter?
- Learnings section exists in each expertise.md?

**Anti-pattern scan:**
```
Grep: "TODO" in .claude/commands/experts/*/expertise.md
Grep: "FIXME" in .claude/commands/experts/*/*.md
```
- Flag stale TODOs or FIXMEs in expertise files

**Layer classification:**
- Class 1 (Foundation): CLAUDE.md, settings.json present?
- Class 2 (Out-Loop): Commands and hooks present?
- Class 3 (Orchestration): At least one expert with full command set?

---

### Phase 6: Report

Generate a structured compliance report.

## Report Format

```markdown
## TAC Maintenance Report

**Date**: {timestamp}
**Scope**: {preset}
**Status**: COMPLIANT | PARTIAL | NON-COMPLIANT

### Expert System

| Expert | _index | expertise | question | plan | self-improve | pbi | maintenance |
|--------|--------|-----------|----------|------|-------------|-----|-------------|
| eval | OK | OK | OK | OK | OK | OK | OK |
| tac | OK | OK | OK | OK | OK | OK | OK |

### Hook Architecture

| Check | Status | Notes |
|-------|--------|-------|
| Flat structure | PASS/FAIL | {details} |
| Dispatcher present | PASS/FAIL | {details} |
| Syntax valid | PASS/FAIL | {details} |
| Naming conventions | PASS/FAIL | {details} |

### Command Coverage

| Expert | Standard Commands | Coverage |
|--------|------------------|----------|
| {name} | {5/5} | 100% |

### Core Four

| Component | Status |
|-----------|--------|
| CLAUDE.md | PRESENT/MISSING |
| .claude/commands/ | {N} commands |
| .claude/commands/experts/ | {N} experts |
| .claude/settings.json | PRESENT/MISSING |

### TAC Compliance

| Principle | Status | Notes |
|-----------|--------|-------|
| Self-improving experts | PASS/FAIL | {N}/{total} have self-improve |
| Expertise freshness | PASS/WARN | Oldest: {date} |
| No anti-patterns | PASS/WARN | {count} TODOs/FIXMEs |
| Layer coverage | Class {max} | {description} |

### Issues Found

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | {HIGH/MED/LOW} | {description} | {suggested fix} |

### Next Steps

- {recommended actions}
```

## Quick Checks

Quick validation without a full audit:

```
# Expert count
Glob: .claude/commands/experts/*/_index.md

# Hook count
Glob: .claude/hooks/*

# Command count
Glob: .claude/commands/*.md

# Check for stale expertise
Grep: "last_updated" in .claude/commands/experts/*/expertise.md
```

## Troubleshooting

### Expert Missing Files
- Run `/experts:tac:plan_build_improve` to scaffold missing files using existing expert as template

### Hooks Not Flat
- Move nested hooks to top level
- Rename with `{type}-{domain}.sh` convention

### Missing Self-Improve
- Expert knowledge will decay without self-improve capability
- Copy `self-improve.md` template from an existing expert and adapt

### Stale Expertise
- Run `/experts:{domain}:self-improve` for each stale expert
- Update `last_updated` in frontmatter
