# Concurrent Worker Pool / Pipeline Template

Based on the Excalidraw SVG export glyphs subsetting diagram (`https://link.excalidraw.com/readonly/8FvNqNc1JwFYLEO1TX2e`), this template provides a proven pattern for visualizing concurrent processing pipelines with worker pools, promise pools, and multi-step data flows.

## Template Structure

Concurrent worker pool diagrams follow this standard pattern:

1. **Title Area** - Section labels (20px font, bold) identifying major zones
2. **Processing Pipeline** - Numbered steps (1-N) showing data flow left-to-right or top-to-bottom
3. **Worker Pool Zone** - Grouped area showing concurrent workers with:
   - Promise pool ellipse (concurrency limiter)
   - Worker instances (stacked rectangles or ellipses)
   - Data queue visualization (stacked FontFace/item rectangles)
4. **External Service Zone** - Dashed boundary boxes for service workers, CDNs, caches
5. **Subset/Processing Worker** - Detailed internal view of a worker showing:
   - WASM bindings and JS bindings as sub-components
   - Processing steps annotated with letters (a, b, c)
6. **Decision Points** - Diamond shapes for branching logic (Done? Yes/No)
7. **Annotations** - Small text explaining transfer mechanisms, strategies, and edge cases

## Zone Layout

The diagram is organized into distinct horizontal/vertical zones:

```
+------------------------------------------------------------------+
|  Main Thread Zone (dashed border, transparent bg)                |
|                                                                   |
|  [Export API] --> [Data Queue] --> [Promise Pool] --> [Workers]   |
|      (green)      (stacked)       (yellow ellipse)   (pool area) |
|                                                                   |
+------------------------------------------------------------------+
                                         |
                              [Service Worker Zone]
                              (dashed border, white bg)
                                         |
                              [External CDN]
                                         |
+------------------------------------------------------------------+
|  Subset Worker Zone (dashed border, white bg)                    |
|                                                                   |
|  [Subset Chunk] with [JS bindings] + [WASM modules]             |
|      (pink bg)        (tan bg)        (blue bg)                  |
|                                                                   |
+------------------------------------------------------------------+
```

## Color Palette

Standard colors for concurrent processing diagrams:

