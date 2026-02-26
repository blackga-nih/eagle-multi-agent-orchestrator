# TAC Maturity Model

> Three levels of agentic development maturity, from human-in-the-loop to fully autonomous.

---

## The Three Levels

```
In-Loop        →  Human directs every step
Out-Loop       →  Agent completes autonomously, human reviews
Zero-Touch     →  Fully automated from trigger to deploy
```

---

## In-Loop

**Human directs every step.** The agent assists but requires guidance.

- Human tells the agent what to do at each step
- Agent may ask clarifying questions
- Human reviews each output before proceeding
- Good for: Learning a new domain, critical changes, unfamiliar patterns

**Example**: "Read this file. Now edit line 42. Now run the tests."

---

## Out-Loop

**Agent completes autonomously. Human reviews the final result.**

- Agent receives a task and completes it end-to-end
- Built-in validation catches errors automatically
- Human reviews the final diff/output
- Good for: Standard features, bug fixes, routine tasks

**Example**: `/experts:backend:plan_build_improve "Add health check endpoint"` — agent plans, builds, validates, and self-improves without interruption.

---

## Zero-Touch

**Fully automated from trigger to deployment. No human in the loop.**

- Triggered by events (CI/CD, hooks, schedules)
- Agent completes the task and deploys
- Human is notified of results but doesn't intervene
- Good for: Bug fixes with clear test cases, formatting, dependency updates

**Example**: A hook detects a failing test → agent fixes it → runs full validation → commits → deploys.

---

## Graduation Path

```
In-Loop (3+ successes)
    │
    ▼
Template as command
    │
    ▼
Add validation (feedback loops)
    │
    ▼
Out-Loop workflow
    │
    ▼
Zero-Touch
```

### Step by Step

1. **Do the task In-Loop 3+ times** — understand the pattern, catch edge cases
2. **Template it as a command** — encode the workflow in `.claude/commands/`
3. **Add validation** — build feedback loops that make it self-correcting (Tactic 5)
4. **Promote to Out-Loop** — use `plan_build_improve` for end-to-end execution
5. **Add triggers** — hooks, CI/CD events that auto-invoke the workflow
6. **Graduate to Zero-Touch** — fully automated, human notified of results

---

## Maturity Tracker Template

Track your workflow maturity across domains:

```markdown
| Workflow | Current Level | Target | Notes |
|----------|---------------|--------|-------|
| Frontend features | In-Loop | Out-Loop | Need 2 more successes |
| Backend endpoints | Out-Loop | Out-Loop | Stable |
| CDK changes | In-Loop | Out-Loop | Complex, need more templates |
| Agent skill additions | In-Loop | Out-Loop | |
| Bug fixes | Out-Loop | Zero-Touch | Add hook triggers |
| Eval runs | Out-Loop | Zero-Touch | Add scheduled trigger |
| Code review | In-Loop | Out-Loop | Review agent working well |
| Documentation | Out-Loop | Zero-Touch | Self-improve handles this |
```

---

## Anti-Patterns by Level

### In-Loop Anti-Patterns
- Staying In-Loop for tasks you've done 5+ times
- Not capturing patterns as you go (violates ACT-LEARN-REUSE)
- Micro-managing the agent (defeats the purpose)

### Out-Loop Anti-Patterns
- Missing validation steps (agent can complete but may produce wrong output)
- No self-improve step (knowledge doesn't accumulate)
- Overly broad task scope (agent loses focus)

### Zero-Touch Anti-Patterns
- Automating tasks you don't understand well yet
- No alerting/notification on failure
- No human review for critical changes

---

## Measuring Maturity

| Metric | In-Loop | Out-Loop | Zero-Touch |
|--------|---------|----------|------------|
| Human interactions per task | 5+ | 1-2 | 0 |
| Time to completion | Manual pace | Minutes | Automated |
| Error rate | Human-dependent | Self-correcting | Self-correcting + auto-fix |
| Knowledge capture | Ad hoc | Structured (expertise.md) | Continuous |
| Trigger method | Human command | Human command | Event/schedule |
