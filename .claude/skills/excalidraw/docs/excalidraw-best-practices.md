# Excalidraw Best Practices Guide
## Based on Cole's Context Engineering Framework (Updated for Light Theme)

**Version:** 2.0
**Date:** March 2026
**Reference:** Cole's visual design patterns, updated for clean PNG export

---

## CRITICAL: Light Canvas Only

**NEVER use dark backgrounds (`#1a1a1a`).** Dark canvas backgrounds render as opaque black rectangles behind every element in PNG exports, Obsidian preview, and most embedded viewers. Always use `#ffffff` (white) or `transparent`.

---

## Core Design Principles

### 1. **Light Canvas, Dark Borders, Pastel Fills**
- Canvas background: `#ffffff` (white) or `transparent`
- **Dark borders** with **light pastel fills**
- Use `fillStyle: "solid"` with light pastel colors for clean rendering
- Colors are for **differentiation**, not decoration

### 2. **Solid Fills Over Hachure**
- **Prefer** `fillStyle: "solid"` with light pastel backgrounds — renders cleanly in all viewers
- `fillStyle: "hachure"` is acceptable for emphasis boxes but not the default
- Hachure on dark fills creates visual noise in PNG exports

### 3. **Typography Hierarchy**
```
Title:        48-60px, Monospace, Dark Navy (#1e3a5f)
Section:      32-36px, Monospace, Color-coded (dark shade)
Subsection:   24-28px, Helvetica, Dark gray (#374151)
Body:         16-20px, Helvetica, Gray (#4b5563)
Details:      14-16px, Helvetica, Muted (#6b7280)
```

---

## Shape Guidelines

### **Rectangles**
```javascript
{
  type: "rectangle",
  strokeColor: "#1e40af",           // Dark blue border
  backgroundColor: "#dbeafe",       // Light blue fill
  fillStyle: "solid",               // Clean solid fill
  strokeWidth: 2,
  roughness: 1,                     // Hand-drawn feel
  opacity: 100                      // Full opacity for clean export
}
```

### **Ellipses**
```javascript
{
  type: "ellipse",
  strokeColor: "#047857",           // Dark green border
  backgroundColor: "#d1fae5",       // Light green fill
  fillStyle: "solid",
  strokeWidth: 3,
  roughness: 1,
  opacity: 100
}
```

### **Rounded Rectangles**
- Use for **interactive elements** or **buttons**
- Add `roundness: { type: 3 }` for rounded corners
- Same light fill pattern

---

## Color Palette

### **Border Colors (Dark)**
```
Blue:     #1e40af  (API, Services)
Orange:   #b45309  (Data, Retrieval)
Red:      #b91c1c  (Security, Critical)
Purple:   #6d28d9  (Processing, Context)
Cyan:     #0e7490  (Generation, Output)
Green:    #047857  (Success, Complete)
```

### **Fill Colors (Light Pastels)**
```
Blue:     #dbeafe
Orange:   #fef3c7
Red:      #fee2e2
Purple:   #ede9fe
Cyan:     #cffafe
Green:    #d1fae5
Yellow:   #fef9c3  (warnings, notes)
```

### **Text Colors**
```
Title:    #1e3a5f  (Dark navy, monospace)
Labels:   #111827  (Near black)
Body:     #374151  (Dark gray)
Details:  #6b7280  (Medium gray)
Muted:    #9ca3af  (Light gray)
```

---

## Layout Patterns

### **Pattern 1: Layered Architecture (Top-to-Bottom)**
```
Purpose: Show system layers
Layout:  Full-width boxes stacked vertically
Spacing: 40-60px between layers
Colors:  Different pastel per layer
Arrows:  Vertical flow between layers
```

### **Pattern 2: Side-by-Side Comparison**
```
Purpose: Compare parallel components
Layout:  Equal-width boxes in a row
Spacing: 40-60px gap
Colors:  Matching border colors, different fills
```

### **Pattern 3: Flow Diagram**
```
Purpose: Show sequential process
Layout:  Shapes connected by arrows
Spacing: 100-150px between elements
Colors:  Consistent palette, arrows in dark gray
```

### **Pattern 4: Information Panels**
```
Purpose: Summary stats or test matrices
Layout:  Equal-width rectangles in a row at bottom
Height:  200-300px
Width:   400-500px each
Gap:     40px between boxes
```

