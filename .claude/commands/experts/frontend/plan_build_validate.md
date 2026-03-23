---
description: "Plan, build, and browser-validate frontend changes with agent-browser screenshots"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
argument-hint: [feature description or change to implement]
---

# Frontend Expert - Plan Build Validate (with Browser Testing)

> Full workflow: Plan changes, build them, then validate visually with agent-browser.

## Purpose

Like `plan_build_improve` but replaces static validation (tsc + build) with **live browser validation** using `agent-browser`. After building, navigate to the affected pages, interact with components, take screenshots, and verify the UI renders correctly.

## Usage

```
/experts:frontend:plan_build_validate [feature description or change]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`, `Agent`

---

## Workflow

### Step 1: PLAN

1. Read `.claude/commands/experts/frontend/expertise.md` for patterns and architecture.
2. Analyze the TASK — search codebase for relevant components, identify affected files.
3. Create a brief plan (no spec file needed for small changes).

---

### Step 2: BUILD

1. Implement changes following existing patterns.
2. Run TypeScript check:
   ```bash
   cd client && npx tsc --noEmit 2>&1 | tail -20
   ```
3. Fix any type errors before proceeding.

---

### Step 3: VALIDATE (Browser)

This is the key differentiator. Use `agent-browser` to verify the UI visually.

#### 3a. Start the dev server (if not running)

```bash
# Check if dev server is already running
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 || (cd client && npm run dev &)
```

#### 3b. Navigate to affected page(s)

```bash
agent-browser open http://localhost:3000/{affected-route}
agent-browser wait --load networkidle
```

#### 3c. Snapshot and verify structure

```bash
# Get interactive elements
agent-browser snapshot -i

# Verify expected elements exist
agent-browser get text @{ref}           # Check text content
agent-browser is visible @{ref}         # Check visibility
agent-browser get count ".{selector}"   # Count elements
```

#### 3d. Interact with components

```bash
# Test user interactions
agent-browser click @{ref}              # Click buttons/links
agent-browser fill @{ref} "test input"  # Fill form fields
agent-browser press Enter               # Submit forms
agent-browser wait --load networkidle   # Wait for response
```

#### 3e. Take screenshots

```bash
# Screenshot the result
agent-browser screenshot screenshots/validate-{feature}-{step}.png

# Full-page screenshot if needed
agent-browser screenshot screenshots/validate-{feature}-full.png --full
```

#### 3f. Verify specific conditions

```bash
# Check for error states
agent-browser get count ".text-red-500"    # No error messages
agent-browser get count "[role='alert']"   # No alert banners

# Check rendered content
agent-browser get text ".{content-selector}"
agent-browser eval "document.querySelectorAll('.{class}').length"
```

---

### Step 4: REVIEW

1. Review screenshots — does the UI look correct?
2. Check for:
   - Layout issues (overflow, alignment, spacing)
   - Missing or broken content
   - Interaction feedback (hover states, click responses)
   - Responsive concerns
3. If issues found: fix and re-run Step 3

---

### Step 5: IMPROVE

1. Update `.claude/commands/experts/frontend/expertise.md`:
   - Add patterns that worked
   - Note any browser testing gotchas
   - Document component behavior observed

---

## Validation Templates

### Chat page validation
```bash
agent-browser open http://localhost:3000/chat
agent-browser wait --load networkidle
agent-browser snapshot -i
# Verify chat input, sidebar, quick actions visible
agent-browser fill @{input-ref} "Test message"
agent-browser click @{send-ref}
agent-browser wait 5000
agent-browser snapshot -i
# Verify response appeared
agent-browser screenshot screenshots/validate-chat.png
```

### Admin page validation
```bash
agent-browser open http://localhost:3000/admin
agent-browser wait --load networkidle
agent-browser snapshot -i
# Verify stat cards, quick actions, system health
agent-browser screenshot screenshots/validate-admin.png
```

### Component-level validation
```bash
agent-browser open http://localhost:3000/{page-with-component}
agent-browser wait --load networkidle
agent-browser snapshot -s ".{component-selector}" -i
# Verify component renders with expected children
agent-browser screenshot screenshots/validate-component.png
```

### Tool display validation (chat)
```bash
agent-browser open http://localhost:3000/chat
agent-browser wait --load networkidle
agent-browser snapshot -i
agent-browser fill @{input-ref} "Search FAR Part 6 competition requirements"
agent-browser click @{send-ref}
agent-browser wait 15000
agent-browser snapshot -i
# Verify tool cards appear in chat
agent-browser get count "[data-tool-card]"
# Verify tool results render (not raw JSON)
agent-browser screenshot screenshots/validate-tool-display.png
```

---

## Report Format

```markdown
## Frontend Plan-Build-Validate: {TASK}

### Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Plan | DONE | {affected files} |
| Build | DONE | tsc clean |
| Validate | PASS | Browser verified |
| Review | PASS | Screenshots look correct |
| Improve | DONE | Expertise updated |

### Browser Validation Results

| Page/Component | Status | Screenshot |
|----------------|--------|------------|
| {route} | PASS | screenshots/validate-{name}.png |

### Files Changed

| File | Change |
|------|--------|
| `client/...` | {description} |
```

---

## Instructions

1. **Always run tsc before browser testing** — catch type errors early
2. **Take screenshots at each validation step** — visual evidence of correctness
3. **Re-snapshot after interactions** — DOM may change after clicks/navigation
4. **Use `wait --load networkidle`** after navigation — ensure page fully loaded
5. **Close browser when done** — `agent-browser close`
