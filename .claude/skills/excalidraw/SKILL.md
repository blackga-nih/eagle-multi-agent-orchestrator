---
name: excalidraw
description: Generate professional Excalidraw diagrams (.excalidraw.md files) from textual descriptions, specifications, or code analysis. Understands Excalidraw's JSON format, element positioning, styling, and layout best practices. Works with any expert domain to create visualizations of architectures, workflows, data flows, and system designs.
---

# Excalidraw Diagram Generator Skill

Automatically generate professional Excalidraw diagrams (`.excalidraw.md` files) from textual descriptions, specifications, or code analysis. This skill can be used by any expert to create visualizations relevant to their domain.

## Core Capabilities

### 1. **Diagram Type Recognition**
- Sequential flowcharts (with retry logic, decision points)
- Architecture diagrams (layered, containerized)
- Ecosystem/data flow diagrams (service interconnectivity)
- Concentric circle hierarchies (trust policies, access levels)
- AWS/cloud infrastructure diagrams
- Domain-specific visualizations (backend services, frontend components, deployment pipelines, etc.)

### 2. **Element Generation**
Generates all Excalidraw element types:
- **Rectangles**: Containers, services, components
- **Ellipses**: Circular nodes, state representations
- **Arrows**: Data flow, dependencies, connections
- **Text**: Labels, descriptions, documentation
- **Lines**: Boundaries, groupings

### 3. **Smart Positioning**
- Automatic grid-based layout
- Proper spacing between elements
- Vertical/horizontal flow detection
- Avoid element overlap
- Center-aligned compositions

### 4. **Styling & Theming**

**IMPORTANT**: Always follow the style guide in `docs/excalidraw-best-practices.md`. Key rules:
- **White/light canvas background**: `#ffffff` or `transparent` — NEVER use dark backgrounds like `#1a1a1a` (they render as opaque black rectangles behind every element in PNG exports and most viewers)
- **Solid fills with light pastel backgrounds**: Use `fillStyle: "solid"` with light fill colors for readability
- **Dark borders + light fills**: e.g. stroke `#1e40af`, background `#dbeafe`
- **Hand-drawn roughness**: `roughness: 1` for organic feel
- **Monospace headers**: `fontFamily: 3` for titles, `fontFamily: 1` for body
- **Typography**: Title 48-60px, Section 32-36px, Body 16-20px
- **Stroke width**: 3-4px main borders, 2px secondary
- **Opacity**: 100 for shapes, 100 for text (full opacity for clean PNG export)

**Color Palette (dark borders / light pastel fills)**:
| Role | Border | Fill |
|------|--------|------|
| Blue (API/Services) | `#1e40af` | `#dbeafe` |
| Orange (Data) | `#b45309` | `#fef3c7` |
| Red (Security) | `#b91c1c` | `#fee2e2` |
| Purple (Processing) | `#6d28d9` | `#ede9fe` |
| Cyan (Output) | `#0e7490` | `#cffafe` |
| Green (Success) | `#047857` | `#d1fae5` |

**Text Colors**: Titles `#1e3a5f` (dark navy), Labels `#111827` (near black), Details `#6b7280` (gray)

### 5. **Advanced Features**
- Element grouping (`groupIds`)
- Arrow binding to connect elements
- Multi-column layouts
- Legend/key generation
- Status indicators (✅, ⚠️, ❌, 🟡)

## Sequence Diagram Templates

The skill supports sequence diagrams for multi-actor interaction flows, based on proven patterns from the EAGLE eval page diagrams.

**Key Features:**
- Standard actor layout with color-coded boxes (User, UI, Supervisor, Skills, Storage)
- Phase grouping with colored backgrounds (Blue, Green, Orange, Purple, Red)
- Message types: user input, system actions, self-loops, return messages
- Consistent spacing: 200px actor gaps, 60px step height, 450px phase spacing

**Common Patterns:**
- Simple request-response flows
- Multi-phase workflows (Intake → Clarification → Determination → Document Generation)
- Skill invocation sequences (when user needs help)
- Quality check workflows (validation and review)

For detailed specifications, layout guidelines, and example patterns, see: `.claude/skills/excalidraw/templates/sequence-diagram.md`

## Concurrent Worker Pool Templates

The skill supports concurrent processing pipeline diagrams for visualizing worker pools, promise pools, and multi-step data flows.

