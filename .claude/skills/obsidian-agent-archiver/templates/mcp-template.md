---
type: mcp-server
name: "{{title}}"
banner: "[[_assets/banners/mcp-banner.png]]"
mtg_card: "{{mtg_card}}"
mtg_color: "Colorless"
mtg_edition: "8th Edition"
mtg_set_code: "8ed"
transport: stdio
status: active
created: <% tp.date.now("YYYY-MM-DD") %>
updated: <% tp.date.now("YYYY-MM-DD") %>
human_reviewed: false
tac_original: false
tags: [mcp]
cssclasses: [cards, cards-cover]
---

![[mcp-banner.png|banner]]

# {{title}}

## Purpose
What external systems does this server connect to?

## Configuration
```json
{
  "mcpServers": {
    "{{title}}": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-{{name}}"],
      "env": {}
    }
  }
}
```

## Exposed Tools
| Tool | Description |
|------|-------------|
| `tool_name` | What it does |

## Exposed Resources
| URI Pattern | Description |
|-------------|-------------|
| `resource://path` | What data it provides |

## Exposed Prompts
| Prompt | Description |
|--------|-------------|
| `prompt_name` | Pre-built prompt template |

## Used By Agents
- [[Agent-Name]]

## Security
- Authentication: OAuth 2.1 / API Key / None
- Permissions: List required permissions

## Source Files
- Configuration: `.mcp.json` or `mcp_servers/{{title}}/`

## Changelog
- <% tp.date.now("YYYY-MM-DD") %>: Created