### Component Colors
- **Export API / Entry Point**: Green (#b2f2bb)
- **Data Items (FontFace/tasks)**: Tan (#eaddd7) - stacked to show queue
- **Promise Pool / Concurrency Limiter**: Yellow (#fff9db, #ffec99)
- **Worker Pool Area**: Light purple (#f3f0ff)
- **Processing Chunk Container**: Pink/Red (#ffc9c9)
- **WASM Modules**: Light blue (#a5d8ff)
- **JS Bindings**: Tan (#eaddd7)
- **External Service Zone**: White (#ffffff) with dashed border
- **Main Thread Zone**: Transparent with dashed border
- **CDN / External**: Gray (#ced4da)
- **Decision Diamond**: Default stroke, no fill

### Stroke Colors
- **Primary connections**: Black (#1e1e1e), 1px width
- **Zone boundaries**: Black (#1e1e1e), dashed style
- **Data flow arrows**: Black (#1e1e1e), solid, with labels

## Step Numbering Convention

Steps are numbered sequentially to show the processing pipeline:

```
0. (Pre) fetch on scene init     - Pre-loading / warm-up step
1. Export to SVG                  - Entry point / trigger
2. Find FontFaces                - Discovery / enumeration
3. Iterate concurrently          - Concurrency initiation
4. Fetch woff2                   - External data retrieval
5. Init Worker                   - Worker instantiation
6. Send raw woff2                - Data transfer to worker
7. Subset font glyphs            - Core processing
8. Send subsetted woff2          - Return processed data
9. Encode woff2 as base64        - Post-processing
10a. Take next FontFace          - Loop continuation
10b. Continue in export process  - Loop exit / completion
11. Save generated SVG           - Final output
```

## Element Specifications

### Stacked Queue Visualization
Show a queue of items using slightly offset rectangles:
- Each item: 62x42px, background #eaddd7
- Offset: +5px X, +7px Y per item
- Stack 8-15 items to convey volume
- Label with item type (e.g., "FontFace")

### Promise Pool (Concurrency Limiter)
- Ellipse: 261x173px, background #fff9db
- Contains smaller ellipses for individual promises (#ffec99, 101x51px)
- Label: "Promise pool" (16px) with annotation about concurrency level
- Sub-label: "defines the concurrency by maintaining N concurrent promises" (9px)

### Worker Pool
- Ellipse: 261x173px, background #f3f0ff
- Contains smaller items for individual workers
- Label: "Worker pool" (16px)
- Sub-label: "reuses the same N workers" (9px)

### Processing Worker (Detailed View)
- Outer container: Dashed rectangle, white bg, 307x219px
- Inner chunk: Rectangle, pink bg (#ffc9c9), 242x141px
- JS binding boxes: 103x48px, tan bg (#eaddd7)
- WASM module boxes: 103x48px, blue bg (#a5d8ff)
- Arranged in 2x2 grid inside the chunk

### External Service Zone
- Dashed rectangle: 209x171px, transparent/white bg
- Contains service label (20px) and strategy annotation (9px)
- Example: "Service Worker" with "CacheFirst strategy"

### Decision Diamond
- Diamond shape for branching: ~50x50px
- Labels: "Done?" (10px)
- Two outgoing arrows: "Yes" and "No" branches

### Annotations
- Transfer mechanism notes: "transferred as ArrayBuffer" (9px, italic style)
- Strategy notes: "with CacheFirst strategy" (9px)
- Edge case notes: Smaller text (9px) explaining fallback behavior

## Arrow Patterns

### Data Flow (Numbered Steps)
- Solid arrows, 1px stroke, black (#1e1e1e)
- Label above arrow with step number and description (16px)
- Sub-label below for technical details (9px)

### Return Flow
- Solid arrows in reverse direction
- Label with step number

### Loop Flow
- Curved arrow from decision point back to iteration start
- "Take next" label

### Pre-fetch Flow
- Arrow from external zone to cache/CDN
- Dashed or solid depending on timing

## Common Patterns

### Pattern 1: Simple Worker Pipeline
```
[Input] --> [Queue] --> [Pool] --> [Worker] --> [Output]
```

### Pattern 2: Concurrent Processing with External Fetch
```
[Input] --> [Enumerate] --> [Promise Pool] --fetch--> [CDN/Cache]
                                |
                          [Worker Pool] --process--> [Return]
                                |
                          [Encode/Transform] --> [Output]
```

### Pattern 3: Worker with WASM Processing
```
[Raw Data] --> [Worker] --> [Subset Chunk]
                               |
                    [JS Bindings] + [WASM Modules]
                               |
                         [Processed Data]
```

### Pattern 4: Loop with Decision
```
[Start] --> [Process Item] --> [Done?]
                                 |
                          Yes ---+--> [Continue Export]
                          No ----+--> [Take Next Item] --> [Process Item]
```

## Layout Specifications

- **Zone spacing**: 100-200px vertical gap between major zones
- **Step spacing**: 150-250px horizontal between pipeline steps
- **Queue item offset**: 5px X, 7px Y per stacked item
- **Worker pool diameter**: ~260px
- **Annotation font**: 9-10px for technical details
- **Step label font**: 16px for numbered steps
- **Zone title font**: 20px for area labels
- **Overall canvas**: ~1700x1200px for a full pipeline diagram

## Usage Guidelines

When generating concurrent worker pool diagrams:
1. Identify the processing pipeline stages and number them sequentially
2. Use the zone layout to separate Main Thread, Service Worker, and Worker areas
3. Show concurrency with Promise Pool and Worker Pool ellipses
4. Visualize queues with stacked offset rectangles
5. Detail worker internals with nested component boxes
6. Annotate data transfer mechanisms (ArrayBuffer, base64, etc.)
7. Include decision points for loop logic
8. Add edge case annotations for fallback paths

## Implementation Notes

- All diagrams use Obsidian Excalidraw format (`.excalidraw.md`)
- Elements use unique IDs
- Arrow bindings use `startBinding` and `endBinding` properties
- Group related elements using `groupIds` (e.g., all items in a worker)
- Stacked queue items share a group for easy repositioning
- Use frames to define major zones if needed
- Zone boundaries use dashed strokeStyle

## Source Reference

- **Original**: Excalidraw+ SVG export glyphs subsetting diagram
- **Link**: `https://link.excalidraw.com/readonly/8FvNqNc1JwFYLEO1TX2e`
- **Raw template**: `svg-export-glyphs-subsetting.excalidraw` (155 elements, 181KB)
- **Element breakdown**: 47 rectangles, 69 text labels, 12 arrows, 12 ellipses, 11 lines, 2 images, 1 diamond, 1 frame
