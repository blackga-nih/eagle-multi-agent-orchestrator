# Excalidraw Best Practices Guide
## Based on Cole's Context Engineering Framework

**Version:** 1.0  
**Date:** October 20, 2025  
**Reference:** Cole's visual design patterns for technical documentation

---

## 🎨 Core Design Principles

### 1. **Minimal Color Philosophy**
- Use **dark backgrounds** (#1a1a1a or similar) for canvas
- **Bright borders** with **dark/transparent fills**
- Avoid solid colored backgrounds - use **cross-hatching (hachure)** instead
- Colors are for **differentiation**, not decoration

### 2. **Cross-Hatching Over Solid Fills**
- **Always prefer** `fillStyle: "hachure"` (cross-hatched pattern)
- Use `fillStyle: "cross-hatch"` for denser patterns
- Avoid `fillStyle: "solid"` except for text boxes
- This creates visual interest without overwhelming the viewer

### 3. **Typography Hierarchy**
```
Title:        48-60px, Monospace, Green (#10b981)
Section:      32-36px, Monospace, Color-coded
Subsection:   24-28px, Helvetica, White/Light
Body:         16-20px, Helvetica, Gray/Light
Details:      14-16px, Helvetica, Muted color
```

---

## 🔵 Shape Guidelines

### **Circles/Ellipses**
```javascript
{
  type: "ellipse",
  strokeColor: "#3b82f6",           // Bright border
  backgroundColor: "#1e3a8a",       // Dark fill
  fillStyle: "hachure",             // Cross-hatching!
  strokeWidth: 3,
  roughness: 1,                     // Hand-drawn feel
  opacity: 85                       // Slightly transparent
}
```

**Best For:**
- Concept groupings (Memory, RAG, Task Management)
- Overlapping Venn diagrams
- Process nodes in workflows

### **Rectangles**
```javascript
{
  type: "rectangle",
  strokeColor: "#dc2626",
  backgroundColor: "#450a0a",       // Very dark, not solid
  fillStyle: "hachure",
  strokeWidth: 2,
  roughness: 1,
  opacity: 70
}
```

**Best For:**
- Container boxes
- Information panels
- Step-by-step guides
- Code/text content areas

### **Rounded Rectangles**
- Use for **interactive elements** or **buttons**
- Use for **tool/service names**
- Add `roundness: { type: 3 }` for rounded corners

---

## 🎨 Color Palette

### **Primary Colors** (Bright Borders)
```
Blue:     #3b82f6  (Auth, API, Services)
Orange:   #f59e0b  (Data, Retrieval)
Red:      #ef4444  (Security, Critical)
Purple:   #8b5cf6  (Processing, Context)
Cyan:     #06b6d4  (Generation, Output)
Green:    #10b981  (Success, Complete)
```

### **Background Colors** (Dark Fills with Hachure)
```
Blue:     #1e3a8a
Orange:   #92400e
Red:      #7f1d1d / #450a0a
Purple:   #4c1d95
Cyan:     #164e63
Green:    #064e3b / #065f46
```

### **Text Colors**
```
Title:    #10b981  (Green monospace)
White:    #ffffff  (Primary labels)
Light:    #bfdbfe, #fde68a, #fecaca, etc. (Muted versions)
Gray:     #6b7280  (Subtle info)
```

---

## 📐 Layout Patterns

### **Pattern 1: Overlapping Circles (Venn)**
Used by Cole for "Context Engineering" diagram

```
Purpose: Show relationships between concepts
Layout:  3-5 circles with 20-30% overlap
Colors:  Different color per circle
Fill:    hachure with dark background
Text:    White titles, colored details
```

**Example:**
- RAG (blue)
- Memory (orange) 
- Task Management (red)
- Prompt Engineering (green)

### **Pattern 2: Vertical Pipeline**
Left-to-right or top-to-bottom flow

```
Purpose: Show sequential process
Layout:  Shapes connected by arrows
Spacing: 100-150px between elements
Colors:  Progress from cool (blue) to warm (red/green)
```

### **Pattern 3: Information Panels**
Bottom section with 2-4 boxes

```
Purpose: Summary stats or metrics
Layout:  Equal-width rectangles in a row
Height:  250-300px
Width:   400-500px each
Gap:     50px between boxes
```

---

## 🖊️ Text Best Practices

### **1. Monospace for Headers**
```javascript
{
  fontFamily: 3,  // Monospace
  fontSize: 48,
  strokeColor: "#10b981"
}
```

### **2. Helvetica for Body**
```javascript
{
  fontFamily: 1,  // Helvetica
  fontSize: 16,
  strokeColor: "#ffffff"
}
```

### **3. Bullet Points**
```
• Use bullet points (not dashes)
• Keep lines short (40-50 chars max)
• Use color-coded text matching container
```

### **4. Hierarchical Information**
```
Title (bold/large)
  • Detail 1 (smaller)
  • Detail 2 (smaller)
  • Detail 3 (smaller)
```

---

## ➡️ Arrow Guidelines

### **Style**
```javascript
{
  type: "arrow",
  strokeColor: "#dc2626",  // Match theme
  strokeWidth: 3,          // Thick for visibility
  roughness: 1,
  endArrowhead: "arrow",
  startArrowhead: null
}
```

### **Usage**
- **Straight arrows**: Sequential steps
- **Curved arrows**: Feedback loops
- **Color**: Match source or destination color
- **Width**: 3-4px for main flow, 2px for secondary

---

## 🎯 Common Patterns from Cole's Framework

### **1. Vibe Plan Box**
```
Shape:  Rounded rectangle
Border: Blue (#3b82f6)
Fill:   Transparent or very light hachure
Text:   White monospace
Size:   600-700px wide × 100-120px tall
```

### **2. Context Engineering Circles**
```
Count:  4-5 overlapping circles
Size:   300-400px diameter
Stroke: 3px, bright colors
Fill:   hachure, dark backgrounds
Labels: White text, centered
```

### **3. Tool Boxes**
```
Shape:  Rounded rectangles
Size:   250px × 80px
Layout: Grid (2×2 or 3×2)
Border: Blue
Fill:   Transparent
Text:   Centered, white
```

### **4. Info Sections**
```
Shape:  Rectangle (not rounded)
Border: 2-3px, colored
Fill:   hachure, dark matching color
Text:   Title (monospace) + bullets (helvetica)
Size:   400-500px wide
```

---

## ✅ Do's

✓ Use **hachure** fill style for visual texture  
✓ Keep backgrounds **dark** with **bright borders**  
✓ Use **monospace** for titles and headers  
✓ Make text **white or light colored** for readability  
✓ Add **roughness: 1** for hand-drawn aesthetic  
✓ Use **opacity: 70-90** for subtle layering  
✓ Group related elements with **similar colors**  
✓ Add **arrows** to show flow and relationships  
✓ Keep **spacing consistent** (50-100px gaps)  
✓ Use **emojis sparingly** for visual markers  

---

## ❌ Don'ts

✗ Avoid **solid fills** on large shapes  
✗ Don't use too many **different colors** (5-6 max)  
✗ Avoid **pure black backgrounds** (use #1a1a1a)  
✗ Don't make **text too small** (<14px)  
✗ Avoid **cluttered layouts** (whitespace is good)  
✗ Don't use **system fonts** (stick to Helvetica/Monospace)  
✗ Avoid **perfectly straight lines** (roughness adds character)  
✗ Don't **over-explain** in text (keep it concise)  

---

## 📏 Sizing Reference

```
Canvas Background:  #1a1a1a (dark gray, not black)

Title Text:         48-60px
Section Headers:    32-36px
Labels:             24-28px
Body Text:          16-20px
Details:            14-16px

Large Circles:      400-500px diameter
Medium Circles:     300-400px diameter
Small Circles:      200-250px diameter

Rectangles:         
  - Width:  400-600px
  - Height: 250-350px

Spacing:
  - Between elements: 50-100px
  - Text padding:     20-30px
  - Arrow gaps:       30-50px

Stroke Width:
  - Main borders:     3-4px
  - Secondary:        2px
  - Arrows:           3-4px
```

---

## 🎨 Complete Element Example

```javascript
{
  "type": "ellipse",
  "id": "unique-id",
  "x": 200,
  "y": 200,
  "width": 400,
  "height": 400,
  "angle": 0,
  "strokeColor": "#3b82f6",        // Bright blue border
  "backgroundColor": "#1e3a8a",    // Dark blue background
  "fillStyle": "hachure",          // CROSS-HATCHING!
  "strokeWidth": 3,
  "strokeStyle": "solid",
  "roughness": 1,                  // Hand-drawn look
  "opacity": 85,                   // Slightly see-through
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

## 📝 Quick Start Template

### **Basic Diagram Structure**
```
1. Canvas: Dark background (#1a1a1a)
2. Title: Green monospace, 48px, top center
3. Main Elements: 3-5 shapes with hachure fills
4. Labels: White text inside shapes
5. Details: Colored bullets below labels
6. Arrows: Connect flow between elements
7. Footer: Gray text with pipeline summary
8. Info Boxes: 2-4 rectangles at bottom
```

### **Color Assignment Strategy**
```
Authentication:  Blue (#3b82f6)
Data/Retrieval:  Orange (#f59e0b)
Security:        Red (#ef4444)
Processing:      Purple (#8b5cf6)
Output/Generate: Cyan (#06b6d4)
Success/Done:    Green (#10b981)
```

---

## 🔍 Troubleshooting

### **Problem: Shapes look flat**
- **Solution:** Use `fillStyle: "hachure"` instead of `"solid"`
- Add `roughness: 1` for texture

### **Problem: Text is hard to read**
- **Solution:** Use white (#ffffff) text on dark backgrounds
- Increase font size to 18px minimum
- Use monospace for headers

### **Problem: Too much visual noise**
- **Solution:** Limit to 5-6 colors maximum
- Use dark fills with bright borders only
- Remove unnecessary elements

### **Problem: Diagram feels cramped**
- **Solution:** Increase spacing to 100px between major elements
- Make canvas larger (2000×1500px minimum)
- Group related items closer, separate unrelated items

---

## 📚 References

**Cole's Examples:**
- Context Engineering Venn diagram (4 overlapping circles)
- Steps to Planning (numbered list with boxes)
- Tool selection grids (rounded rectangles)

**Key Takeaways:**
1. **Hachure fills** create visual interest without overwhelming
2. **Dark backgrounds + bright borders** = high contrast
3. **Monospace titles** = professional, code-like aesthetic
4. **Minimal color** = focused, clear communication
5. **Hand-drawn roughness** = approachable, informal

---

**Document Version:** 1.0  
**Created:** October 20, 2025  
**Style Guide For:** Technical diagrams, architecture docs, process flows

