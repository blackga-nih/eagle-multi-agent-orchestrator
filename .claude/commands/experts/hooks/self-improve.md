---
type: expert-file
parent: "[[hooks/_index]]"
file-type: command
command-name: "self-improve"
human_reviewed: false
tags: [expert-file, command, self-improve, hooks]
---

# Hooks Expert - Self-Improve Mode

> Validate and update hooks expertise by scanning actual hook implementations in this codebase.

## Purpose
Scan the current project's hook implementations, compare against the expertise mental model, and update the expertise file with any new patterns, configurations, or lessons learned.

## Usage
```
/experts:hooks:self-improve
```

## Allowed Tools
`Read`, `Glob`, `Grep`, `Edit`

---

## Workflow

### Step 1: Scan Current Hooks

```
Glob: .claude/hooks/**/*.py
Glob: .claude/settings.json
Glob: ~/.claude/settings.json (global)
Glob: .claude/hooks/**/*.sh
```

### Step 2: Catalog Findings

For each hook found:
- Which event does it handle?
- Which pattern does it implement?
- Any new patterns not in expertise.md?
- Any deviations from best practices?

### Step 3: Compare Against Expertise

| Check | Action |
|-------|--------|
| New pattern found | Add to Part 2 |
| New event usage | Update Part 1 examples |
| Configuration change | Update Part 3 |
| New recipe | Add to Part 6 |
| Best practice violation | Flag for review |

### Step 4: Update Expertise

Edit `expertise.md` with:
- New patterns discovered
- Updated reference implementations
- Corrected configuration examples
- New best practices from real usage

### Step 5: Report

```markdown
## Self-Improve Report

### Hooks Scanned
- {N} hook scripts found
- {N} events configured in settings.json

### Expertise Updates
- Added: {new patterns or recipes}
- Updated: {corrected information}
- Flagged: {issues needing human review}

### Coverage
| Event | Implemented | In Expertise |
|-------|------------|--------------|
| PreToolUse | Yes/No | Yes/No |
| PostToolUse | Yes/No | Yes/No |
| ... | ... | ... |
```
