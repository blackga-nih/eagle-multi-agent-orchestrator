# Viewing Excalidraw Diagrams

This repo has two Excalidraw file formats. Only one renders inside Obsidian; both can be viewed on the web.

---

## 1. Obsidian (`.excalidraw.md` files)

**Files that render in Obsidian** use the **Obsidian Excalidraw plugin** format: extension `.excalidraw.md`, frontmatter `excalidraw-plugin: parsed` and `tags: [excalidraw]`, plus a "Text Elements" section and a drawing block in `%%` with JSON.

### How to render in Obsidian

1. Open the `.excalidraw.md` note in Obsidian.
2. In the **top-right of the document**, open **More options** (⋯ or "More options" menu).
3. Choose **Switch to EXCALIDRAW VIEW** (or "Excalidraw" view).
4. The canvas will render; you can pan, zoom, and edit.

If you only see markdown and a JSON block, you are in normal editor view — switch to Excalidraw view as above.

### Where the renderable diagrams are

| Location | Format | Renders in Obsidian? |
|----------|--------|----------------------|
| `docs/architecture/*.excalidraw.md` | Obsidian | ✅ Yes (use EXCALIDRAW VIEW) |
| `docs/excalidraw-diagrams/aws/*.excalidraw.md` | Obsidian | ✅ Yes |
| `docs/architecture/diagrams/excalidraw/obsidian/*.excalidraw` | Raw JSON | ❌ No |
| `eagle-plugin/diagrams/excalidraw/*.excalidraw` | Raw JSON | ❌ No |
| `docs/excalidraw-diagrams/exports/*.excalidraw` | Raw JSON | ❌ No |

---

## 2. Excalidraw.com (any `.excalidraw` or JSON)

**Raw `.excalidraw`** files (and the JSON inside `.excalidraw.md`) can be opened in the web app:

1. Go to **https://excalidraw.com**.
2. **Open**: use the menu (hamburger or "Open") → **Open from file** and select a `.excalidraw` file, **or** paste the diagram JSON into the app (e.g. from the drawing block of a `.excalidraw.md` file).
3. Optional: **Share** → "Export to link" gives a `https://excalidraw.com/#json=...` URL you can bookmark or share.

So: **all diagrams can be viewed** — Obsidian for `.excalidraw.md` (with EXCALIDRAW VIEW), excalidraw.com for raw `.excalidraw` or copied JSON.

---

## 3. File template (renderable in Obsidian)

To generate diagrams that render in Obsidian, use the structure in `.claude/skills/excalidraw/templates/obsidian-excalidraw-template.md`. Summary:

- YAML frontmatter: `excalidraw-plugin: parsed` and `tags: [excalidraw]`.
- Section `# Text Elements` with lines like `Label text ^element-id`.
- Block: `%%` then `# Drawing` then ` ```json ` and the Excalidraw JSON, then ` ``` `.
- File extension: `.excalidraw.md`.

Raw JSON-only files (e.g. many under `docs/architecture/diagrams/excalidraw/obsidian/` and `eagle-plugin/diagrams/excalidraw/`) do **not** render in Obsidian; open those in excalidraw.com or convert them to the Obsidian format using the template.