**Key Features:**
- Zone-based layout separating Main Thread, Service Worker, and Worker areas
- Stacked queue visualization for task/item backlogs
- Promise Pool and Worker Pool ellipses showing concurrency
- Detailed worker internals with JS bindings and WASM modules
- Numbered pipeline steps (0-N) with annotations
- Decision diamonds for loop/branching logic
- Transfer mechanism annotations (ArrayBuffer, base64, etc.)

**Common Patterns:**
- Simple worker pipelines (Input → Queue → Pool → Worker → Output)
- Concurrent processing with external fetch (CDN/cache integration)
- WASM-based processing workers with subsetting
- Loop with decision points (Done? → Take next / Continue)

For detailed specifications, layout guidelines, and example patterns, see: `.claude/skills/excalidraw/templates/concurrent-worker-pool.md`

## Available Templates

The skill includes detailed templates for common diagram types. Reference these when generating diagrams:

### Sequence Diagrams
- **Location**: `.claude/skills/excalidraw/templates/sequence-diagram.md`
- **Use Case**: Multi-actor interaction flows, workflow sequences, system interactions
- **Features**: Actor color palette, phase grouping, message types, layout specifications
- **Source**: Based on EAGLE eval page diagrams (`eagle-plugin/diagrams/excalidraw/`)

### Concurrent Worker Pool / Pipeline
- **Location**: `.claude/skills/excalidraw/templates/concurrent-worker-pool.md`
- **Use Case**: Concurrent processing pipelines, worker pools, promise pools, multi-step data flows
- **Features**: Zone-based layout (Main Thread, Service Worker, Worker zones), stacked queue visualization, Promise/Worker pool ellipses, WASM worker internals, decision diamonds, numbered pipeline steps, transfer mechanism annotations
- **Source**: Extracted from Excalidraw+ SVG export glyphs subsetting diagram

### Adding New Templates

To add a new template:
1. Create a new markdown file in `.claude/skills/excalidraw/templates/`
2. Document the template structure, patterns, and specifications
3. Reference it in this section with a brief description
4. Include example use cases and implementation notes

**Template Structure:**
- Overview and use cases
- Element specifications (sizes, colors, positioning)
- Common patterns and examples
- Layout guidelines
- Implementation notes

## Input Formats

The skill accepts:

### 1. **Markdown Descriptions**
```markdown
Create a sequential flowchart showing:
- Session Start → User Prompt → Tool Execution → Stop
- Include service integration points
- Use green for start, red for stop
```

### 2. **YAML Specifications**
```yaml
diagram_type: architecture
title: "AWS Microservices Architecture"
layers:
  - name: "Load Balancer"
    services: ["ALB", "CloudFront"]
  - name: "Compute"
    services: ["ECS Fargate", "Lambda"]
  - name: "Storage"
    services: ["S3", "DynamoDB"]
```

### 3. **Existing Code/Docs**
```bash
# Point to files to analyze
@server/app/agentic_service.py
@README.md

# Skill extracts structure and generates diagram
```

### 4. **Expert Domain Context**
When used with an expert, the skill automatically adapts to:
- **Backend Expert**: Service architectures, tool dispatch flows, AWS integrations
- **Frontend Expert**: Component hierarchies, UI flows, state management
- **Deployment Expert**: CI/CD pipelines, infrastructure diagrams
- **Claude SDK Expert**: Session flows, subagent relationships, hook lifecycles
- **Any Expert**: Domain-specific visualizations based on context

## Output Format

### Obsidian Excalidraw Format (REQUIRED)

Files MUST use the Obsidian Excalidraw plugin format (NOT raw JSON). Raw JSON files will NOT render.

**Required structure:**
- YAML frontmatter: `excalidraw-plugin: parsed` and `tags: [excalidraw]`
- Text Elements section with `^element-id` anchors
- Drawing section wrapped in `%%` with json code block
- File extension: `.excalidraw.md` (NOT `.excalidraw` or `.excalidrawlib`)

**Viewing:** In Obsidian, open the note → **More options** (top-right) → **Switch to EXCALIDRAW VIEW**. Raw `.excalidraw` files do not render in Obsidian; open them at https://excalidraw.com. Full guide and file template: `.claude/skills/excalidraw/docs/viewing-excalidraw-diagrams.md`, `.claude/skills/excalidraw/templates/obsidian-excalidraw-template.md`.

