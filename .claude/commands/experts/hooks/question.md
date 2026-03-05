---
type: expert-file
parent: "[[hooks/_index]]"
file-type: command
command-name: "question"
human_reviewed: false
tags: [expert-file, command, read-only, hooks]
---

# Hooks Expert - Question Mode

> Read-only command to query Claude Code hooks patterns without making changes.

## Purpose
Answer questions about Claude Code hook events, patterns, configuration, and observability **without making any code changes**.

## Usage
```
/experts:hooks:question [question]
```

## Allowed Tools
`Read`, `Glob`, `Grep`, `Task`

---

## Workflow

1. **Receive question** from user
2. **Read expertise.md** for hooks mental model
3. **Search codebase** for existing hook implementations if relevant
4. **Answer** with pattern reference, code example, and source

---

## Question Categories

### Category 1: Event Questions
"Which hook fires when...?", "What data does PreToolUse receive?"

**Resolution**: Reference Part 1 (12 Hook Events) in expertise.md

### Category 2: Pattern Questions
"How do I block a tool call?", "How does the dispatcher work?"

**Resolution**: Reference Part 2 (7 Hook Patterns) with code examples

### Category 3: Configuration Questions
"How do I set up matchers?", "Global vs project hooks?"

**Resolution**: Reference Part 3 (Hook Architecture) for settings.json patterns

### Category 4: Agent Integration Questions
"How do agent-specific hooks work?", "Builder/Validator pattern?"

**Resolution**: Reference Part 4 (Agent Integration)

### Category 5: Observability Questions
"How do I track tool usage?", "What metrics should I capture?"

**Resolution**: Reference Part 5 (Observability Pipeline)

### Category 6: Implementation Questions
"How do I get started?", "What's the minimum setup?"

**Resolution**: Reference Part 6 (Implementation Recipes)

---

## Report Format

```markdown
## Answer

{Direct answer with code example if applicable}

## Hook Pattern

**Pattern**: {Pattern name from Part 2}
**Event**: {Which of the 12 events}
**Key Code**:
```python
# Relevant code snippet
```

## Source Reference

- Expertise: `Part {N}: {Section Name}`
- Reference Implementation: `{repo name}`
```
