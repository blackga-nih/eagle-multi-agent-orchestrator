# Publishing the TAC Experts Plugin

How to publish `tac-experts-plugin` as an official Claude Code plugin, host it on a marketplace, and distribute it privately or publicly.

---

## Table of Contents

1. [Plugin Format](#plugin-format)
2. [Directory Layout](#directory-layout)
3. [Creating the Marketplace](#creating-the-marketplace)
4. [Publishing to GitHub](#publishing-to-github)
5. [Installing (User Side)](#installing-user-side)
6. [Private Distribution](#private-distribution)
7. [Team Auto-Install](#team-auto-install)
8. [Justfile Recipes](#justfile-recipes)
9. [Updating & Versioning](#updating--versioning)

---

## Plugin Format

Claude Code plugins require a specific structure. The key difference from our current layout:

| Current (TAC) | Official Plugin Format |
|----------------|----------------------|
| `plugin.json` at root | `.claude-plugin/plugin.json` at root |
| `commands/experts/tac/` | Same — works as-is |
| `examples/` | Same — works as-is |
| Hooks in settings.json | `hooks/hooks.json` at root |
| N/A | Skills in `skills/SKILL_NAME/SKILL.md` |

**Key rule**: Only `plugin.json` goes inside `.claude-plugin/`. Everything else stays at the plugin root.

---

## Directory Layout

The official Claude Code plugin structure:

```
tac-experts-plugin/
├── .claude-plugin/
│   ├── plugin.json              ← Plugin manifest (required)
│   └── marketplace.json         ← Marketplace catalog (if self-hosting)
├── commands/                    ← Slash commands (become /tac-experts:command-name)
│   └── experts/tac/
│       ├── question.md
│       ├── plan.md
│       ├── plan_build_improve.md
│       ├── self-improve.md
│       └── maintenance.md
├── agents/                      ← Agent definitions
│   └── (moved from examples/agents/ if distributing)
├── skills/                      ← Agent Skills (model-invoked)
│   └── tac-question/
│       └── SKILL.md
├── hooks/
│   └── hooks.json               ← Hook configurations
├── templates/                   ← Templates (referenced by commands)
├── docs/                        ← Reference documentation
├── examples/                    ← Code examples (hooks, SDK, experts)
├── apps/                        ← App catalog
├── scripts/                     ← Tooling scripts
├── data/                        ← Schemas, tags, cross-refs
└── README.md
```

### What changes from current layout

1. **Move** `plugin.json` → `.claude-plugin/plugin.json` (different schema)
2. **Create** `hooks/hooks.json` for hook configurations
3. **Create** `skills/` directory for model-invoked Skills
4. **Use** `${CLAUDE_PLUGIN_ROOT}` in hook commands (resolved at install time)

### `.claude-plugin/plugin.json` (official format)

```json
{
  "name": "tac-experts",
  "description": "Tactical Agentic Coding — expert system, frameworks, and patterns for agent-first development",
  "version": "1.1.0",
  "author": {
    "name": "Greg Black"
  },
  "homepage": "https://github.com/gblack686-openclaw/tac-experts-plugin",
  "repository": "https://github.com/gblack686-openclaw/tac-experts-plugin",
  "license": "MIT",
  "keywords": ["tac", "agentic", "expert-system", "claude-code", "methodology"]
}
```

### `hooks/hooks.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "uv run ${CLAUDE_PLUGIN_ROOT}/examples/hooks/pretooluse_guard.py"
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [{
          "type": "command",
          "command": "uv run ${CLAUDE_PLUGIN_ROOT}/examples/hooks/posttooluse_validator.py"
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/examples/hooks/stop_dispatcher.sh"
        }]
      }
    ]
  }
}
```

**Important**: Use `${CLAUDE_PLUGIN_ROOT}` instead of relative paths. Plugins are copied to `~/.claude/plugins/cache/` at install time, so relative paths to the original location won't work.

---

## Creating the Marketplace

A marketplace is a catalog that lists plugins and where to fetch them.

### `.claude-plugin/marketplace.json`

```json
{
  "name": "tac-marketplace",
  "owner": {
    "name": "Greg Black",
    "email": "your-email@example.com"
  },
  "metadata": {
    "description": "TAC (Tactical Agentic Coding) plugins for Claude Code",
    "version": "1.0.0"
  },
  "plugins": [
    {
      "name": "tac-experts",
      "source": "./",
      "description": "TAC methodology expert system with 8 tactics, frameworks, hooks, and 27 lessons",
      "version": "1.1.0",
      "category": "methodology",
      "tags": ["tac", "agentic", "expert-system", "hooks", "ssva"],
      "keywords": ["tac", "claude-code", "agentic-coding"]
    }
  ]
}
```

### Marketplace with multiple plugins (OpenClaw org)

If publishing the TAC collection as multiple plugins:

```json
{
  "name": "openclaw-tac",
  "owner": {
    "name": "OpenClaw",
    "email": "your-email@example.com"
  },
  "plugins": [
    {
      "name": "tac-experts",
      "source": {
        "source": "github",
        "repo": "gblack686-openclaw/tac-experts-plugin"
      },
      "description": "TAC methodology expert system"
    },
    {
      "name": "tac-hooks-mastery",
      "source": {
        "source": "github",
        "repo": "gblack686-openclaw/claude-code-hooks-mastery"
      },
      "description": "Hook lifecycle mastery (Lesson 15)"
    },
    {
      "name": "tac-ssva",
      "source": {
        "source": "github",
        "repo": "gblack686-openclaw/agentic-finance-review"
      },
      "description": "Specialized Self-Validating Agents (Lesson 19)"
    }
  ]
}
```

---

## Publishing to GitHub

### Step 1: Push the plugin repo

```bash
cd Desktop/tac/tac-experts-plugin

# Initialize if not already a repo
git init
git remote add origin https://github.com/gblack686-openclaw/tac-experts-plugin.git

# Create the official plugin manifest
mkdir -p .claude-plugin
# (create .claude-plugin/plugin.json and marketplace.json as shown above)

git add .
git commit -m "feat: official Claude Code plugin format"
git push -u origin main
```

### Step 2: Validate

```bash
# From the plugin directory
claude plugin validate .

# Or from within Claude Code
/plugin validate .
```

### Step 3: Tag a release

```bash
git tag v1.1.0
git push origin v1.1.0
```

---

## Where Plugins Download To

When a user installs a plugin, Claude Code:

1. **Clones** the source (git repo, npm package, or local path)
2. **Copies** the plugin directory to `~/.claude/plugins/cache/`
3. **Resolves** `${CLAUDE_PLUGIN_ROOT}` to the cached path
4. **Loads** commands, agents, skills, hooks from the cached copy

This means:
- Plugins are **self-contained** — no external file references
- **Symlinks** inside the plugin ARE followed during copy
- Files **outside** the plugin directory are NOT copied
- Updates pull from the source and re-cache

---

## Installing (User Side)

### Add the marketplace

```bash
# From GitHub
/plugin marketplace add gblack686-openclaw/tac-experts-plugin

# From git URL
/plugin marketplace add https://github.com/gblack686-openclaw/tac-experts-plugin.git

# From local directory (for testing)
/plugin marketplace add ./Desktop/tac/tac-experts-plugin
```

### Install the plugin

```bash
/plugin install tac-experts@tac-marketplace
```

### Use plugin commands

Commands are namespaced with the plugin name:

```bash
/tac-experts:experts/tac/question "What is SSVA?"
/tac-experts:experts/tac/plan "Add auth system"
/tac-experts:experts/tac/plan_build_improve "Add dark mode"
```

### Test locally (development)

```bash
# Load plugin without installing
claude --plugin-dir ./Desktop/tac/tac-experts-plugin
```

---

## Private Distribution

### Private GitHub repo

If the repo is private, users need authentication:

```bash
# User authenticates with GitHub CLI
gh auth login

# Then adds marketplace normally
/plugin marketplace add gblack686-openclaw/tac-experts-plugin
```

### Auto-updates for private repos

Set `GITHUB_TOKEN` for background auto-updates:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
```

Without the token, manual installs/updates still work (using git credential helpers), but background auto-updates at startup won't.

---

## Team Auto-Install

Add to a project's `.claude/settings.json` so team members are prompted on trust:

```json
{
  "extraKnownMarketplaces": {
    "tac-marketplace": {
      "source": {
        "source": "github",
        "repo": "gblack686-openclaw/tac-experts-plugin"
      }
    }
  },
  "enabledPlugins": {
    "tac-experts@tac-marketplace": true
  }
}
```

---

## Justfile Recipes

The following `just` recipes handle the publishing workflow:

```bash
# ─── Publishing ──────────────────────────────

# Convert current plugin.json to official .claude-plugin/ format
just plugin-init

# Validate plugin structure
just plugin-validate

# Build distributable (copy to temp, resolve symlinks)
just plugin-build

# Test plugin locally with Claude Code
just plugin-test

# Tag a new version and push
just plugin-release 1.2.0

# Full publish: validate → build → tag → push
just plugin-publish 1.2.0
```

### Recipe details

| Recipe | What it does |
|--------|-------------|
| `just plugin-init` | Creates `.claude-plugin/` dir, generates official `plugin.json` and `marketplace.json` from current `plugin.json` |
| `just plugin-validate` | Runs `claude plugin validate .` to check structure |
| `just plugin-build` | Copies plugin to `dist/` with symlinks resolved |
| `just plugin-test` | Launches `claude --plugin-dir .` for local testing |
| `just plugin-release 1.2.0` | Updates version in manifests, commits, tags, pushes |
| `just plugin-publish 1.2.0` | Full pipeline: validate → build → release |

---

## Updating & Versioning

### Bump version

Update the version in `.claude-plugin/plugin.json`:

```json
{ "version": "1.2.0" }
```

### Users update

```bash
# Update all marketplaces
/plugin marketplace update

# Reinstall to get latest
/plugin install tac-experts@tac-marketplace
```

### Versioning strategy

| Change | Version Bump | Example |
|--------|-------------|---------|
| New docs, fix typos | Patch (x.x.1) | 1.1.0 → 1.1.1 |
| New commands, examples | Minor (x.1.0) | 1.1.0 → 1.2.0 |
| Breaking changes, restructure | Major (1.0.0) | 1.x → 2.0.0 |

### Release channels

For stable vs bleeding-edge:

```json
// stable marketplace
{ "source": { "source": "github", "repo": "org/plugin", "ref": "stable" } }

// latest marketplace
{ "source": { "source": "github", "repo": "org/plugin", "ref": "main" } }
```

---

## Quick Reference

```bash
# ─── Development ─────────────────────────────
just plugin-test                  # Test locally
just plugin-validate              # Check structure

# ─── Publishing ──────────────────────────────
just plugin-publish 1.2.0         # Full publish pipeline

# ─── User Installation ───────────────────────
/plugin marketplace add gblack686-openclaw/tac-experts-plugin
/plugin install tac-experts@tac-marketplace

# ─── User Commands ───────────────────────────
/tac-experts:experts/tac/question "What is SSVA?"
/tac-experts:experts/tac/plan "Add feature X"
```
