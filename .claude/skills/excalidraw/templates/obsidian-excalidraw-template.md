# Obsidian Excalidraw file template

Use this structure so the diagram **renders in Obsidian**: open the note → **More options** (top-right) → **Switch to EXCALIDRAW VIEW**.

---

Required structure:

1. **YAML frontmatter** (first line `---`, then):
   - `excalidraw-plugin: parsed`
   - `tags: [excalidraw]`
   - closing `---`

2. **Section** `# Text Elements`  
   One line per text element: `Display text ^element-id`  
   The `element-id` must match the `id` of the corresponding element in the JSON.

3. **Drawing block**  
   - Line: `%%`  
   - Line: `# Drawing`  
   - Fenced code block: ` ```json ` then the full Excalidraw JSON, then ` ``` `  
   - Line: `%%`

4. **File extension**: `.excalidraw.md`

---

## Minimal example (copy and replace JSON as needed)

```text
---
excalidraw-plugin: parsed
tags: [excalidraw]
---

# Text Elements

Diagram title ^title

%%
# Drawing
```json
{"type":"excalidraw","version":2,"source":"https://excalidraw.com","elements":[{"id":"title","type":"text","x":100,"y":20,"width":200,"height":32,"text":"Diagram title","fontSize":24,"fontFamily":3,"textAlign":"left","baseline":20,"strokeColor":"#10b981","backgroundColor":"transparent","fillStyle":"solid","strokeWidth":2,"roughness":1,"opacity":100,"seed":1,"version":1,"versionNonce":1,"isDeleted":false,"boundElements":null,"updated":1,"link":null,"locked":false,"containerId":null,"originalText":"Diagram title","lineHeight":1.25}],"appState":{"viewBackgroundColor":"#1a1a1a"},"files":{}}
```
%%
```

---

Full viewing instructions: `.claude/skills/excalidraw/docs/viewing-excalidraw-diagrams.md`
