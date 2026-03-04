---
model: sonnet
description: Link Excalidraw diagrams to current branch changes or audit the registry
argument-hint: "[link|update-registry|scan] - Match diagrams to code changes"
allowed-tools: Read, Bash(git:*), Bash(wc:*), Bash(ls:*), Glob, Grep
---

# Diagram Linker

## Purpose

Match code changes against `.github/diagram-registry.yml` to identify which Excalidraw architecture diagrams are affected. Three modes: link (default), update-registry, scan.

## Variables

- **MODE**: $1 or "link"
- **REGISTRY**: `.github/diagram-registry.yml`

## Instructions

### Mode: link (default)

1. Run `git diff --name-only main...HEAD` to get all changed files on the current branch
2. Read the diagram registry
3. For each diagram entry, check if any changed file matches any trigger glob
4. Special rule: `system-overview` (trigger `**`) only matches when 10+ files changed
5. Output a markdown table of matched diagrams

### Mode: update-registry

1. Scan all three diagram directories for `.excalidraw` and `.excalidraw.md` files:
   - `docs/architecture/diagrams/excalidraw/obsidian/`
   - `docs/excalidraw-diagrams/`
   - `eagle-plugin/diagrams/excalidraw/`
   - `docs/architecture/` (for `*.excalidraw.md`)
2. Compare found files against registry entries
3. Report unregistered diagrams with suggested YAML entries
4. Report registry entries pointing to missing files

### Mode: scan

Full audit:
1. Verify every `path` in the registry exists on disk
2. Find all `.excalidraw` / `.excalidraw.md` files not in the registry
3. Check for trigger patterns that match no current files
4. Report broken links, untracked diagrams, dead triggers

## Report

```markdown
# Diagram Linker Report

## Mode: {MODE}

### Matched Diagrams
| Diagram | File | Matching Changes |
|---------|------|-----------------|
| {desc} | {path} | {files} |

### Summary
- Changed files: {N}
- Matched diagrams: {N}
- Unmatched diagrams: {N}
```

## Examples

```bash
# Show diagrams affected by current branch
/diagram-linker

# Same as above, explicit
/diagram-linker link

# Find unregistered diagram files
/diagram-linker update-registry

# Full audit — broken links, dead triggers
/diagram-linker scan
```
