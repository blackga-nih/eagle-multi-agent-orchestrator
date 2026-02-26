---
description: "Plan implementations using TAC principles — tactics, frameworks, and agentic patterns"
allowed-tools: Read, Write, Glob, Grep, Bash
argument-hint: [feature or implementation to plan]
---

# TAC Expert - Plan Mode

> Create TAC-informed plans for features, experts, hooks, or any implementation work.

## Purpose

Generate a plan for building features, creating new experts, designing hooks, or restructuring workflows, using:
- TAC tactics and frameworks from `expertise.md`
- Current project structure and patterns
- Agentic layer classification
- Validation-first methodology

## Usage

```
/experts:tac:plan [feature or implementation description]
```

## Variables

- `TASK`: $ARGUMENTS

## Allowed Tools

`Read`, `Write`, `Glob`, `Grep`, `Bash`

---

## Workflow

### Phase 1: Load Context

1. Read `.claude/commands/experts/tac/tac-learning-expertise.md` for:
   - Applicable tactics (Part 1)
   - Framework selection (Part 4: PITER, R&D, ACT-LEARN-REUSE)
   - Maturity level target (Part 5)

2. Read `.claude/commands/experts/tac/expertise.md` for:
   - Relevant patterns from the pattern index (Part 4)
   - Hook architecture if applicable (Part 1)
   - Agent team workflow patterns (Part 5)
   - SSVA patterns if applicable (Part 2)

2. Scan project structure:
   ```
   Glob: .claude/commands/experts/*/_index.md
   Glob: .claude/commands/*.md
   Glob: .claude/hooks/*
   ```

3. Understand the TASK:
   - What is being built?
   - Which agentic layer does it belong to? (Class 1, 2, or 3)
   - Which TAC tactics apply?
   - Which framework fits? (PITER for features, R&D for exploration, ACT-LEARN-REUSE for iterative)

### Phase 2: Analyze TAC Alignment

1. Map TASK to tactics:
   - Does this follow Stop Coding? (Agent does the work, not human)
   - Is it Stay Out of the Loop? (Agent can complete without interruption)
   - Does it include Feedback Loops? (Validation built in)
   - Is it Template Engineering? (Reusable patterns)

2. Identify the workflow pattern:
   - Plan-Build-Validate?
   - Expert Bootstrap?
   - Hook-Driven Development?
   - Spec-to-Implementation?

3. Check for anti-patterns:
   - Kitchen-sink prompts (violates Tactic 6)
   - Manual steps (violates Tactic 4)
   - Missing validation (violates Tactic 5)
   - Missing self-improve (violates ACT-LEARN-REUSE)

### Phase 3: Generate Plan

Create a TAC-informed plan:

```markdown
# TAC Plan: {TASK}

## TAC Analysis

| Dimension | Assessment |
|-----------|------------|
| Agentic Layer | Class {1/2/3}: {layer name} |
| Primary Framework | {PITER / R&D / ACT-LEARN-REUSE} |
| Workflow Pattern | {pattern name} |
| Key Tactics | {list of applicable tactics} |
| Anti-patterns to avoid | {list} |

## Implementation Plan

### Step 1: {action}
- TAC tactic: {N} - {name}
- Details: {what to do}
- Validation: {how to verify}

### Step 2: {action}
...

## Files to Create/Modify

| File | Action | Layer |
|------|--------|-------|
| {path} | Create/Edit | Class {N} |

## Validation Strategy

- [ ] {check 1} (Tactic 5: Feedback Loops)
- [ ] {check 2}
- [ ] {check 3}

## TAC Compliance Checklist

- [ ] Agent does the work, not human (Tactic 1)
- [ ] Agent can complete without interruption (Tactic 4)
- [ ] Validation built into workflow (Tactic 5)
- [ ] Single-purpose prompts where applicable (Tactic 6)
- [ ] Automated end-to-end where possible (Tactic 7)
- [ ] Self-improve step included (ACT-LEARN-REUSE)
```

### Phase 4: Save Plan

1. Write plan to `.claude/specs/tac-{feature}.md`
2. Report plan summary to user

---

## Instructions

1. **Read both expertise files** - Theory in `tac-learning-expertise.md`, patterns in `expertise.md`
2. **Map to tactics** - Every plan step should reference the TAC tactic it follows
3. **Include validation** - Every plan must have built-in feedback loops
4. **Classify the layer** - Identify if work is Class 1, 2, or 3
5. **Check anti-patterns** - Explicitly call out what to avoid
6. **Include self-improve** - Plans should end with a learning step

---

## Output Location

Plans are saved to: `.claude/specs/tac-{feature}.md`
