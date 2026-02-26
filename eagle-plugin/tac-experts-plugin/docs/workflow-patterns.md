# Workflow (Agent Team Workflow) Patterns

> Workflows are standardized workflows that combine TAC tactics into repeatable processes.

---

## The 7 Canonical Workflows

| Workflow | Description | Key Tactics | When to Use |
|-----|-------------|-------------|-------------|
| Plan-Build-Validate | Design, implement, test in sequence | 4, 5, 8 | New features, standard development |
| ACT-LEARN-REUSE | Do work, capture learnings, apply patterns | 5, 3, 8 | Every task (default cycle) |
| Expert Bootstrap | Create a new expert from scratch | 3, 6, 2 | New domain needs accumulated knowledge |
| Hook-Driven Development | Build features triggered by hooks | 4, 7, 5 | Automated responses to events |
| Spec-to-Implementation | Write spec, agent builds it | 1, 4, 5 | Complex features needing up-front design |
| Test-First Agentic | Define test, agent implements until green | 5, 1, 4 | Bug fixes, behavior-driven work |
| Context Refresh | Update CLAUDE.md and expertise files | 9, 2, 14 | After significant codebase changes |

---

## Plan-Build-Validate

The workhorse Workflow for standard development.

```
PLAN      →  Write spec to .claude/specs/
BUILD     →  Agent implements the spec
VALIDATE  →  Run validation ladder
```

**Tactic 4** (Stay Out): Agent completes without interruption.
**Tactic 5** (Feedback): Validation built into every step.
**Tactic 8** (Prioritize): Agent does the work, not human.

### Implementation

```bash
/experts:{domain}:plan "Add new endpoint"       # PLAN
/build .claude/specs/backend-new-endpoint.md     # BUILD + VALIDATE
```

---

## ACT-LEARN-REUSE

The core TAC improvement cycle. Should be the default operating mode.

```
ACT    →  Execute the task (build, test, deploy)
LEARN  →  Capture what worked and what didn't (update expertise.md)
REUSE  →  Apply patterns to future tasks (template, reference)
```

**Tactic 5** (Feedback): Learning from outcomes.
**Tactic 3** (Template): Reusing proven patterns.
**Tactic 8** (Prioritize): Investing in agent capability.

### Implementation

```bash
/experts:{domain}:plan_build_improve "Feature X"   # ACT + LEARN + REUSE in one command
# Or manually:
/experts:{domain}:plan "Feature X"                  # ACT
# ... build ...
/experts:{domain}:self-improve component success    # LEARN
# Future tasks reference expertise.md              # REUSE
```

---

## Expert Bootstrap

Create a new domain expert from scratch.

```
IDENTIFY  →  Recognize a domain needing accumulated knowledge
SCAFFOLD  →  Create the 7 standard expert files from templates
POPULATE  →  Fill expertise.md with initial domain knowledge
VALIDATE  →  Run maintenance to check structure
```

**Tactic 3** (Template): Expert templates encode the pattern.
**Tactic 6** (One:One): Each expert owns one domain.
**Tactic 2** (Adopt): Design for agent consumption.

### Implementation

1. Copy templates from `tac-experts-plugin/templates/expert/`
2. Replace `{{DOMAIN}}` placeholders with your domain name
3. Fill `expertise.md` with initial domain knowledge
4. Run `/experts:tac:maintenance --experts` to validate

---

## Hook-Driven Development

Build features triggered by Claude Code hooks.

```
IDENTIFY  →  What event should trigger the action?
IMPLEMENT →  Write the hook script
CONFIGURE →  Add to settings.json with proper matchers
VALIDATE  →  Test the hook fires correctly
```

**Tactic 4** (Stay Out): Hooks run automatically.
**Tactic 7** (Zero-Touch): No manual intervention needed.
**Tactic 5** (Feedback): Hook validates its own execution.

---

## Spec-to-Implementation

Write a detailed spec, then let the agent build it.

```
SPEC      →  Write detailed plan to .claude/specs/
REVIEW    →  Human reviews the spec (one interruption)
BUILD     →  Agent implements from spec without interruption
VALIDATE  →  Agent runs validation commands from spec
```

**Tactic 1** (Stop): Human writes spec, not code.
**Tactic 4** (Stay Out): Agent builds autonomously from spec.
**Tactic 5** (Feedback): Spec includes validation commands.

### Implementation

```bash
/plan "Complex feature requiring up-front design"   # SPEC
# Review the spec in .claude/specs/
/build .claude/specs/complex-feature.md              # BUILD + VALIDATE
```

---

## Test-First Agentic

Define the expected behavior via tests, then let the agent implement until tests pass.

```
TEST      →  Write or define the test case
IMPLEMENT →  Agent writes code to make test pass
ITERATE   →  If test fails, agent fixes and re-runs
DONE      →  All tests green
```

**Tactic 5** (Feedback): Test IS the feedback loop.
**Tactic 1** (Stop): Human defines the test, agent writes the code.
**Tactic 4** (Stay Out): Agent iterates until green.

---

## Context Refresh

Update CLAUDE.md and expertise files to reflect current codebase state.

```
AUDIT     →  Run maintenance across all experts
UPDATE    →  Refresh stale expertise files
VALIDATE  →  Verify all experts are current
```

**Tactic 9** (Context): Keep context accurate.
**Tactic 2** (Adopt): Ensure agent has correct information.
**Tactic 14** (Singularity): Move toward self-describing codebase.

### Implementation

```bash
/experts:tac:maintenance --all                     # AUDIT
/experts:{domain}:self-improve                     # UPDATE (per domain)
/experts:tac:maintenance --freshness               # VALIDATE
```

---

## Agent Catalog

| Agent Type | Role | Example |
|-----------|------|---------|
| Supervisor | Orchestrates specialists | Supervisor with intake/legal/market/tech |
| Domain Specialist | Deep expertise in one area | Legal counsel, tech review |
| Tool Agent | Executes specific tool operations | S3 ops, DynamoDB CRUD |
| Eval Agent | Runs and validates test suites | Eval expert running test suite |
| Builder Agent | Implements features from specs | Plan-build-improve workflow agent |
| Reviewer Agent | Reviews code and provides feedback | PR review, compliance check |

## Command Catalog

| Command | Type | Purpose |
|---------|------|---------|
| `question` | Read-only | Answer questions from expertise |
| `plan` | Planning | Design implementations |
| `self-improve` | Learning | Update expertise with findings |
| `plan_build_improve` | Full workflow | ACT-LEARN-REUSE end-to-end |
| `maintenance` | Validation | Check health and compliance |
| `add-{thing}` | Scaffold | Create new instances from templates |

## Scale Reference

| Component | Typical Count | Notes |
|-----------|--------------|-------|
| Experts | 3-10 per project | One per major domain |
| Commands per Expert | 5-7 | Standard set + domain-specific |
| Hooks | 5-15 | Flat structure, one file per hook |
| Skills/Prompts | 5-20 | One per agent role |
| Workflow Patterns | 5-10 | Reusable across experts |
