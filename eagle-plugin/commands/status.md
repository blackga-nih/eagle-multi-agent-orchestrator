---
name: status
command: /status
description: Check intake package status and document completeness
usage: /status [intake_id]
examples:
  - /status
  - /status EAGLE-12345
---

# /status Command

Check the current intake package status, document completeness, and next actions.

## Usage

```
/status [optional: intake_id]
```

## Behavior

### Without Intake ID
Shows status of current/most recent intake session.

### With Intake ID
Shows status of specific intake package.

## Output

### Status Summary
```markdown
## Intake Package Status

**Intake ID:** EAGLE-demo-user-12345
**Status:** In Progress
**Completion:** 50%

### Acquisition Summary

| Category | Value |
|----------|-------|
| Requirement | Illumina NextSeq 2000 Sequencer |
| Estimated Value | $85,000 |
| Acquisition Type | Simplified Acquisition |
| Competition | Sole Source (FAR 6.302-1) |

### Document Status

| Document | Status | Last Updated |
|----------|--------|--------------|
| Statement of Work | ✅ Complete | 2024-01-15 |
| IGCE | ✅ Complete | 2024-01-15 |
| Market Research | 🔲 Not Started | - |
| J&A | 🔲 Required | - |

### Next Actions

1. **Generate Market Research Report**
   Use `/document market-research` to create

2. **Complete J&A for Sole Source**
   Use `/document ja` to create

3. **Submit for Review**
   Once documents complete, submit package

### Files in Package

- sow_20240115_143022.md (2.1 KB)
- igce_20240115_145530.md (1.8 KB)
```

## Document Status Icons

| Icon | Meaning |
|------|---------|
| ✅ | Complete |
| 🔲 | Not Started |
| ⏳ | In Progress |
| ⚠️ | Needs Revision |
| ❌ | Missing (Required) |

## Completeness Calculation

Percentage based on required documents for acquisition type:

### Micro-Purchase (≤$15K)
- Statement of Need (SON)
- Purchase Request

### Simplified ($15K–$350K)
- SOW
- IGCE
- Market Research
- Acquisition Plan (AP Under SAT)
- (J&A if sole source)

### Negotiated (>$350K)
- SOW
- IGCE
- Market Research
- Acquisition Plan (AP Above SAT)
- D&F
- Tech Eval Plan
- (J&A if sole source)

## Example Outputs

### Example 1: Active Intake
```
User: /status

EAGLE: 
## Intake Package Status

**Intake ID:** EAGLE-demo-12345
**Completion:** 75% ████████░░

### Documents

| Document | Status |
|----------|--------|
| SOW | ✅ Complete |
| IGCE | ✅ Complete |
| Market Research | ✅ Complete |
| J&A | 🔲 Required |

### Next Steps

Your package is almost complete! You just need the J&A document.

Since you indicated Illumina is the only source, use:
`/document ja`

I'll use FAR 6.302-1 (Only One Responsible Source) as the authority.
```

### Example 2: No Active Intake
```
User: /status

EAGLE: 
You don't have an active intake session.

To start a new acquisition request, use:
`/intake`

Or describe your need:
`/intake I need to purchase lab equipment`
```

### Example 3: Complete Package
```
User: /status

EAGLE:
## Intake Package Status ✅

**Intake ID:** EAGLE-demo-12345
**Status:** Complete
**Completion:** 100% ██████████

All required documents have been generated:
- ✅ Statement of Work
- ✅ IGCE
- ✅ Market Research
- ✅ J&A

### Package Location
S3: `s3://nci-documents/eagle/demo-user/documents/`

### Next Steps
1. Review all documents for accuracy
2. Obtain required signatures
3. Submit to contracting officer

Would you like me to provide a summary for the package cover sheet?
```

## Routing

This command invokes the `get_intake_status` tool directly and displays formatted results.
