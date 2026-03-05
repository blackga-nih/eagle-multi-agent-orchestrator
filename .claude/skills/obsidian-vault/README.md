# Obsidian Vault Integration

> Persistent knowledge management for Claude Code projects

## Overview

This skill integrates Obsidian vault capabilities into your Claude Code workflow, enabling:
- 📝 Automatic note creation and management
- 🔍 Full-text search across your knowledge base
- 🧠 Persistent context and memory across sessions
- 📊 Architecture Decision Records (ADRs)
- 🔗 Knowledge graph with backlinks

## Quick Start

### 1. Install Dependencies

```bash
cd .claude/skills/obsidian-vault
npm install
```

### 2. Configure Vault Path

Edit `.claude/skills/obsidian-vault/config/vault-settings.json`:

```json
{
  "vaultPath": "/path/to/your/obsidian/vault",
  "projectFolder": "Projects/your-project-name"
}
```

### 3. Initialize Vault Structure

```bash
node scripts/init-vault.js
```

This creates:
- Folder structure (Daily Notes, Decisions, Learnings, Tasks)
- Template files
- Project index
- Initial configuration

### 4. Test Integration

```bash
# In Claude Code session
/note-create "My First Note"
/note-search "test"
/daily-note
```

## Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/note-create [title] [category?]` | Create new note | `/note-create "API Design" architecture` |
| `/note-search [query]` | Search vault | `/note-search authentication` |
| `/decision-log [title]` | Create ADR | `/decision-log "Use Lambda"` |
| `/daily-note` | Open today's daily note | `/daily-note` |
| `/vault-sync` | Sync session to vault | `/vault-sync` |
| `/context-load [note]` | Load note into context | `/context-load "ADR-005"` |

## Directory Structure

```
.claude/skills/obsidian-vault/
├── SKILL.md                      # Skill definition
├── README.md                     # This file
├── package.json                  # Node.js dependencies
├── scripts/
│   ├── vault-operations.js       # Core vault operations
│   ├── note-templates.js         # Template rendering
│   ├── search-engine.js          # Search functionality
│   └── init-vault.js             # Vault initialization
├── templates/
│   ├── daily-note.md             # Daily note template
│   ├── adr.md                    # ADR template
│   ├── learning.md               # Learning template
│   └── task.md                   # Task template
└── config/
    ├── vault-settings.json       # Main configuration
    └── note-categories.yaml      # Note taxonomy
```

## Configuration

### Vault Settings

**Location:** `config/vault-settings.json`

Key settings:
- `vaultPath`: Path to your Obsidian vault
- `projectFolder`: Folder within vault for this project
- `features.autoSync`: Auto-sync on session start/end
- `features.createDailyNote`: Auto-create daily notes
- `search.depth`: Link traversal depth
- `permissions.readOnly`: Read-only mode

### Note Categories

**Location:** `config/note-categories.yaml`

Defines:
- Folder structure
- Templates for each category
- Default tags
- Metadata schemas

## Hooks Integration

### SessionStart
Automatically runs when you start a Claude Code session:
- Creates/opens today's daily note
- Loads recent project notes (last 3 days)
- Displays pending tasks

### Stop
Runs when you type "stop":
- Appends session summary to daily note
- Updates work-status.md
- Tags notes created during session

### SessionEnd
Runs when session ends:
- Triggers @knowledge-curator agent
- Extracts learnings from session
- Creates retrospective
- Syncs all changes

## Templates

### Daily Note Template
```markdown
---
date: {{date}}
project: {{project}}
tags: [daily, {{project-tag}}]
---

# {{date-formatted}}

## Context
<!-- What am I working on today? -->

## Tasks
- [ ]

## Learnings
<!-- What did I learn? -->
```

### ADR Template
```markdown
---
date: {{date}}
status: proposed
tags: [adr, architecture, decision]
adr-number: {{number}}
---

# ADR-{{number}}: {{title}}

## Status
{{status}} - {{date}}

## Context
<!-- What issue are we addressing? -->

## Decision
<!-- What change are we proposing? -->

## Consequences
- Positive:
- Negative:
```

