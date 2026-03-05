# Obsidian Vault Schema Generator Skill

A Claude Code skill that analyzes Obsidian vaults and generates comprehensive schemas for visualization, analysis, and integration.

## Quick Start

### Installation

This skill is already installed in your `.claude/skills/` directory. To use it, simply invoke it in conversation:

```
User: "Generate a schema for my Obsidian vault"
```

### Requirements

- Python 3.7+ (managed via `uv`)
- PyYAML library (auto-installed via `uv`)

**Installation:**
```bash
# Install uv if not already installed
pip install uv

# Dependencies will be auto-installed when running the script
```

### Usage Examples

**Complete Schema (All Formats)**
```
User: "Generate a complete schema for my Obsidian vault"
```

**Specific Format**
```
User: "Generate just the GraphML file for 3D visualization"
User: "Create a JSON schema of my vault links"
```

**With Exclusions**
```
User: "Generate schema but skip Attachments and backup folders"
```

## What It Does

The skill:

1. **Scans** your Obsidian vault directory
2. **Extracts**:
   - Folder structure
   - Note titles and metadata
   - Wikilinks (`[[links]]`)
   - Tags (`#tags`)
   - Frontmatter (YAML)
   - File statistics
3. **Builds** a knowledge graph of connections
4. **Generates** output in multiple formats:
   - JSON (programmatic use)
   - YAML (human-readable)
   - GraphML (visualization tools)
   - Markdown (reports)

## Output Files

```
vault-schema-output/
├── vault_schema.json          # Complete structured data
├── vault_schema.yaml          # Human-readable format
├── vault_graph.graphml        # For Gephi, 3D Graph plugin
└── VAULT_SCHEMA_REPORT.md     # Summary report
```

## Technical Details

### Parser Features

- **Frontmatter**: Extracts YAML metadata from note headers
- **Wikilinks**: Resolves `[[Note Name]]` and `[[Note|Alias]]` formats
- **Tags**: Captures `#tag` and `#nested/tags` plus frontmatter tags
- **Links**: Maps bidirectional relationships between notes
- **Performance**: Handles large vaults (10,000+ notes)

### Schema Structure

**JSON Schema includes:**
```json
{
  "vault_info": { /* metadata and statistics */ },
  "folders": [ /* folder hierarchy */ ],
  "notes": [ /* all notes with metadata */ ],
  "links": [ /* connections between notes */ ],
  "statistics": { /* analytics */ }
}
```

**Each note contains:**
- Unique ID
- Title and path
- Creation/modification dates
- Tags and frontmatter
- Inbound/outbound links
- Word count and size

## Use Cases

### 1. 3D Visualization
Generate GraphML and import into:
- Obsidian 3D Graph plugin
- Gephi for network analysis
- yEd for diagram creation

### 2. Vault Analysis
Identify:
- Most connected notes (hubs)
- Orphaned notes (no links)
- Tag distribution
- Knowledge clusters

### 3. Migration/Backup
Export vault structure to:
- Other note-taking apps
- Databases
- Content management systems

### 4. AI/RAG Integration
Use schemas for:
- Vector database indexing
- Semantic search
- Context-aware AI agents
- Knowledge base Q&A

## Command Line Usage

You can also run the parser directly using `uv`:

```bash
# Complete schema, all formats
uv run .claude/skills/obsidian-schema-generator/vault_parser.py \
  --vault-path "C:\Users\gblac\OneDrive\Desktop\obsidian\Gbautomation" \
  --schema-type complete \
  --output-format all \
  --output-dir "./my-vault-schema"

# Just JSON with content
uv run .claude/skills/obsidian-schema-generator/vault_parser.py \
  --vault-path "/path/to/vault" \
  --output-format json \
  --include-content

# Exclude folders
uv run .claude/skills/obsidian-schema-generator/vault_parser.py \
  --vault-path "/path/to/vault" \
  --exclude-folders "Attachments,Templates,.trash"
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--vault-path` | Path to Obsidian vault (required) | - |
| `--schema-type` | `structure`, `links`, `metadata`, `complete` | `complete` |
| `--output-format` | `json`, `yaml`, `graphml`, `markdown`, `all` | `all` |
| `--output-dir` | Where to save outputs | `./vault-schema-output` |
| `--exclude-folders` | Comma-separated folder names to skip | - |
| `--include-content` | Include full note content (large files) | `false` |

## Troubleshooting

**"No module named 'yaml'"**
```bash
# Install dependencies with uv
uv pip install pyyaml

# Or let uv auto-install on first run
uv run .claude/skills/obsidian-schema-generator/vault_parser.py --help
```

**"Permission denied"**
- Check vault directory permissions
- Run with appropriate user access

**"Too many files"**
- Use `--exclude-folders` to filter
- Process in batches
- Disable `--include-content`

**"Links not resolving"**
- Parser uses note titles to resolve wikilinks
- Ensure wikilinks match note file names
- Check for duplicate note titles

## Development

### Project Structure
```
.claude/skills/obsidian-schema-generator/
├── skill.md              # Skill instructions for Claude
├── vault_parser.py       # Main parser script
├── README.md            # This file
└── examples/            # Example outputs (optional)
```

### Testing

Test the parser on a small vault first:

```bash
uv run vault_parser.py \
  --vault-path "./test-vault" \
  --output-format markdown
```

Review the markdown report before generating full schemas.

## License

Part of Claude Code skills - use freely for personal and commercial projects.

## Support

For issues or questions:
1. Check the skill.md file for detailed instructions
2. Review error messages in console output
3. Test on a smaller vault subset
4. Report bugs via Claude Code feedback

---

**Version:** 1.0.0
**Last Updated:** 2025-11-17