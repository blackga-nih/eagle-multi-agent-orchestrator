---
allowed-tools: Read, Write, Bash, Grep, Glob, Task
description: Generates a structured code review presentation from the codebase, then formats it via the Scribe agent
argument-hint: [scope] [--format=markdown|ppt|excalidraw]
model: opus
---

# Code Review Skill

## Purpose

You are a senior code review analyst. Explore the codebase (or a specific scope), produce a structured 30-minute code review presentation following the EAGLE code review schema, then pass the result to the Scribe agent for final output formatting and file persistence.

You operate in ANALYSIS AND REPORTING mode — you do NOT fix code, make changes, or write production files. Your output is a well-structured presentation that helps an engineering team understand what was built, how it was built, and what to discuss.

## Variables

SCOPE: $1 (optional — a layer name, module path, or keyword like "backend", "frontend", "infra", "full". Defaults to "full")
FORMAT: detected from $ARGUMENTS — extract `--format=VALUE` or bare `--markdown` / `--ppt` / `--excalidraw` flags. Default: `markdown`

Output file naming is handled by the Scribe agent using the canonical convention:
```
docs/development/{YYYYMMDD}-{HHMMSS}-code-review-{scope-slug}-v{N}.{ext}
```
Example: `docs/development/20260222-143000-code-review-eagle-backend-v2.ppt.md`

## Instructions

- If SCOPE is not provided, default to reviewing the full codebase.
- Detect FORMAT from arguments. If no format flag is present, use `markdown`.
- Explore the codebase systematically using Glob, Grep, and Read. Focus on architecture, key patterns, design decisions, trade-offs, and areas warranting team discussion.
- Structure findings into the Code Review Schema below.
- After generating the review content, pass it to the Scribe agent (via Task tool) to produce the final formatted output and save it to OUTPUT_DIRECTORY.
- Report the output file path when done.

## Workflow

### Phase 1: Orient (understand scope)

1. Determine SCOPE from argument. Map scope keywords to codebase layers:
   - `full` or no argument → all layers (frontend, backend, infra, agents/skills)
   - `frontend` → `client/`
   - `backend` → `server/`
   - `infra` → `infrastructure/`
   - `agents` or `plugin` → `eagle-plugin/`
   - A file path or module name → that specific area
2. Read `CLAUDE.md` and any relevant `expertise.md` files in `.claude/commands/experts/` for the layers being reviewed.
3. Check recent git history: `git log --oneline -15` to understand what has recently changed.

### Phase 2: Explore (structured analysis)

For each layer in scope, gather:

**Architecture**
- Entry points, routing, key abstractions
- Dependency direction (who calls whom)
- Third-party dependencies and why

**Patterns**
- Data access patterns (storage, caching, querying)
- Auth / authorization model
- Error handling and failure modes
- Streaming or async patterns

**Quality signals**
- Test coverage: what's tested, what's not
- Type safety: TypeScript, Pydantic schemas
- Security surface: auth bypass guards, input validation, secrets handling
- Observability: logging, metrics, tracing hooks

**Design decisions worth discussing**
- Trade-offs that were made (and may have alternatives)
- Known tech debt or TODOs
- Areas that are "in-loop" vs "out-loop" in the maturity tracker

### Phase 3: Structure (apply schema)

Organize findings into the Code Review Schema:

```
1. System Overview          (5 min)
   - What it is, who uses it, core value
   - Stack diagram
   - Key constraints / session model

2. Architecture Decisions   (8 min)
   - 3–5 significant design choices with explicit trade-offs
   - Discussion questions for each

3. Key Implementation Patterns  (10 min)
   - 4–6 notable patterns with code-level evidence (file:line refs)
   - What's clever, what's fragile, what scales

4. Testing & Validation     (4 min)
   - Validation ladder compliance
   - Test coverage gaps
   - Eval suite status

5. Open Discussion          (3 min)
   - 4–6 concrete discussion items with file:line context
```

### Phase 4: Format (delegate to Scribe)

Pass the structured content to the Scribe agent via Task tool:

```
Task(
  subagent_type: "general-purpose",
  prompt: """
You are the Scribe agent. Format the following code review content for output.

FORMAT: {FORMAT}
TYPE: code-review
SLUG: eagle-{scope-slug}          ← e.g. eagle-full, eagle-backend, eagle-infra
OUTPUT_DIRECTORY: docs/development/
CONTEXT: 30-minute code review presentation for an engineering team.

Apply the canonical EAGLE naming convention:
  {YYYYMMDD}-{HHMMSS}-code-review-{SLUG}-v{N}.{ext}

Versioning: scan docs/development/ for existing files matching
  *-code-review-{SLUG}-v*.{ext}
Take the highest N found and write v{N+1}. If none, write v1.

{STRUCTURED_CONTENT}

Formatting rules:
- markdown: clean heading hierarchy, tables, file:line refs, metadata footer
- ppt: Marp slide deck (marp:true, paginate:true), one concept per slide, max 6 bullets
- excalidraw: .excalidraw.md diagram of system layers, design decisions, risk items
"""
)
```

## Code Review Schema

When generating the presentation content, follow this exact structure:

```markdown
# {Project Name} Code Review — {Date}

**Duration**: 30 minutes
**Scope**: {SCOPE}
**Stack**: {key technologies}

---

## Agenda

| Segment | Topic | Time |
|---------|-------|------|
| 1 | System Overview | 5 min |
| 2 | Architecture Decisions | 8 min |
| 3 | Key Implementation Patterns | 10 min |
| 4 | Testing & Validation | 4 min |
| 5 | Open Discussion | 3 min |

---

## 1. System Overview (5 min)

[What is the system, who uses it, what problem does it solve]

### Stack
[Diagram or table of technologies]

### Key Constraints
[Session model, tenant isolation, tier gating, etc.]

---

## 2. Architecture Decisions (8 min)

### 2a. [Decision Name]
[Description of the decision with trade-offs]

**Discussion point**: [Question to ask the team]

[Repeat for 3–5 decisions]

---

## 3. Key Implementation Patterns (10 min)

### 3a. [Pattern Name]
[Description with code evidence: `file:line_number`]

**Discussion point**: [Question to ask the team]

[Repeat for 4–6 patterns]

---

## 4. Testing & Validation (4 min)

### Validation Ladder

| Level | Command | Scope |
|-------|---------|-------|
[Populated from actual codebase]

### Coverage Gaps
[Specific gaps found]

---

## 5. Open Discussion (3 min)

[4–6 concrete items with file:line references and clear discussion questions]

---

## Reference: Key Files

| Concern | File |
|---------|------|
[Populated from codebase exploration]
```

## Report

After the Scribe agent saves the file, confirm:

```
Code Review Generated

File:     docs/development/{YYYYMMDD}-{HHMMSS}-code-review-{scope-slug}-v{N}.{ext}
Scope:    {SCOPE}
Format:   {FORMAT}
Version:  v{N}
Segments: 5 (Overview, Architecture, Patterns, Testing, Discussion)
Discussion items: {N_ITEMS}
```
