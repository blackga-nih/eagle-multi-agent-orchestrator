---
type: expert-file
file-type: skill
domain: document-playground
tags: [playground, document, html, acquisition, interactive, download]
description: "Creates interactive HTML document playgrounds -- self-contained single-file explorers for configuring and previewing NCI acquisition documents with live preview, prompt output, and download button."
---

# Document Playground Builder

> A document playground is a self-contained HTML file with document configuration controls on one side, a live NCI-branded document preview on the other, and a prompt output at the bottom with copy + download buttons. The user adjusts controls, previews the document visually, then either downloads the HTML or copies the generated prompt back into Claude.

## When to use this skill

- User asks to create, preview, or configure an acquisition document interactively
- User wants to visually configure document sections before generating
- User asks for an HTML document with download capability
- User asks for a document playground, document explorer, or document builder

## How to use this skill

1. **Identify the document type** from the user's request (SOW, IGCE, AP, J&A, MRR)
2. **Load the template** from `templates/acquisition-doc.md`
3. **Follow the template** to build the playground HTML file
4. **Pre-populate** with relevant content if the user provided intake context, package data, or specific requirements
5. **Write** to `document-playground-{topic}.html` in the project root
6. **Open in browser**: `start "" "document-playground-{topic}.html"` (Windows) or `open "document-playground-{topic}.html"` (macOS)

## Core requirements (every playground)

- **Single HTML file.** Inline all CSS and JS. No external dependencies, no CDN links, no external fonts.
- **Live preview.** Updates instantly on every control change. No "Apply" button.
- **Prompt output.** Natural language, not a value dump. Only mentions non-default choices. Includes enough context to act on without seeing the playground. Updates live.
- **Copy button.** Clipboard copy with brief "Copied!" feedback.
- **Download button.** Extracts the preview content and wraps it in a standalone NCI-branded HTML document with no controls -- just the clean document. Downloads via Blob URL.
- **Sensible defaults + presets.** Looks like a real document on first load. Include 3-5 named presets (e.g., "Basic SOW", "Full IGCE", "Simplified AP").
- **NCI theme.** Dark sidebar for controls, white document preview area. NCI blue (#003366) for headings and accents.

## State management pattern

Keep a single state object. Every control writes to it, every render reads from it.

```javascript
const state = {
  docType: 'sow',
  title: 'Statement of Work',
  sections: { background: true, scope: true, period: true, deliverables: true, qasp: true },
  farCitations: ['FAR 52.212-4'],
  showWatermark: true,
  showHeader: true,
  showFooter: true,
  // ... per-section content fields
};

const DEFAULTS = { ...state }; // snapshot for prompt diffing

function updateAll() {
  renderPreview();
  updatePrompt();
}
// Every control calls updateAll() on change
```

## Prompt output pattern

Generate a natural language instruction that can be pasted back into Claude:

```javascript
function updatePrompt() {
  const parts = [];

  // Doc type and title
  parts.push(`Generate a ${DOC_NAMES[state.docType]} titled "${state.title}"`);

  // Active sections
  const active = Object.entries(state.sections)
    .filter(([_, on]) => on)
    .map(([name]) => SECTION_LABELS[name]);
  if (active.length > 0) {
    parts.push(`that includes: ${active.join(', ')}`);
  }

  // FAR citations
  if (state.farCitations.length > 0) {
    parts.push(`referencing ${state.farCitations.join(', ')}`);
  }

  prompt.textContent = parts.join(' ') + '.';
}
```

## Download button pattern

The download extracts the preview and wraps it in a standalone document:

```javascript
function downloadDocument() {
  const preview = document.getElementById('preview').innerHTML;
  const html = buildStandaloneDoc(preview);
  const blob = new Blob([html], { type: 'text/html; charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `EAGLE_${state.docType.toUpperCase()}_${new Date().toISOString().slice(0,10)}.html`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(a.href);
}

function buildStandaloneDoc(bodyHtml) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EAGLE - ${state.title}</title>
  <style>
    /* NCI branded document styles -- inlined from preview */
    body { font-family: 'Segoe UI', system-ui, sans-serif; max-width: 8.5in; margin: 2rem auto; padding: 1in; background: #fff; color: #1a1a1a; line-height: 1.6; }
    h1, h2, h3 { color: #003366; }
    .watermark { position: fixed; top: 50%; left: 50%; transform: translate(-50%,-50%) rotate(-45deg); font-size: 120px; color: rgba(0,51,102,0.06); pointer-events: none; z-index: 0; font-weight: 900; }
    header { border-bottom: 2px solid #003366; padding-bottom: 0.5rem; margin-bottom: 2rem; color: #003366; font-size: 0.85rem; }
    footer { border-top: 1px solid #ccc; padding-top: 0.5rem; margin-top: 3rem; text-align: center; color: #888; font-size: 0.75rem; }
    table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
    th { background: #003366; color: #fff; padding: 0.5rem; text-align: left; }
    td { padding: 0.5rem; border: 1px solid #ddd; }
    tr:nth-child(even) td { background: #E6EEF5; }
    .far-citation { font-family: 'Courier New', monospace; font-weight: bold; color: #003366; background: #f0f4ff; padding: 1px 4px; border-radius: 3px; }
    .status-badge { display: inline-block; background: #FFF3CD; color: #856404; padding: 4px 12px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
    @media print { .watermark { color: rgba(0,51,102,0.03); } }
  </style>
</head>
<body>
  ${state.showWatermark ? '<div class="watermark">DRAFT</div>' : ''}
  ${state.showHeader ? '<header><strong>EAGLE</strong> | ' + state.title + '</header>' : ''}
  ${bodyHtml}
  ${state.showFooter ? '<footer>Generated by EAGLE - NCI Acquisition Assistant</footer>' : ''}
</body>
</html>`;
}
```

## Common mistakes to avoid

- Prompt output is just a settings dump -- write it as a natural instruction to Claude
- Preview doesn't look like a real document -- use page-like styling with margins, shadows, NCI branding
- Download includes the controls -- download must be ONLY the clean document
- Too many controls at once -- group by concern, use collapsible sections
- No presets -- the document should look complete on first load
- External dependencies -- everything must be inline
- FAR citations not highlighted -- use regex to auto-detect and style them
- Missing watermark -- DRAFT watermark is required for all generated documents
