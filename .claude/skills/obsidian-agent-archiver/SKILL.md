---
name: Obsidian Agent Archiver
description: Document AI agents, ADWs, skills, and workflows into a visual Obsidian knowledge base with card galleries and cross-references. Use when archiving agent systems.
dependencies: python>=3.8, pillow>=9.0
---

# Obsidian Agent Archiver

This skill creates visual documentation for AI agent systems in Obsidian.

## Instructions

1. **Scan Source Repository**: Identify ADWs, agents, skills, experts, MCP servers, prompts, and scripts
2. **Create Folder Structure**: Set up the AI-Agent-KB hierarchy in the target Obsidian vault
3. **Generate Banners**: Run `scripts/create_banners.py` to create themed placeholder images
4. **Populate Content**: Use templates to document each component with source references
5. **Install CSS**: Copy `css/ai-agent-kb-cards.css` to Obsidian's `.obsidian/snippets/`

## Usage

```bash
# Generate banner images
python scripts/create_banners.py --output-dir "/path/to/obsidian/AI-Agent-KB/_assets/banners"

# Populate knowledge base from source repo
python scripts/populate_kb.py \
  --source-repo "/path/to/agent-repo" \
  --obsidian-vault "/path/to/obsidian/vault"
```

## Components

- **Templates**: Markdown templates for each entity type
- **Base Templates**: `.base` files for Obsidian Bases (database views)
- **Scripts**: Python scripts for automation
- **CSS**: GB Automation themed Obsidian snippet

## Obsidian Bases

Each category has a `.base` file for interactive database views:

```
AI-Agent-KB/
├── Dashboard.base          # Master "base of bases"
├── 01-ADWs/ADWs.base
├── 02-Agents/Agents.base
├── 03-Skills/Skills.base
├── 04-MCP-Servers/MCP-Servers.base
├── 05-Prompts/Prompts.base
├── 06-Scripts/Scripts.base
└── 07-Experts/Experts.base
```

**Embedding Bases in Notes:**
```markdown
![[ADWs.base]]              # Embed full base
![[ADWs.base#Active]]       # Embed specific view
```

**Base Syntax Reference:**
```yaml
filters:
  and:
    - file.hasTag("agent")
    - file.inFolder("AI-Agent-KB/02-Agents")

properties:
  - name
  - status
  - category

views:
  - type: table
    name: "All Agents"
    order:
      - name
```

**Enable Bases Plugin:**
Settings → Core Plugins → Enable "Bases"

## Theme Options

### Dark Angular Theme (Recommended)
- Dark backgrounds (#0d0d0d, #1a1a1a, #242424)
- NO rounded corners - sharp, angular aesthetic
- Terracotta accent (#D97757)
- CSS file: `ai-agent-kb-dark-angular.css`

### Light GB Automation Theme
- Cream backgrounds (#F3F1E7)
- Terracotta accents
- Glass panel effects
- CSS file: `ai-agent-kb-cards.css`

## Advanced: Datacore Integration

For interactive views with live editing, install Datacore via BRAT:

1. Install BRAT plugin
2. Add beta plugin: `blacksmithgu/datacore`
3. Use DatacoreJSX blocks for interactive queries

**Example Datacore Query:**
```datacorejsx
const agents = dc.useQuery(`
  @page
  WHERE contains(tags, "agent")
  AND contains(file.path, "AI-Agent-KB")
`);

return (
  <div className="agent-grid">
    {agents.map(agent => (
      <div className="agent-card" key={agent.file.path}>
        <h3>{agent.name}</h3>
        <span className="status">{agent.status}</span>
      </div>
    ))}
  </div>
);
```

## Advanced: Dynamic Views Plugin

For Grid/Masonry card layouts:

1. Install Dynamic Views via BRAT: `greetclammy/dynamic-views`
2. Works with both Bases and Datacore
3. Features: infinite scroll, image previews, up to 14 properties per card
