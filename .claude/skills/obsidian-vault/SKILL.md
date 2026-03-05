# Obsidian Vault Integration Skill

> Comprehensive Obsidian vault management for persistent project knowledge

## Purpose

This skill enables Claude Code to interact with an Obsidian knowledge vault, providing:
- Note creation and management
- Vault-wide search capabilities
- Knowledge graph maintenance
- Automatic documentation of decisions and learnings
- Persistent context across sessions

## When to Use This Skill

Activate this skill when:
- User requests note operations (`create a note`, `search my notes`)
- Creating architectural decision records
- Documenting learnings from a session
- Loading context from past work
- Organizing project knowledge

## Capabilities

### Note Operations
- **Create** notes using templates (daily, ADR, learning, task)
- **Read** notes and load into conversation context
- **Search** vault with full-text and tag filtering
- **Update** existing notes with new information
- **Link** notes together (backlinks and forward links)

### Knowledge Management
- Generate daily notes automatically
- Create Architecture Decision Records (ADRs)
- Extract and save learnings from sessions
- Maintain project index and MOCs (Maps of Content)
- Organize notes by tags and folders

### Context Loading
- Load notes with linked content (configurable depth)
- Search and retrieve relevant past decisions
- Prime conversation with project context
- Sync session state to vault

## Configuration

Configuration is managed through:
- **Vault Settings**: `.claude/skills/obsidian-vault/config/vault-settings.json`
- **Note Categories**: `.claude/skills/obsidian-vault/config/note-categories.yaml`

### Required Setup

Before using this skill, you must:

1. **Set Vault Path**
   ```json
   {
     "vaultPath": "/path/to/your/obsidian/vault"
   }
   ```

2. **Configure Project Folder**
   ```json
   {
     "projectFolder": "Projects/your-project-name"
   }
   ```

3. **Initialize Vault Structure** (first time only)
   ```bash
   node .claude/skills/obsidian-vault/scripts/init-vault.js
   ```

## Available Commands

When this skill is active, you can use:

- `/note-create [title]` - Create a new note
- `/note-search [query]` - Search the vault
- `/decision-log [title]` - Create an ADR
- `/daily-note` - Open/create today's daily note
- `/vault-sync` - Sync current session to vault
- `/context-load [note-name]` - Load note context

## Workflow Examples

### Example 1: Starting a Session
```
User: Start my daily note
Claude: [Activates obsidian-vault skill]
        Created daily note: Daily Notes/2025-11-13.md

        Today's focus:
        - Review gb-automation-landing deployment
        - Plan Obsidian integration

        3 pending tasks from yesterday:
        - [ ] Fix mobile navigation
        - [ ] Update pricing tier
        - [ ] SSL certificate setup
```

### Example 2: Logging a Decision
```
User: We decided to use Lambda instead of ECS for cost reasons
Claude: [Activates obsidian-vault skill]
        Let me document this architectural decision.

        Created: Decisions/Architecture/ADR-007-Lambda-for-API.md

        Status: Accepted
        Context: Cost optimization for API endpoints
        Decision: Use AWS Lambda instead of ECS Fargate

        Linked to:
        - Projects/gb-automation-landing/architecture-overview.md
        - Decisions/ADR-003-Serverless-First.md
```

### Example 3: Searching Past Knowledge
```
User: How did we handle SSL certificates last time?
Claude: [Activates obsidian-vault skill]
        Searching vault for "SSL certificates"...

        Found 3 relevant notes:

        1. **LIGHTSAIL-SSL-SETUP-GUIDE.md** (Nov 10, 2025)
           - Used Certbot with Route53 DNS validation
           - Automated renewal with cron job

        2. **ADR-005-SSL-Certificate-Strategy.md** (Oct 15, 2025)
           - Decision: Use Let's Encrypt for all non-production
           - Use AWS Certificate Manager for production

        3. **Daily Notes/2025-11-10.md**
           - Troubleshooting: Certificate validation timeout
           - Solution: Added TXT record manually

        Would you like me to load any of these notes for more detail?
```

## Technical Implementation

### Dependencies
This skill requires:
- Node.js 18+
- npm packages: `glob`, `gray-matter`, `fuse.js`, `date-fns`, `yaml`

Install with:
```bash
cd .claude/skills/obsidian-vault
npm install
```

### File Structure
```
.claude/skills/obsidian-vault/
├── SKILL.md                     # This file
├── scripts/
│   ├── vault-operations.js      # Core vault operations
│   ├── note-templates.js        # Template rendering
│   ├── search-engine.js         # Search functionality
│   └── init-vault.js            # One-time vault initialization
├── templates/
│   ├── daily-note.md            # Daily note template
│   ├── adr.md                   # ADR template
│   ├── learning.md              # Learning note template
│   └── task.md                  # Task note template
├── config/
│   ├── vault-settings.json      # Vault configuration
│   └── note-categories.yaml     # Note taxonomy
└── package.json                 # Node.js dependencies
```

## Integration with Hooks

This skill integrates seamlessly with Claude Code hooks:

### SessionStart Hook
Automatically:
- Creates/opens today's daily note
- Loads recent project notes (last 3 days)
- Displays pending tasks from vault

### Stop Hook
Automatically:
- Appends session summary to daily note
- Updates work-status.md in vault
- Tags notes created during session

### SessionEnd Hook
Automatically:
- Triggers @knowledge-curator agent
- Creates session retrospective
- Syncs all changes to vault

## Security & Permissions

### Access Control
- Only reads/writes to configured vault path
- Respects `.claudeignore` patterns
- Optional read-only mode

### Privacy
- All operations are local (no external API calls)
- Vault contents never sent to external services
- Operations logged to `.claude/logs/obsidian-operations.log`

## Model Recommendation

**Recommended:** Sonnet (claude-sonnet-4-5)
- Balanced performance and cost
- Sufficient for note operations and search
- Good at maintaining context and structure

**Alternative:** Haiku for simple operations
- Use for basic note creation
- Search queries
- Template rendering

## Troubleshooting

### Vault Not Found
```
Error: Vault path does not exist: /path/to/vault
Solution: Update vaultPath in vault-settings.json
```

### Note Template Missing
```
Error: Template not found: custom-template.md
Solution: Check templates/ folder or use default templates
```

### Search Returns No Results
```
Issue: Search query returns no results
Solution:
- Check vault indexing with /vault-sync
- Verify note has content (not empty)
- Try broader search terms
```

## Version

**Version:** 1.0
**Last Updated:** November 13, 2025
**Model Compatibility:** All Claude models (Haiku, Sonnet, Opus)