## Workflow Examples

### Daily Workflow
```bash
# Morning - start session
claude

# Automatically creates daily note
# Loads recent context

# During work - log decisions
/decision-log "Use PostgreSQL for user data"

# During work - capture learnings
"I learned how to optimize lambda cold starts"
# Automatically captured by @knowledge-curator

# End of day
stop
# Session logged to daily note
# Learnings extracted and saved
```

### Research Workflow
```bash
# Search past solutions
/note-search "how did we handle rate limiting"

# Load relevant context
/context-load "ADR-008-Rate-Limiting-Strategy"

# Create new learning note
/note-create "Redis vs In-Memory Rate Limiting" learning
```

### Architecture Workflow
```bash
# Start architectural discussion
"We need to decide between microservices and monolith"

# Claude helps analyze options

# Log the decision
/decision-log "Modular Monolith with Domain Boundaries"

# ADR created with full context
# Links to related decisions
# Captures alternatives considered
```

## Agents

### @knowledge-curator
**Purpose:** Extract and organize learnings from sessions

**Activates:**
- Automatically at SessionEnd
- On demand with `/curate-knowledge`

**Actions:**
- Reviews session transcript
- Identifies key decisions and learnings
- Creates/updates relevant notes
- Maintains knowledge graph coherence

### @obsidian-organizer
**Purpose:** Keep vault organized and structured

**Activates:**
- On demand with `/organize-vault`
- Weekly (if configured)

**Actions:**
- Analyzes note structure
- Suggests tagging improvements
- Identifies orphaned notes
- Creates Maps of Content (MOCs)
- Validates backlinks

## Search Capabilities

### Basic Search
```bash
/note-search authentication
```

### Tag Search
```bash
/note-search #architecture #aws
```

### Date Range Search
```bash
/note-search date:2025-11-01..2025-11-13
```

### Folder Search
```bash
/note-search folder:Decisions lambda
```

### Combined Search
```bash
/note-search #decision aws date:last-30-days
```

## Troubleshooting

### Issue: Vault not found
**Solution:** Update `vaultPath` in `vault-settings.json`

### Issue: Notes not being created
**Solution:**
1. Check vault permissions
2. Run `node scripts/init-vault.js`
3. Verify folder structure exists

### Issue: Search returns no results
**Solution:**
1. Run `/vault-sync` to rebuild index
2. Check if notes have content
3. Try broader search terms

### Issue: Templates not rendering
**Solution:**
1. Check templates exist in `templates/` folder
2. Verify template syntax
3. Check `note-categories.yaml` configuration

## Performance

- **Small vaults** (< 1000 notes): Sub-second operations
- **Medium vaults** (1000-5000 notes): 1-2 second operations
- **Large vaults** (> 5000 notes): 2-5 second operations

Optimizations:
- Indexed search
- Cached metadata
- Lazy loading of linked notes
- Incremental sync

## Security

- All operations are local (no external API calls)
- Vault contents never sent to external services
- Optional read-only mode
- Configurable folder permissions
- Operations logged for audit

## Future Enhancements

Planned for future releases:
- [ ] MCP server for bidirectional sync
- [ ] Real-time vault monitoring
- [ ] Semantic search with embeddings
- [ ] Graph visualization
- [ ] Mobile vault sync
- [ ] Obsidian plugin integration
- [ ] Canvas support
- [ ] Dataview query execution

## Support

For issues or questions:
1. Check this README
2. Review `SKILL.md` for detailed documentation
3. Check logs: `.claude/logs/obsidian-operations.log`
4. Consult integration plan: `.claude/OBSIDIAN_INTEGRATION_PLAN.md`

## Version

**Version:** 1.0.0
**Last Updated:** November 13, 2025
**Requires:** Claude Code 1.0+, Node.js 18+
