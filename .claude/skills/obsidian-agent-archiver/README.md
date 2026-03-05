# Obsidian Agent Archiver

> Document AI agents, ADWs, skills, and workflows into a visual Obsidian knowledge base with card galleries and cross-references.

## Overview

This skill creates a comprehensive, visually pleasing knowledge base in Obsidian for documenting AI agent systems. It uses the **GB Automation theme** with terracotta accents, cream backgrounds, and elegant typography.

## Features

- **7 Entity Types**: ADWs, Agents, Skills, Experts, MCP Servers, Prompts, Scripts
- **Card Galleries**: Dataview-powered visual galleries with hover effects
- **Themed Banners**: Auto-generated banner images for each category
- **Cross-References**: Wiki-links connect related components
- **Source Linking**: Each doc links back to source code files

## Quick Start

### 1. Generate Banner Images

```bash
cd .claude/skills/obsidian-agent-archiver
pip install pillow
python scripts/create_banners.py --output-dir "C:/path/to/obsidian/AI-Agent-KB/_assets/banners"
```

### 2. Populate from Source Repo

```bash
python scripts/populate_kb.py \
  --source-repo "C:/path/to/agent-repo" \
  --obsidian-vault "C:/path/to/obsidian/vault"
```

### 3. Install CSS Snippet

Copy `css/ai-agent-kb-cards.css` to your Obsidian vault's `.obsidian/snippets/` folder and enable it in Settings > Appearance > CSS Snippets.

## Folder Structure

```
AI-Agent-KB/
├── _Dashboard.md           # Main entry point
├── _assets/banners/        # Banner images
├── 01-ADWs/                # AI Developer Workflows
├── 02-Agents/              # Agent Definitions
├── 03-Skills/              # Reusable Skills
├── 04-MCP-Servers/         # MCP Server Configs
├── 05-Prompts/             # Prompt Library
├── 06-Scripts/             # Code & Automation
└── 07-Experts/             # Domain Experts
```

## Theme Colors

| Element | Color | Hex |
|---------|-------|-----|
| Accent (Primary) | Terracotta | `#D97757` |
| Accent (Deep) | Deep Terracotta | `#C26D52` |
| Background | Cream | `#F3F1E7` |
| Panel | Warm Cream | `#E6E4D9` |
| Text | Near Black | `#191919` |
| Border | Soft Taupe | `#D6D4C8` |

## Templates

### ADW Template
For documenting AI Developer Workflows with workflow diagrams and agent relationships.

### Agent Template
For agent definitions with system prompts, tools, and configuration.

### Skill Template
For reusable capability packages with instructions and usage examples.

### Expert Template
For domain expertise documentation with mental models and patterns.

### MCP Template
For MCP Server configurations with exposed tools and resources.

### Prompt Template
For prompt library entries with variables and examples.

### Script Template
For code documentation with usage and dependencies.

## Requirements

- **Python 3.8+** with Pillow for banner generation
- **Obsidian** with these plugins:
  - Dataview (for dynamic queries)
  - Templater (for template insertion)

## Usage

### Invoke the Skill

When working with Claude Code, describe an agent system and ask to document it:

```
Document the agents in /path/to/repo into an Obsidian knowledge base
```

Claude will use this skill to:
1. Scan the repository for ADWs, agents, skills, experts
2. Create the folder structure
3. Generate themed banner images
4. Populate documentation with source references
5. Create indexes and dashboard

## Source Repository Detection

The skill scans for:

| Component | Location |
|-----------|----------|
| Agents | `.claude/agents/*.md` |
| ADWs | `adws/adw_workflows/adw_*.py` |
| Skills | `.claude/skills/*/SKILL.md` |
| Experts | `.claude/commands/experts/*/expertise.yaml` |
| Commands | `.claude/commands/*.md` |

## License

Part of GB Automation consulting toolkit.
