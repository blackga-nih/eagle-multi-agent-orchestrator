---
description: "Plan frontend changes, new pages, component updates, or mapping modifications using expertise context"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature description or change to plan]
---

# Frontend Expert - Plan Mode

> Create detailed plans for frontend changes informed by expertise.

## Purpose

Generate a plan for adding pages, modifying components, updating test mappings, or improving the frontend, using:
- Expertise from `.claude/commands/experts/frontend/expertise.md`
- Current component structure and patterns
- Test result mapping requirements
- Validation-first methodology

## Usage

```
/experts:frontend:plan [feature description or change]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/frontend/expertise.md` for:
   - App architecture and routes
   - Component patterns
   - Test result mappings
   - Styling conventions
   - Known issues

2. Read relevant source files for:
   - Current implementations
   - Component interfaces
   - Data structures

3. Understand the TASK:
   - What area of the frontend is affected? (chat, admin, auth, styling)
   - Does it require new pages, components, or mapping changes?
   - What data sources are involved?

### Phase 2: Analyze Current State

1. Search for related components:
   ```
   glob "client/components/**/*.tsx"
   grep "pattern" client/
   ```

2. Check existing pages:
   ```
   glob "client/app/**/page.tsx"
   ```

3. Identify:
   - Files that need to change
   - New files needed
   - Dependencies and imports
   - Mapping updates required

### Phase 3: Generate Plan

Create a plan document:

```markdown
# Frontend Plan: {TASK}

## Overview
- Area: Chat | Admin | Auth | Styling | Mapping
- Pages Affected: {list}
- Components Affected: {list}
- New Files: {list}

## Design

### Changes

| File | Change | Reason |
|------|--------|--------|
| `client/...` | {description} | {why} |

### Component Design (if new component)

```typescript
interface Props {
    // ...
}
```

### Mapping Updates (if test-related)

| Location | Current | New |
|----------|---------|-----|
| TEST_NAMES | ... | Add entry N |
| TEST_DEFS | ... | Add entry N |
| SKILL_TEST_MAP | ... | Add key |
| Readiness panel | ... | Add entry |

## Files Modified

| File | Change Type |
|------|-------------|
| `client/...` | modify |

## Verification

1. `npm run build` -- no TypeScript errors
2. Visual check: {what to verify}
3. Mapping check: {consistency verification}
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/frontend-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Always read expertise.md first** - Contains architecture and patterns
2. **Follow existing patterns** - Use AuthGuard, TopNav, Tailwind classes consistently
3. **Include mapping updates** - If adding tests, list all 3 frontend registration points
4. **Check both frontends** - HTML dashboard + Next.js may both need updates
5. **Keep components small** - Follow existing component decomposition patterns
6. **Include TypeScript types** - All new interfaces and props

---

## Output Location

Plans are saved to: `.claude/specs/frontend-{feature}.md`
