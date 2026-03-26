# Acquisition Document Playground Template

Use this template when the playground is about configuring and previewing NCI acquisition documents: SOW, IGCE, Acquisition Plan, J&A, or Market Research Report. The user visually selects sections, adjusts content, and previews a branded document with download capability.

## Layout

```
+------------------------+----------------------------------+
|                        |                                  |
|  Controls:             |  Live Document Preview           |
|  • Doc type (radio)    |  (white page on dark bg)         |
|  • Title (text input)  |                                  |
|  • Presets (cards)     |  +----------------------------+  |
|  • Section toggles     |  | EAGLE | Title       Date  |  |
|    (per doc type)      |  |                            |  |
|  • FAR citations       |  |    DRAFT watermark         |  |
|    (chip input)        |  |                            |  |
|  • Formatting toggles  |  | # Document Title           |  |
|                        |  | ## Section 1               |  |
|  [Presets bar]         |  | Content with FAR 52.212    |  |
|  Basic | Full |        |  | highlighted in blue        |  |
|  Template | Custom     |  |                            |  |
|                        |  | | Table | Data |           |  |
|                        |  |                            |  |
|                        |  | Footer: EAGLE - NCI        |  |
|                        |  +----------------------------+  |
|                        +----------------------------------+
|                        |  Prompt output (natural lang)    |
|                        |  [ Copy Prompt ] [ Download HTML]|
+------------------------+----------------------------------+
```

## HTML structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EAGLE Document Playground</title>
  <style>/* all styles inline */</style>
</head>
<body>
  <div class="app">
    <aside class="sidebar"><!-- controls --></aside>
    <div class="main">
      <div class="preview-wrap">
        <div id="preview" class="document"><!-- live preview --></div>
      </div>
      <div class="prompt-bar">
        <pre id="prompt-text"></pre>
        <div class="prompt-actions">
          <button onclick="copyPrompt()">Copy Prompt</button>
          <button onclick="downloadDocument()">Download HTML</button>
        </div>
      </div>
    </div>
  </div>
  <script>/* all JS inline */</script>
