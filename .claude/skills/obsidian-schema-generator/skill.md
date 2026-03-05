# Obsidian Vault Schema Generator

Generate comprehensive schemas from Obsidian vaults including folder structure, note relationships, metadata, and link graphs.

## Description

This skill analyzes an Obsidian vault and generates various schema formats that can be used for visualization, analysis, migration, or AI context. It extracts:

- Folder hierarchy and file organization
- Note-to-note relationships via wikilinks
- Frontmatter metadata and properties
- Tags and categories
- Orphaned notes and connection statistics
- Knowledge graph structure

## When to Use

Use this skill when users want to:
- "Generate a schema for my Obsidian vault"
- "Analyze my knowledge base structure"
- "Export my vault as a graph"
- "Create a map of my notes and links"
- "Visualize my Obsidian connections"
- "Generate metadata from my vault"

## Available Tools

You have access to all standard Claude Code tools including:
- Read: Read markdown files and vault contents
- Glob: Find files matching patterns
- Bash: Execute the vault_parser.py script
- Write: Generate schema output files

## Instructions

### 1. Determine Vault Location

First, check if the user has specified a vault path in CLAUDE.md or ask them:

```bash
# Default vault path from CLAUDE.md
C:\Users\gblac\OneDrive\Desktop\obsidian\Gbautomation
```

### 2. Understand User Requirements

Ask the user what type of schema they need:

**Schema Types:**
- `structure`: Folder hierarchy and file organization only
- `links`: Note relationships and wikilink connections
- `metadata`: Frontmatter, tags, and properties
- `complete`: All of the above (default)

**Output Formats:**
- `json`: Structured JSON for programmatic use
- `yaml`: Human-readable YAML
- `graphml`: Graph format for visualization tools (Gephi, 3D Graph)
- `markdown`: Readable documentation report
- `all`: Generate all formats

### 3. Run the Schema Parser

Execute the vault_parser.py script using `uv`:

```bash
uv run .claude/skills/obsidian-schema-generator/vault_parser.py \
  --vault-path "C:\Users\gblac\OneDrive\Desktop\obsidian\Gbautomation" \
  --schema-type complete \
  --output-format all \
  --output-dir "./vault-schema-output"
```

**Note:** The skill uses `uv` for fast Python execution. If dependencies are needed, they'll be auto-installed.

**Parameters:**
- `--vault-path`: Path to Obsidian vault directory
- `--schema-type`: Type of schema (structure/links/metadata/complete)
- `--output-format`: Format(s) to generate (json/yaml/graphml/markdown/all)
- `--output-dir`: Where to save output files
- `--exclude-folders`: Comma-separated folders to skip (e.g., "Attachments,.trash")
- `--include-content`: Include note content in schema (warning: large output)

### 4. Process the Results

After generation, analyze the output:

1. **Read the summary statistics** from the console output
2. **Review generated files** in the output directory
3. **Validate the schema** for completeness
4. **Present results** to the user with:
   - Total notes scanned
   - Total links found
   - Orphaned notes count
   - Output file locations
   - Sample of the schema structure

### 5. Provide Next Steps

Suggest what the user can do with the schema:

- **For 3D Visualization**: "You can import the GraphML file into the Obsidian 3D Graph plugin"
- **For Analysis**: "The JSON schema contains X nodes and Y connections, revealing..."
- **For Migration**: "The complete schema is ready for import into [target system]"
- **For AI/RAG**: "The schema can be indexed for semantic search and context"

## Output File Structure

The skill generates files in this structure:

```
vault-schema-output/
├── vault_schema.json           # Complete schema in JSON
├── vault_schema.yaml           # Complete schema in YAML
├── vault_graph.graphml         # Graph format for visualization
├── VAULT_SCHEMA_REPORT.md      # Human-readable report
└── schema_metadata.json        # Generation metadata
```

## Schema Format Specifications

