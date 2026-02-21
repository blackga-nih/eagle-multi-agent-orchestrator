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
- **Dark canvas background**: `#1a1a1a` (NOT white)
- **Hachure fills**: Always use `fillStyle: "hachure"` (NOT solid) for shapes
- **Bright borders + dark fills**: e.g. stroke `#3b82f6`, background `#1e3a8a`
- **Hand-drawn roughness**: `roughness: 1` for organic feel
- **Monospace headers**: `fontFamily: 3` for titles, `fontFamily: 1` for body
- **Typography**: Title 48-60px, Section 32-36px, Body 16-20px
- **Stroke width**: 3-4px main borders, 2px secondary
- **Opacity**: 70-90 for subtle layering

**Color Palette (bright borders / dark fills)**:
| Role | Border | Fill |
|------|--------|------|
| Blue (API/Services) | `#3b82f6` | `#1e3a8a` |
| Orange (Data) | `#f59e0b` | `#92400e` |
| Red (Security) | `#ef4444` | `#7f1d1d` |
| Purple (Processing) | `#8b5cf6` | `#4c1d95` |
| Cyan (Output) | `#06b6d4` | `#164e63` |
| Green (Success) | `#10b981` | `#064e3b` |

**Text Colors**: Titles `#10b981` (green monospace), Labels `#ffffff`, Details `#6b7280`

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

All excalidraw files should be saved in:

```
{workspace_root}/docs/excalidraw-diagrams/{context}/*.excalidraw.md
```

Where `{context}` represents the context-specific subdirectory based on:
- Current project/workspace name
- Expert domain (e.g., `backend`, `frontend`, `deployment`)
- Feature or component being visualized

### Examples
- `docs/excalidraw-diagrams/backend/agentic-service-architecture.excalidraw.md`
- `docs/excalidraw-diagrams/frontend/component-hierarchy.excalidraw.md`
- `docs/excalidraw-diagrams/deployment/ci-cd-pipeline.excalidraw.md`
- `docs/excalidraw-diagrams/claude-sdk/session-flow.excalidraw.md`

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
Output: docs/excalidraw-diagrams/backend/agentic-service-architecture.excalidraw.md
```

### 2. Frontend Component Hierarchy
```bash
Input: Create component tree for React app
Output: docs/excalidraw-diagrams/frontend/component-hierarchy.excalidraw.md
```

### 3. Deployment Pipeline
```bash
Input: Show CI/CD workflow from commit to production
Output: docs/excalidraw-diagrams/deployment/ci-cd-pipeline.excalidraw.md
```

### 4. Claude SDK Session Flow
```bash
Input: Visualize session lifecycle with subagents and hooks
Output: docs/excalidraw-diagrams/claude-sdk/session-flow.excalidraw.md
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
