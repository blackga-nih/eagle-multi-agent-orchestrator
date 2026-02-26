---
description: "Query {{DOMAIN}} concepts, patterns, or architecture without making changes"
allowed-tools: Read, Glob, Grep
---

# {{DOMAIN_TITLE}} Expert - Question Mode

> Read-only command to query {{DOMAIN}} knowledge without making any changes.

## Purpose

Answer questions about {{DOMAIN}} — patterns, architecture, conventions, troubleshooting — **without making any code changes**.

## Usage

```
/experts:{{DOMAIN}}:question [question]
```

## Allowed Tools

`Read`, `Glob`, `Grep` (read-only only)

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/{{DOMAIN}}/expertise.md`
2. Identify which Part(s) are relevant to the question

### Phase 2: Research (if needed)

1. Scan relevant source files:
   ```
   Glob: {{SOURCE_GLOB_PATTERN}}
   ```
2. Check for specific patterns:
   ```
   Grep: {{RELEVANT_PATTERN}}
   ```

### Phase 3: Answer

1. Provide a direct answer referencing expertise.md sections
2. Include source file references when applicable

---

## Report Format

```markdown
## Answer

{Direct answer to the question}

## Details

{Supporting information from expertise.md and source files}

## Source Reference

- expertise.md -> Part {N}: {section name}
- {source file references if applicable}
```

---

## Instructions

1. **Read expertise.md first** — all domain knowledge is stored there
2. **Never modify files** — this is a read-only command
3. **Be specific** — reference exact sections and file paths
4. **Connect to practice** — relate concepts to the actual codebase
5. **Suggest next steps** — if appropriate, recommend which command to run next