### JSON Schema Structure
```json
{
  "vault_info": {
    "name": "Gbautomation",
    "path": "C:\\Users\\gblac\\OneDrive\\Desktop\\obsidian\\Gbautomation",
    "scanned_at": "2025-11-17T12:00:00Z",
    "total_notes": 150,
    "total_links": 423,
    "total_folders": 11
  },
  "folders": [
    {
      "path": "00a - grimoire/liber ozymandias",
      "note_count": 45,
      "subfolder_count": 5
    }
  ],
  "notes": [
    {
      "id": "note_001",
      "title": "Example Note",
      "path": "001 - Strategy/weekly-plan.md",
      "created": "2025-01-15",
      "modified": "2025-11-16",
      "tags": ["planning", "strategy"],
      "frontmatter": {
        "author": "GB",
        "status": "active"
      },
      "outbound_links": ["note_002", "note_015"],
      "inbound_links": ["note_003"],
      "word_count": 1250
    }
  ],
  "links": [
    {
      "source": "note_001",
      "target": "note_002",
      "link_text": "See also",
      "context": "For more details, [[See also]]"
    }
  ],
  "statistics": {
    "orphaned_notes": 12,
    "most_connected_note": "note_045",
    "average_links_per_note": 2.82,
    "tag_distribution": {
      "planning": 15,
      "research": 23
    }
  }
}
```

### GraphML Format
Standard GraphML XML format compatible with:
- Obsidian 3D Graph plugin
- Gephi
- yEd
- Cytoscape

## Error Handling

**Common Issues:**

1. **Vault path not found**
   - Verify path exists
   - Check for typos
   - Use absolute paths on Windows

2. **Permission errors**
   - Ensure read access to vault directory
   - Check file permissions

3. **Large vault performance**
   - For vaults with >10,000 notes, use `--exclude-folders` to filter
   - Disable `--include-content` for faster processing
   - Process in chunks if needed

4. **Invalid markdown**
   - Parser skips malformed files
   - Warnings logged to console
   - Continue processing remaining files

## Examples

### Example 1: Complete Schema
```
User: "Generate a complete schema for my Obsidian vault"
Assistant: I'll generate a complete schema including structure, links, and metadata.

[Runs vault_parser.py with --schema-type complete --output-format all]

✅ Schema generation complete!

📊 Summary:
- Total notes: 347
- Total links: 1,253
- Orphaned notes: 23
- Folders: 11
- Most connected: "Projects.md" (47 links)

📁 Generated files:
- vault_schema.json (425 KB)
- vault_schema.yaml (512 KB)
- vault_graph.graphml (189 KB)
- VAULT_SCHEMA_REPORT.md (human-readable)

The GraphML file can be imported into Obsidian 3D Graph plugin for visualization.
```

### Example 2: Link Analysis Only
```
User: "Show me just the connections between my notes"
Assistant: I'll generate a links-focused schema.

[Runs vault_parser.py with --schema-type links --output-format json]

✅ Link schema generated!

📊 Statistics:
- Total connections: 1,253
- Bidirectional links: 89
- Most linked note: "Projects.md"
- Average connections per note: 3.61
```

### Example 3: Exclude Folders
```
User: "Generate schema but skip my Attachments and Templates folders"
Assistant: I'll exclude those folders from the analysis.

[Runs with --exclude-folders "Attachments,Templates,bkp_llm-chats"]

✅ Filtered schema complete (331 notes analyzed)
```

## Tips for Users

1. **First-time users**: Start with `--output-format markdown` to get a readable report
2. **Visualization**: Use `graphml` format for 3D Graph or Gephi
3. **Large vaults**: Exclude backup/attachment folders for faster processing
4. **AI/RAG systems**: Use JSON format with `--include-content` flag
5. **Regular analysis**: Schedule periodic schema generation to track vault growth

## Technical Notes

- The parser handles malformed frontmatter gracefully
- Wikilinks with aliases `[[note|alias]]` are properly extracted
- Both `[[wikilinks]]` and `[markdown](links.md)` are captured
- Tag formats: `#tag`, `#nested/tag`, and frontmatter tags array
- File modification times use OS metadata
- Unicode file names are fully supported