### Library File Structure (for reference)
```json
{
  "type": "excalidrawlib",
  "version": 2,
  "source": "https://excalidraw.com",
  "libraryItems": [
    {
      "id": "unique-id",
      "status": "published",
      "created": 1732579800000,
      "name": "Diagram Title",
      "description": "Diagram description",
      "elements": [
        // Element array
      ]
    }
  ]
}
```

### Element Properties
Each element includes:
- `id`: Unique identifier
- `type`: rectangle, ellipse, arrow, text, line
- `x`, `y`: Position coordinates
- `width`, `height`: Dimensions
- `strokeColor`, `backgroundColor`: Colors
- `strokeWidth`, `roughness`: Style properties
- `fontSize`, `fontFamily`, `textAlign`: Text properties
- `groupIds`: Grouping (optional)
- `startBinding`, `endBinding`: Arrow connections (optional)

## File Storage Convention

All diagrams live under the canonical directory:

```
docs/architecture/diagrams/
├── excalidraw/          ← Claude-generated .excalidraw.md files (primary)
│   └── obsidian/        ← Obsidian-native .excalidraw files (imported from vault)
├── mermaid/             ← .mmd source files + rendered .png exports
└── exports/             ← PNG/SVG exports of excalidraw diagrams
```

**Plugin-specific diagrams** (use-case flows) remain in `eagle-plugin/diagrams/` since they ship with the plugin.

### Naming Convention

Follow the project artifact naming pattern:
```
{YYYYMMDD}-{HHMMSS}-arch-{slug}-v{N}.excalidraw.md
```

Examples:
- `20260226-161925-arch-cdk-stack-architecture-v1.excalidraw.md`
- `20260220-175116-arch-aws-architecture-v1.excalidraw.md`

### Where to Save New Diagrams

| Diagram type | Save to |
|-------------|---------|
| Architecture / infra | `docs/architecture/diagrams/excalidraw/` |
| Sequence / workflow | `docs/architecture/diagrams/excalidraw/` |
| Mermaid flowcharts | `docs/architecture/diagrams/mermaid/` |
| PNG exports | `docs/architecture/diagrams/exports/` |
| Plugin use-case flows | `eagle-plugin/diagrams/excalidraw/` |
| Obsidian vault imports | `docs/architecture/diagrams/excalidraw/obsidian/` |

### Current Inventory (36 excalidraw files)

- `docs/architecture/diagrams/excalidraw/` — 7 `.excalidraw.md` (Claude-generated architecture)
- `docs/architecture/diagrams/excalidraw/obsidian/` — 18 `.excalidraw` (Obsidian-native, imported)
- `docs/architecture/diagrams/exports/` — 2 `.excalidraw` + 3 `.png`
- `eagle-plugin/diagrams/excalidraw/` — 9 `.excalidraw` (UC01-UC09 use cases)
- `docs/architecture/diagrams/mermaid/` — 15 `.mmd` + 15 `.png` (mermaid renders)

## PNG Export (Required After Every Diagram)

After saving the `.excalidraw.md` file, **always export a PNG** alongside it. PNG files go into the `images/` subdirectory of the same project folder.

### Obsidian Vault Target

```
C:\Users\blackga\Desktop\eagle-obsidian\{author}\images\{stem}.png
```

The vault uses an author-namespaced layout to leave room for multiple contributors:
```
eagle-obsidian/
├── blackga-nih/          ← author namespace
│   ├── *.excalidraw.md
│   ├── *.png
│   └── images/
│       └── *.png
└── {other-author}/       ← future contributors
```

For example, for a diagram saved by `blackga-nih`:
```
C:\Users\blackga\Desktop\eagle-obsidian\blackga-nih\images\arch-cdk-stack-v1.png
```

### Export Pipeline

The Obsidian `.excalidraw.md` format uses `compressed-json` (LZ-string base64). Export to PNG using:

```
lz-string (decompression) → raw .excalidraw JSON → @tommywalkie/excalidraw-cli → PNG
```

**One-time setup** (already installed globally):
```bash
npm install -g @tommywalkie/excalidraw-cli
# lz-string lives at C:/tmp/excali-export/node_modules/lz-string
```

