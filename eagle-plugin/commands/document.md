---
name: document
command: /document
description: Generate acquisition documents (SOW, IGCE, AP, J&A, Market Research)
usage: /document <type> [title]
examples:
  - /document sow
  - /document igce "CT Scanner Acquisition"
  - /document ja
  - /document market-research
---

# /document Command

Generate acquisition documents based on intake context.

## Usage

```
/document <type> [optional: document title]
```

## Document Types

| Type | Aliases | Description |
|------|---------|-------------|
| `sow` | `statement-of-work` | Statement of Work |
| `igce` | `cost-estimate` | Independent Government Cost Estimate |
| `ap` | `acquisition-plan` | Acquisition Plan (FAR 7.105) |
| `ja` | `j&a`, `justification` | Justification & Approval |
| `market-research` | `mr`, `market` | Market Research Report |

## Behavior

### With Active Intake
Uses context from current intake session:
- Requirement description
- Estimated value
- Timeline
- Vendor information
- Acquisition type determination

### Without Active Intake
Prompts for required information:
1. Document type (if not specified)
2. Requirement description
3. Relevant details for document type

## Examples

### Example 1: Generate SOW from Intake
```
User: /document sow

EAGLE: I'll generate a Statement of Work based on your intake:

**Requirement:** Illumina NextSeq 2000 Sequencer
**Value:** $85,000
**Type:** Commercial equipment acquisition

[Generates SOW draft]

---
# STATEMENT OF WORK (SOW)
## Illumina NextSeq 2000 Genomic Sequencer
### National Cancer Institute (NCI)
...
```

### Example 2: Generate J&A
```
User: /document ja "Sole Source for Proprietary Equipment"

EAGLE: I'll create a Justification & Approval document.

To complete the J&A, I need:
1. The authority you're citing (FAR 6.302-1 seems applicable for proprietary)
2. The proposed contractor name
3. Brief rationale for why this is the only source

Would you like me to proceed with FAR 6.302-1 (Only One Responsible Source)?
```

### Example 3: IGCE with Line Items
```
User: /document igce

EAGLE: I'll generate an IGCE. Let me gather the cost information:

Based on your intake, I have:
- Illumina NextSeq 2000: $75,000 (equipment)
- Installation: $5,000
- Training: $3,000
- First-year warranty: Included

Would you like me to add overhead (12%) and contingency (10%)?
```

## Context Requirements

Each document type has required context:

### SOW
- Requirement description (required)
- Period of performance (optional, defaults to 12 months)
- Deliverables (optional, uses defaults)
- Tasks (optional, generated from description)

### IGCE
- Line items with costs (required)
- Overhead rate (optional, default 12%)
- Contingency (optional, default 10%)

### J&A
- Authority cited (required)
- Contractor name (required)
- Rationale (required)
- Estimated value (required)

### Market Research
- Requirement description (required)
- NAICS code (optional)
- Potential vendors (optional)

## Output

Documents are:
1. Displayed in chat as formatted markdown
2. Saved to S3: `s3://nci-documents/eagle/{tenant}/generated/{doc_type}_{timestamp}.md`
3. Linked in intake status

## Routing

This command routes to the `document-generator` skill.
