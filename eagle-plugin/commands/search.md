---
name: search
command: /search
description: Search FAR/DFAR regulations, policies, and the knowledge base
usage: /search <query> [--part <number>] [--type <type>]
examples:
  - /search sole source justification
  - /search competition requirements --part 6
  - /search small business set-aside --type regulation
---

# /search Command

Search the FAR/DFAR database, policies, and knowledge base.

## Usage

```
/search <query> [options]
```

## Options

| Option | Description | Values |
|--------|-------------|--------|
| `--part` | Limit to specific FAR part | 1-53 |
| `--type` | Filter by content type | regulation, guidance, template, precedent |
| `--limit` | Maximum results | 1-15 (default: 5) |

## Search Targets

### 1. FAR Database (Default)
53+ entries covering key regulations:
- Competition requirements (Part 6)
- Acquisition planning (Part 7)
- Simplified acquisition (Part 13)
- Negotiated procurement (Part 15)
- Contract types (Part 16)
- Small business (Part 19)
- And more...

### 2. DFAR/HHSAR Supplements
Agency-specific requirements:
- HHS-specific clauses
- NIH research contracting
- Medical device requirements

### 3. Knowledge Base
- Past acquisition precedents
- Policy documents
- Templates and checklists
- Lessons learned

## Examples

### Example 1: Basic Search
```
User: /search sole source justification requirements

EAGLE: Found 5 relevant FAR sections:

### 1. FAR 6.302 - Circumstances Permitting Other Than Full Competition
**Applicability:** Sole source or limited competition situations
> Seven exceptions: (1) Only one responsible source/unique supply...

### 2. FAR 6.303 - Justifications (J&A)
**Applicability:** All sole source or limited competition actions
> Written Justification and Approval required...

### 3. FAR 6.304 - Approval of Justifications
**Applicability:** All J&A approvals
> Approval thresholds: ≤$750K by Contracting Officer...

[More results...]
```

### Example 2: Part-Specific Search
```
User: /search set-aside --part 19

EAGLE: Found 5 FAR Part 19 sections:

### 1. FAR 19.502-2 - Total Small Business Set-Asides
> Set aside for small business if reasonable expectation of 2+ offers...

### 2. FAR 19.805 - 8(a) Competitive Requirements
> Competitive 8(a) acquisitions required above $4.5M (services)...

### 3. FAR 19.1305 - HUBZone Set-Aside Procedures
> Set aside for HUBZone if reasonable expectation of 2+ offers...

[More results...]
```

### Example 3: Template Search
```
User: /search market research template --type template

EAGLE: Found 1 template:

### Market Research Report Template
**Location:** data/templates/market-research-template.md

Key sections:
1. Description of Need
2. Sources Consulted
3. Potential Sources Identified
4. Commercial Availability Analysis
5. Small Business Analysis
6. Recommended Acquisition Strategy

Would you like me to retrieve the full template?
```

## Response Format

Each result includes:
- **Part/Section:** FAR reference
- **Title:** Section name
- **Summary:** Key points
- **Applicability:** When this applies
- **Related sections:** Cross-references

## Routing

This command routes to:
- `compliance` skill for regulation searches
- `knowledge-retrieval` skill for broader searches

## Notes

⚠️ **Always verify** against current FAR at acquisition.gov for official guidance.

The embedded database is a reference tool, not a replacement for official sources.