**Export script** (`C:/tmp/excali-export/export-pngs.js`):
```javascript
const LZString = require('lz-string');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Usage: node export-pngs.js <input_dir> <project_name>
// e.g.:  node export-pngs.js "C:/Users/blackga/Desktop/Gbautomation/excalidraw-diagrams/nci" nci

const INPUT_DIR = process.argv[2];
const PROJECT   = process.argv[3] || path.basename(INPUT_DIR);
const OUTPUT_DIR = path.join(
  'C:/Users/blackga/Desktop/Gbautomation/excalidraw-diagrams',
  PROJECT, 'images'
);
const TMP_DIR = 'C:/tmp/excali-export/tmp';

fs.mkdirSync(OUTPUT_DIR, { recursive: true });
fs.mkdirSync(TMP_DIR, { recursive: true });

const files = fs.readdirSync(INPUT_DIR).filter(f => f.endsWith('.excalidraw.md'));
console.log(`Exporting ${files.length} diagrams → ${OUTPUT_DIR}\n`);

for (const file of files) {
  const stem = file.replace('.excalidraw.md', '');
  const content = fs.readFileSync(path.join(INPUT_DIR, file), 'utf8');
  const m = content.match(/```compressed-json\n([\s\S]*?)\n```/);
  if (!m) { console.log(`⚠ ${stem}: no compressed-json block — skipped`); continue; }

  const json = LZString.decompressFromBase64(m[1].replace(/\n/g, ''));
  if (!json) { console.log(`⚠ ${stem}: decompression failed — skipped`); continue; }

  const excalidrawPath = path.join(TMP_DIR, stem + '.excalidraw');
  fs.writeFileSync(excalidrawPath, json);

  try {
    execSync(`excalidraw-cli "${stem}.excalidraw" .`, { cwd: TMP_DIR, stdio: 'inherit' });
    fs.copyFileSync(path.join(TMP_DIR, stem + '.png'), path.join(OUTPUT_DIR, stem + '.png'));
    console.log(`✓ ${stem}.png`);
  } catch (e) {
    console.log(`✗ ${stem}: ${e.message}`);
  }
}
console.log('\nDone.');
```

**Run after generating diagrams:**
```bash
node "C:/tmp/excali-export/export-pngs.js"
# defaults to eagle-obsidian/blackga-nih → images/ subfolder

# Other author:
node "C:/tmp/excali-export/export-pngs.js" \
  "C:/Users/blackga/Desktop/eagle-obsidian/other-author" other-author
```

