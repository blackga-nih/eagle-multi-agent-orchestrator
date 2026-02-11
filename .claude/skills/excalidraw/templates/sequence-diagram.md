# Sequence Diagram Template

Based on the EAGLE eval page sequence diagrams (`eagle-plugin/diagrams/excalidraw/`), this template provides a proven pattern for multi-actor interaction flows.

## Template Structure

Sequence diagrams follow this standard pattern:

1. **Title** - Centered text at top (32px font, bold)
2. **Actors** - Rectangular boxes (180px width, 60px height) with:
   - Distinct background colors per actor type
   - Centered text labels (16px font)
   - Positioned horizontally with 200px spacing
3. **Lifelines** - Dashed vertical lines (1px stroke, #495057 color) extending from each actor
4. **Messages** - Horizontal arrows between actors:
   - Solid arrows for synchronous messages
   - Dashed arrows for asynchronous/return messages
   - Text labels above arrows (14px font)
   - Arrow width: 2px, color: #1e1e1e
5. **Self-loops** - Curved arrows for internal processing (80px width, 30px height)
6. **Phase Backgrounds** - Colored rectangles grouping related steps:
   - Phase 1 (Minimal Intake): Blue (#339af0, opacity 60%)
   - Phase 2 (Clarifying Questions): Green (#2f9e44, opacity 60%)
   - Phase 3 (Determination): Orange (#f08c00, opacity 60%)
   - Phase 4 (Document Generation): Purple (#9c36b5, opacity 60%)
   - Special phases (Skill Invocation): Red (#c92a2a) or Orange (#f08c00)
7. **Notes** - Yellow/colored rectangles with explanatory text (13px font)

## Actor Color Palette

Standard actor colors for consistency:
- **User/COR**: Blue (#4a90d9)
- **UI/Frontend**: Purple (#7b68ee)
- **Supervisor Agent**: Green (#50c878)
- **OA Intake Skill**: Red (#ff6b6b)
- **Document Generator Skill**: Orange (#ffa500)
- **Compliance Skill**: Gold (#daa520)
- **Tech Review Skill**: Teal (#20b2aa)
- **Storage/S3**: Gray (#808080)

## Message Types

1. **User Input** - Quoted text in messages (e.g., `"I need to buy lab equipment"`)
2. **System Actions** - Action descriptions (e.g., "New session created", "Delegate to OA Intake")
3. **Self-Processing** - Self-loops with internal logic (e.g., "Detect intent: acquisition request")
4. **Return Messages** - Dashed arrows with "Answers" or result labels
5. **Asynchronous** - Dashed arrows for non-blocking operations

## Phase Grouping Pattern

Phases are visually grouped with:
- Background rectangle spanning all actors
- Phase title in top-left (20px font, bold)
- Consistent vertical spacing (450px per phase)
- Color-coded borders matching phase theme

## Example Sequence Patterns

### Pattern 1: Simple Request-Response
```
User → UI: "Request"
UI → Supervisor: Route request
Supervisor → Skill: Delegate
Skill → UI: Response
UI → User: Display
```

### Pattern 2: Multi-Phase Workflow
```
Phase 1: Initial Intake
  User → UI → Supervisor → Intake Skill
  [Questions and answers]
  
Phase 2: Clarification
  Intake → UI → User
  [Follow-up questions]
  
Phase 3: Determination
  Intake → Supervisor: Decision
  Supervisor → UI: Summary
  
Phase 4: Document Generation
  User → UI → Supervisor → DocGen
  DocGen → S3: Store
  S3 → UI: URL
  UI → User: Download link
```

### Pattern 3: Skill Invocation (Red Phase)
When user needs help or system invokes additional skills:
```
User: "I don't know"
Intake → Supervisor: User lacks info
Supervisor → Compliance Skill: Invoke
Compliance → KB: Search
KB → Compliance: Results
Compliance → Supervisor: Present options
Supervisor → UI → User: Display
```

### Pattern 4: Quality Check (Orange Phase)
When system performs validation:
```
DocGen → Supervisor: Draft ready
Supervisor → Tech Review: Invoke
Tech Review → [Internal check]
Tech Review → Supervisor: Findings
Supervisor → DocGen: Update needed
DocGen → S3: Store v2
```

## Layout Specifications

- **Actor spacing**: 200px horizontal gap
- **Step height**: 60px vertical spacing between messages
- **Lifeline length**: Extends to bottom of last phase
- **Arrow positioning**: 20px above message text
- **Phase padding**: 10px margin inside phase rectangles
- **Note positioning**: Below relevant messages, 280px width

## Template Files Reference

Source templates available in `eagle-plugin/diagrams/excalidraw/`:
- `uc01-new-acquisition-happy-path.excalidraw` - Standard 4-phase workflow
- `uc01-complex-agent-subrouting.excalidraw` - Multi-skill invocation pattern
- `uc02-micro-purchase.excalidraw` - Simplified flow for small purchases
- `uc03-option-exercise.excalidraw` - Contract option workflow
- `uc04-contract-modification.excalidraw` - Modification request flow
- `uc05-co-package-review.excalidraw` - Review and approval process
- `uc07-contract-closeout.excalidraw` - Closeout workflow
- `uc08-shutdown-notification.excalidraw` - Notification sequence
- `uc09-score-consolidation.excalidraw` - Scoring and consolidation

## Usage Guidelines

When generating sequence diagrams for eval/test scenarios:
1. Reference the template patterns above
2. Use consistent actor colors and spacing
3. Group related steps into phases with colored backgrounds
4. Include self-loops for internal processing
5. Add notes for important clarifications
6. Follow the message labeling conventions

## Implementation Notes

- All diagrams use Obsidian Excalidraw format (`.excalidraw.md`)
- Elements must have unique IDs
- Arrow bindings use `startBinding` and `endBinding` properties
- Phase backgrounds use `groupIds` for visual grouping
- Text elements use `containerId` to bind to rectangles