---

## Text Best Practices

### **Monospace for Headers**
```javascript
{
  fontFamily: 3,  // Monospace (Cascadia)
  fontSize: 48,
  strokeColor: "#1e3a5f"  // Dark navy
}
```

### **Helvetica for Body**
```javascript
{
  fontFamily: 1,  // Helvetica
  fontSize: 16,
  strokeColor: "#374151"  // Dark gray
}
```

### **Bullet Points**
```
• Use bullet points (not dashes)
• Keep lines short (40-50 chars max)
• Dark text on light background for readability
```

---

## Arrow Guidelines

### **Style**
```javascript
{
  type: "arrow",
  strokeColor: "#374151",  // Dark gray (neutral)
  strokeWidth: 2,
  roughness: 1,
  endArrowhead: "arrow",
  startArrowhead: null
}
```

### **Usage**
- **Straight arrows**: Sequential steps
- **Color**: Dark gray for most, match source color for emphasis
- **Width**: 2-3px for main flow, 1-2px for secondary
- **Labels**: Add text elements near arrows for data flow labels

---

## Do's

- Use **white or transparent canvas** background
- Use **solid fills** with **light pastel** colors
- Use **dark borders** for contrast against light fills
- Use **dark text** (#111827 or #374151) for readability
- Use **monospace** for titles and headers
- Add **roughness: 1** for hand-drawn aesthetic
- Use **opacity: 100** for clean PNG export
- Group related elements with **similar colors**
- Keep **spacing consistent** (40-100px gaps)

---

## Don'ts

- **NEVER** use dark canvas backgrounds (`#1a1a1a`, `#000000`, etc.)
- **NEVER** use dark fills with light/white text (hard to read in exports)
- Don't use too many **different colors** (5-6 max)
- Don't make **text too small** (<14px)
- Avoid **cluttered layouts** (whitespace is good)
- Don't use **hachure fills as default** — use solid with light pastels
- Don't use **low opacity** (<80) — causes washed-out exports

---

## Sizing Reference

```
Canvas Background:  #ffffff (white) or transparent — NEVER dark

Title Text:         48-60px
Section Headers:    32-36px
Labels:             24-28px
Body Text:          16-20px
Details:            14-16px

Rectangles:
  - Width:  400-600px
  - Height: 200-350px

Spacing:
  - Between elements: 40-100px
  - Text padding:     20-30px
  - Arrow gaps:       30-50px

Stroke Width:
  - Main borders:     2-3px
  - Secondary:        1-2px
  - Arrows:           2-3px
```

---

## Complete Element Example

```javascript
{
  "type": "rectangle",
  "id": "unique-id",
  "x": 200,
  "y": 200,
  "width": 500,
  "height": 300,
  "angle": 0,
  "strokeColor": "#1e40af",        // Dark blue border
  "backgroundColor": "#dbeafe",    // Light blue fill
  "fillStyle": "solid",            // SOLID, not hachure
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,                  // Full opacity
  "seed": 123456,
  "version": 1,
  "versionNonce": 1,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [],
  "updated": 1,
  "link": null,
  "locked": false
}
```

---

## Quick Start Template

### **Basic Diagram Structure**
```
1. Canvas: White background (#ffffff)
2. Title: Dark navy monospace, 48px, top center
3. Main Elements: 3-5 shapes with solid light pastel fills
4. Labels: Dark text inside shapes
5. Details: Gray body text below labels
6. Arrows: Dark gray (#374151) connecting flow
7. Footer: Gray text with summary
8. Info Boxes: 2-4 rectangles at bottom
```

### **Color Assignment Strategy**
```
API/Services:    Blue    border #1e40af  fill #dbeafe
Data/Retrieval:  Orange  border #b45309  fill #fef3c7
Security:        Red     border #b91c1c  fill #fee2e2
Processing:      Purple  border #6d28d9  fill #ede9fe
Output/Generate: Cyan    border #0e7490  fill #cffafe
Success/Done:    Green   border #047857  fill #d1fae5
Warnings/Notes:  Yellow  border #a16207  fill #fef9c3
```

---

**Document Version:** 2.0
**Updated:** March 2026
**Change:** Replaced dark canvas + hachure with white canvas + solid light pastels for clean PNG/viewer rendering
**Style Guide For:** Technical diagrams, architecture docs, process flows