### Notes
- Font warnings (`couldn't load font "Virgil"`) are cosmetic; install the [Virgil font](https://virgil.excalidraw.com) to fix
- PNGs are 1–2 MB at default scale; add `-s 2` flag to `excalidraw-cli` for 2× resolution
- The script auto-creates the `images/` subdirectory if it doesn't exist

## Knowledge Base

The skill has deep knowledge of:

### Excalidraw Technical Specs
- Element types and required properties
- Coordinate system (origin top-left)
- Color codes (hex format with #)
- Font families (1 = Virgil, 2 = Helvetica, 3 = Cascadia)
- Roughness values (0 = smooth, 1 = rough, 2 = very rough)
- Arrow binding mechanics
- Group management

### Layout Patterns
- Grid-based positioning (100px spacing standard)
- Vertical flow: Y increases downward
- Horizontal flow: X increases rightward
- Center alignment calculations
- Multi-column layouts
- Concentric circle positioning

### Color Palettes
Predefined palettes for common use cases:
- **AWS Colors**: Orange (#f08c00), Blue (#1971c2), Green (#2f9e44)
- **System Colors**: Green (#2f9e44), Purple (#7950f2), Orange (#f08c00), Cyan (#0c8599), Red (#c92a2a)
- **Compliance**: Purple (#5f3dc4), Blue (#1971c2)
- **Status Colors**: Success (#2f9e44), Warning (#f08c00), Error (#c92a2a), Info (#1971c2)

## Workflow Integration

### Simple Workflow
For straightforward diagrams:
1. Parse user request (or expert context)
2. Generate Excalidraw JSON
3. Save `.excalidraw.md` file
4. Provide import instructions

### Complex Workflow
For sophisticated multi-diagram sets:
1. **Plan**: Analyze requirements, determine diagram types needed
2. **Implement**: Generate multiple related diagrams
3. **Update**: Create documentation (README, import guide)
4. **Validate**: Check JSON validity, element positioning

## Expert Integration

This skill is designed to work seamlessly with any expert in `.claude/commands/experts/*`:

### Backend Expert
- Service architecture diagrams
- Tool dispatch flows
- AWS integration diagrams
- Tenant scoping visualizations

### Frontend Expert
- Component hierarchy trees
- UI flow diagrams
- State management flows
- User journey maps

### Deployment Expert
- CI/CD pipeline diagrams
- Infrastructure as code visualizations
- Environment deployment flows
- Rollback procedures

### Claude SDK Expert
- Session lifecycle diagrams
- Subagent relationship graphs
- Hook execution flows
- Tool use patterns

### CloudWatch Expert
- Log aggregation flows
- Metric collection diagrams
- Alert routing visualizations

### TAC Expert
- Support workflow diagrams
- Escalation paths
- Issue resolution flows

### Eval Expert
- Test execution flows
- Evaluation criteria trees
- Scoring methodology diagrams

## Example Use Cases

### 1. Backend Service Architecture
```bash
Input: @server/app/agentic_service.py
Output: docs/architecture/diagrams/excalidraw/20260303-143000-arch-agentic-service-v1.excalidraw.md
```

### 2. Frontend Component Hierarchy
```bash
Input: Create component tree for React app
Output: docs/architecture/diagrams/excalidraw/20260303-143000-arch-component-hierarchy-v1.excalidraw.md
```

### 3. Deployment Pipeline
```bash
Input: Show CI/CD workflow from commit to production
Output: docs/architecture/diagrams/excalidraw/20260303-143000-arch-ci-cd-pipeline-v1.excalidraw.md
```

### 4. Claude SDK Session Flow
```bash
Input: Visualize session lifecycle with subagents and hooks
Output: docs/architecture/diagrams/excalidraw/20260303-143000-arch-session-flow-v1.excalidraw.md
```

## Quality Standards

Generated diagrams must meet:

### Technical Quality
- ✅ Valid JSON structure
- ✅ All required properties present
- ✅ Unique element IDs
- ✅ Proper coordinate system
- ✅ Arrow bindings functional
- ✅ Obsidian Excalidraw format compliance

### Visual Quality
- ✅ No element overlap
- ✅ Consistent spacing
- ✅ Readable text (minimum 16px)
- ✅ Color contrast for accessibility
- ✅ Professional appearance

### Usability Quality
- ✅ Clear titles and labels
- ✅ Legend/key if needed
- ✅ Import instructions provided
- ✅ Template metadata accurate
- ✅ Documentation complete

## Error Handling

The skill handles:
- Invalid input specifications → Request clarification
- Complex layouts → Use multi-pass positioning
- Element overlap → Adjust spacing automatically
- Missing metadata → Use sensible defaults
- File conflicts → Append version numbers
- Expert context missing → Use generic domain-agnostic approach

## Usage Examples

### With Backend Expert
```
User: "Create a diagram showing the tool dispatch flow in agentic_service.py"
Expert: Uses backend expertise + excalidraw skill
Output: Visual diagram of TOOL_DISPATCH, execute_tool(), and handler flow
```

### With Frontend Expert
```
User: "Show me the component hierarchy for the React app"
Expert: Uses frontend expertise + excalidraw skill
Output: Component tree diagram with props flow
```

### With Deployment Expert
```
User: "Visualize the deployment pipeline"
Expert: Uses deployment expertise + excalidraw skill
Output: CI/CD flow diagram with stages and gates
```

### Standalone (No Expert)
```
User: "Create a flowchart for user authentication"
Skill: Uses generic diagram generation
Output: Authentication flow diagram
```

## Success Metrics

The skill is successful when:
- Diagram imports cleanly into Excalidraw web/Obsidian
- Visual layout is professional and clear
- All requested elements are present
- Colors and styling are consistent
- User can immediately use for presentation
- Expert context is appropriately reflected (if used with expert)

## Version History

### v1.0.0 (2025-02-11)
- Initial skill release
- Support for 5+ diagram types
- Expert-agnostic design
- Obsidian Excalidraw format support
- Integration with all experts in `.claude/commands/experts/*`

## Future Enhancements

Planned improvements:
- Interactive diagram editor mode
- Diagram diffing and updates
- Template inheritance
- Style guide enforcement
- Automatic color theme selection based on expert domain
- Multi-page diagram sets
- Export to PNG/SVG
- Expert-specific diagram templates