</body>
</html>
```

## CSS specifications

### App layout
```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; height: 100vh; overflow: hidden; }
.app { display: grid; grid-template-columns: 320px 1fr; height: 100vh; }
.sidebar { background: #161822; border-right: 1px solid #2a2d3a; padding: 1.25rem; overflow-y: auto; }
.main { display: grid; grid-template-rows: 1fr auto; overflow: hidden; }
.preview-wrap { overflow-y: auto; padding: 2rem; background: #1a1d2b; display: flex; justify-content: center; }
```

### Document preview (page-like)
```css
.document {
  background: #ffffff;
  color: #1a1a1a;
  max-width: 8.5in;
  width: 100%;
  min-height: 11in;
  padding: 1in;
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  border-radius: 4px;
  font-family: 'Segoe UI', 'Calibri', system-ui, sans-serif;
  font-size: 11pt;
  line-height: 1.6;
}
.document h1 { color: #003366; font-size: 18pt; margin: 0 0 0.25rem; border-bottom: 2px solid #003366; padding-bottom: 0.5rem; }
.document h2 { color: #003366; font-size: 14pt; margin: 1.5rem 0 0.5rem; }
.document h3 { color: #003366; font-size: 12pt; margin: 1rem 0 0.25rem; }
```

### NCI branding elements
```css
.doc-header { border-bottom: 2px solid #003366; padding-bottom: 0.5rem; margin-bottom: 1.5rem; font-size: 9pt; color: #003366; display: flex; justify-content: space-between; }
.doc-header strong { font-size: 10pt; }
.doc-footer { border-top: 1px solid #ccc; padding-top: 0.5rem; margin-top: 2rem; text-align: center; color: #888; font-size: 8pt; }
.watermark { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-45deg); font-size: 100px; color: rgba(0,51,102,0.06); pointer-events: none; font-weight: 900; letter-spacing: 0.1em; }
.status-badge { display: inline-block; background: #FFF3CD; color: #856404; padding: 3px 10px; border-radius: 4px; font-size: 8pt; font-weight: 600; }
```

### Tables (NCI style)
```css
.document table { width: 100%; border-collapse: collapse; margin: 0.75rem 0; font-size: 10pt; }
.document th { background: #003366; color: #fff; padding: 6px 10px; text-align: left; font-weight: 600; }
.document td { padding: 6px 10px; border: 1px solid #ddd; }
.document tr:nth-child(even) td { background: #E6EEF5; }
```

### FAR citation highlighting
```css
.far-citation { font-family: 'Courier New', monospace; font-weight: 700; color: #003366; background: #f0f4ff; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }
```

### Sidebar controls
```css
.control-group { margin-bottom: 1.25rem; }
.control-group label { display: block; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-bottom: 0.4rem; }
.control-group input[type="text"] { width: 100%; background: #1e2130; border: 1px solid #2a2d3a; color: #e0e0e0; padding: 0.5rem; border-radius: 6px; font-size: 0.85rem; }
.control-group input[type="text"]:focus { border-color: #003366; outline: none; box-shadow: 0 0 0 2px rgba(0,51,102,0.3); }

/* Radio cards for doc type */
.radio-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
.radio-card { background: #1e2130; border: 1px solid #2a2d3a; border-radius: 6px; padding: 0.5rem; text-align: center; cursor: pointer; font-size: 0.8rem; transition: all 0.15s; }
.radio-card:hover { border-color: #444; }
.radio-card.active { border-color: #003366; background: rgba(0,51,102,0.15); color: #4da6ff; }

/* Section toggles */
.toggle-row { display: flex; align-items: center; justify-content: space-between; padding: 0.35rem 0; border-bottom: 1px solid #1e2130; }
.toggle-row span { font-size: 0.8rem; }
.toggle { width: 36px; height: 20px; background: #2a2d3a; border-radius: 10px; position: relative; cursor: pointer; transition: background 0.2s; }
.toggle.on { background: #003366; }
.toggle::after { content: ''; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; background: #fff; border-radius: 50%; transition: transform 0.2s; }
.toggle.on::after { transform: translateX(16px); }

/* FAR citation chips */
.chip-input { display: flex; flex-wrap: wrap; gap: 0.3rem; background: #1e2130; border: 1px solid #2a2d3a; border-radius: 6px; padding: 0.4rem; min-height: 36px; }
.chip { background: rgba(0,51,102,0.2); color: #4da6ff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; display: flex; align-items: center; gap: 4px; }
.chip .remove { cursor: pointer; opacity: 0.6; }
.chip .remove:hover { opacity: 1; }
.chip-input input { background: none; border: none; color: #e0e0e0; outline: none; flex: 1; min-width: 80px; font-size: 0.8rem; }

/* Preset bar */
.presets { display: flex; gap: 0.4rem; margin-bottom: 1rem; }
.preset-btn { background: #1e2130; border: 1px solid #2a2d3a; color: #aaa; padding: 0.4rem 0.75rem; border-radius: 6px; cursor: pointer; font-size: 0.75rem; transition: all 0.15s; flex: 1; text-align: center; }
.preset-btn:hover { border-color: #003366; color: #e0e0e0; }
.preset-btn.active { border-color: #003366; background: rgba(0,51,102,0.15); color: #4da6ff; }
```

### Prompt bar
```css
.prompt-bar { background: #161822; border-top: 1px solid #2a2d3a; padding: 1rem 1.5rem; }
#prompt-text { font-family: system-ui, sans-serif; font-size: 0.85rem; color: #ccc; white-space: pre-wrap; max-height: 100px; overflow-y: auto; margin-bottom: 0.75rem; line-height: 1.5; }
.prompt-actions { display: flex; gap: 0.5rem; }
.prompt-actions button { padding: 0.5rem 1.25rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: all 0.15s; }
.prompt-actions button:first-child { background: #003366; color: #fff; }
.prompt-actions button:first-child:hover { background: #004488; }
.prompt-actions button:last-child { background: #1e2130; color: #4da6ff; border: 1px solid #003366; }
.prompt-actions button:last-child:hover { background: rgba(0,51,102,0.15); }
```

## Control types by decision

| Decision | Control | Example |
|---|---|---|
| Document type | Radio cards (2-col grid) | SOW, IGCE, AP, J&A, MRR |
| Title | Text input | "Cloud Migration Services SOW" |
| Sections | Toggle rows (per doc type) | Background, Scope, Deliverables, QASP... |
| FAR citations | Chip input (type + Enter) | FAR 15.304, DFARS 252.204-7012 |
| Cost rows (IGCE) | Add-row button + editable fields | CLIN, description, qty, unit price |
| Formatting | Toggle rows | Watermark, header, footer, NCI branding |
| Presets | Button row | "Basic", "Full", "Template", "Minimal" |

## Section definitions per document type

The sections object in state changes when the doc type changes. Each doc type has its own section set:

```javascript
const SECTIONS = {
  sow: [
    { key: 'background', label: 'Background & Purpose', default: true },
    { key: 'scope', label: 'Scope of Work', default: true },
    { key: 'period', label: 'Period of Performance', default: true },
    { key: 'standards', label: 'Applicable Documents & Standards', default: false },
    { key: 'tasks', label: 'Tasks & Requirements', default: true },
    { key: 'deliverables', label: 'Deliverables', default: true },
    { key: 'gfp', label: 'Government-Furnished Property', default: false },
    { key: 'place', label: 'Place of Performance', default: true },
    { key: 'security', label: 'Security Requirements', default: false },
    { key: 'qasp', label: 'Quality Assurance (QASP)', default: true },
    { key: 'personnel', label: 'Key Personnel', default: false },
    { key: 'travel', label: 'Travel Requirements', default: false },
  ],
  igce: [
    { key: 'purpose', label: 'Purpose', default: true },
    { key: 'methodology', label: 'Methodology', default: true },
    { key: 'direct_costs', label: 'Direct Costs', default: true },
    { key: 'labor_costs', label: 'Labor Costs', default: true },
    { key: 'indirect_costs', label: 'Indirect Costs', default: true },
    { key: 'other_costs', label: 'Other Costs (Travel, ODCs)', default: false },
    { key: 'total', label: 'Total Estimated Cost', default: true },
    { key: 'assumptions', label: 'Assumptions & Limitations', default: true },
    { key: 'confidence', label: 'Confidence Level', default: false },
    { key: 'sources', label: 'Data Sources', default: true },
  ],
  ap: [
    { key: 'background', label: 'Background', default: true },
    { key: 'requirements', label: 'Requirements', default: true },
    { key: 'market_research', label: 'Market Research Summary', default: true },
    { key: 'strategy', label: 'Acquisition Strategy', default: true },
    { key: 'contract_type', label: 'Contract Type', default: true },
    { key: 'source_selection', label: 'Source Selection', default: false },
    { key: 'period', label: 'Period of Performance', default: true },
    { key: 'budget', label: 'Budget & Funding', default: true },
    { key: 'milestones', label: 'Milestones', default: false },
    { key: 'competition', label: 'Competition Strategy', default: true },
  ],
  ja: [
    { key: 'authority', label: 'Statutory Authority', default: true },
    { key: 'activity', label: 'Contracting Activity', default: true },
    { key: 'action', label: 'Description of Action', default: true },
    { key: 'supplies', label: 'Description of Supplies/Services', default: true },
    { key: 'justification', label: 'Authority Justification', default: true },
    { key: 'market_research', label: 'Market Research', default: true },
    { key: 'barriers', label: 'Actions to Remove Barriers', default: true },
    { key: 'determination', label: 'Price Reasonableness', default: false },
  ],
  mrr: [
    { key: 'requirement', label: 'Requirement Description', default: true },
    { key: 'sources_searched', label: 'Sources Searched', default: true },
    { key: 'potential_sources', label: 'Potential Sources', default: true },
    { key: 'market_conditions', label: 'Market Conditions', default: true },
    { key: 'commercial', label: 'Commercial Availability', default: true },
    { key: 'small_business', label: 'Small Business Considerations', default: true },
    { key: 'recommendation', label: 'Recommendation', default: true },
    { key: 'methodology', label: 'Research Methodology', default: false },
  ],
};
```

## Preview rendering

Build the document HTML from state:

```javascript
function renderPreview() {
  const doc = document.getElementById('preview');
  const type = state.docType;
  const secs = SECTIONS[type].filter(s => state.sections[s.key]);

  let html = '';

  // Watermark
  if (state.showWatermark) {
    html += '<div class="watermark">DRAFT</div>';
  }

  // Header
  if (state.showHeader) {
    html += `<div class="doc-header">
      <span><strong>EAGLE</strong> &nbsp;|&nbsp; ${esc(state.title)}</span>
      <span>${new Date().toLocaleDateString()}</span>
    </div>`;
  }

  // Title block
  html += `<h1>${esc(DOC_TITLES[type])}</h1>`;
  html += `<h2 style="color:#444;font-size:12pt;margin-top:0">${esc(state.title)}</h2>`;
  html += `<p style="color:#666;font-size:9pt">National Cancer Institute (NCI)</p>`;
  html += `<p><span class="status-badge">DRAFT -- FOR REVIEW ONLY</span></p>`;
  html += '<hr style="border:none;border-top:1px solid #ddd;margin:1rem 0">';

  // Sections
  let secNum = 1;
  for (const sec of secs) {
    html += `<h2>${secNum}. ${esc(sec.label.toUpperCase())}</h2>`;
    html += renderSectionContent(type, sec.key, secNum);
    secNum++;
  }

  // FAR citations footer
  if (state.farCitations.length > 0) {
    html += '<hr style="border:none;border-top:1px solid #ddd;margin:1.5rem 0">';
    html += '<h3>Applicable Regulations</h3>';
    html += '<ul>';
    for (const cite of state.farCitations) {
      html += `<li><span class="far-citation">${esc(cite)}</span></li>`;
    }
    html += '</ul>';
  }

  // Footer
  if (state.showFooter) {
    html += '<div class="doc-footer">Generated by EAGLE -- NCI Acquisition Assistant</div>';
  }

  // Highlight any FAR citations in the body text
  doc.innerHTML = highlightFAR(html);

  // Make document position:relative for watermark
  doc.style.position = 'relative';
}

function highlightFAR(html) {
  // Match FAR/DFARS/HHSAM/HHSAR citations not already inside a tag
  return html.replace(
    /(?<![">])\b((?:FAR|DFARS|HHSAM|HHSAR)\s+\d+[\.\d]*(?:\([a-z]\)(?:\(\d+\))?)?(?:-\d+)?)\b/g,
    '<span class="far-citation">$1</span>'
  );
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
```

## Section content generation

Each section has placeholder content appropriate to its doc type:

```javascript
function renderSectionContent(type, key, num) {
  // Return placeholder content appropriate for each section
  // This gives the preview a realistic appearance
  const content = SECTION_CONTENT[type]?.[key];
  if (content) return content;
  return '<p style="color:#888;font-style:italic">[Section content will be generated by EAGLE]</p>';
}
```

Pre-populate `SECTION_CONTENT` with realistic placeholder text for each doc type and section. For example:

**SOW background:**
```html
<p>The National Cancer Institute (NCI), part of the National Institutes of Health (NIH),
requires [description of requirement]. This Statement of Work (SOW) describes the tasks,
deliverables, and performance requirements for this acquisition.</p>
```

**IGCE direct_costs:**
```html
<table>
  <thead><tr><th>Description</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr></thead>
  <tbody>
    <tr><td>[Line Item 1]</td><td>1</td><td>$0.00</td><td>$0.00</td></tr>
    <tr><td>[Line Item 2]</td><td>1</td><td>$0.00</td><td>$0.00</td></tr>
  </tbody>
</table>
<p><strong>Direct Costs Subtotal:</strong> $0.00</p>
```

**SOW deliverables:**
```html
<table>
  <thead><tr><th>Deliverable</th><th>Due Date</th><th>Format</th></tr></thead>
  <tbody>
    <tr><td>Project Management Plan</td><td>30 days after award</td><td>PDF/Word</td></tr>
    <tr><td>Monthly Status Reports</td><td>5th of each month</td><td>PDF</td></tr>
    <tr><td>Final Report</td><td>30 days before end</td><td>PDF</td></tr>
  </tbody>
</table>
```

## Preset configurations

```javascript
const PRESETS = {
  sow: [
    {
      name: 'Basic SOW',
      config: { sections: { background: true, scope: true, period: true, deliverables: true, qasp: true } }
    },
    {
      name: 'Full SOW',
      config: { sections: Object.fromEntries(SECTIONS.sow.map(s => [s.key, true])) }
    },
    {
      name: 'IT Services',
      config: {
        sections: { background: true, scope: true, period: true, tasks: true, deliverables: true, security: true, qasp: true, personnel: true },
        farCitations: ['FAR 52.204-21', 'DFARS 252.204-7012', 'FAR 52.212-4']
      }
    },
  ],
  igce: [
    {
      name: 'Basic IGCE',
      config: { sections: { purpose: true, direct_costs: true, total: true, assumptions: true } }
    },
    {
      name: 'Full IGCE',
      config: { sections: Object.fromEntries(SECTIONS.igce.map(s => [s.key, true])) }
    },
    {
      name: 'Labor-Heavy',
      config: {
        sections: { purpose: true, methodology: true, labor_costs: true, indirect_costs: true, total: true, assumptions: true, sources: true }
      }
    },
  ],
  // Similar for ap, ja, mrr
};
```

## Prompt output generation

```javascript
function updatePrompt() {
  const parts = [];
  const type = state.docType;
  const typeName = DOC_TITLES[type];

  parts.push(`Generate a ${typeName} titled "${state.title}"`);

  // List active sections
  const active = SECTIONS[type]
    .filter(s => state.sections[s.key])
    .map(s => s.label);
  if (active.length > 0 && active.length < SECTIONS[type].length) {
    parts.push(`that includes: ${active.join(', ')}`);
  } else if (active.length === SECTIONS[type].length) {
    parts.push('with all standard sections');
  }

  // FAR citations
  if (state.farCitations.length > 0) {
    parts.push(`referencing ${state.farCitations.join(', ')}`);
  }

  // Non-default formatting
  if (!state.showWatermark) parts.push('without a DRAFT watermark');

  const text = parts.join(' ') + '.';
  document.getElementById('prompt-text').textContent = text;
}
```

## Copy and download handlers

```javascript
function copyPrompt() {
  const text = document.getElementById('prompt-text').textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    btn.style.background = '#1a7f37';
    setTimeout(() => { btn.textContent = orig; btn.style.background = ''; }, 1500);
  });
}

// downloadDocument() and buildStandaloneDoc() are defined in the main skill file
```

## Example use cases

- **SOW for IT services**: Background, scope with 4 tasks, deliverables table, QASP, security (DFARS 252.204-7012)
- **IGCE with labor breakdown**: Purpose, methodology, labor categories with GSA rates, indirect costs, total with confidence level
- **Simplified Acquisition Plan**: Background, requirements, strategy, contract type, budget -- for acquisitions under SAT
- **Sole Source J&A**: All sections filled, authority citing FAR 6.302-1, market research justification
- **Market Research Report**: Sources searched (SAM.gov, GSA Advantage, GovWin), potential vendors, small business analysis
