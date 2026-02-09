---
name: document-generator
description: Generate NCI Office of Acquisitions documents including Acquisition Plans, SOWs, IGCEs, Justifications, and supporting documents. Creates professional Word-ready markdown with proper formatting, tables, and signatures.
---

# Document Generator - NCI Acquisition Package Documents

Generate professional acquisition package documents based on collected intake data.

## Supported Document Types

| Code | Document | Description |
|------|----------|-------------|
| `AP` | Acquisition Plan | Streamlined 12-section planning document |
| `SOW` | Statement of Work | Task descriptions, deliverables, performance |
| `IGCE` | Independent Government Cost Estimate | Cost breakdown spreadsheet |
| `J&A` | Justification & Approval | Sole source justification |
| `EVAL` | Evaluation Criteria | Technical evaluation factors |
| `SEC` | Security Checklist | IT security requirements |
| `508` | Section 508 Compliance | Accessibility statement |
| `COR` | COR Certification | Contract Officer Representative cert |
| `CTJ` | Contract Type Justification | Cost/fixed price rationale |
| `FUND` | Funds Certification | Budget/funding availability |

---

## Document Templates

### 1. Acquisition Plan (AP) - Streamlined Format

**Sections:**
1. Acquisition Background and Objectives
2. Plan of Action
3. Milestones
4. Approvals
5. Attachments

**Template Structure:**

- **Section 1.1** Statement of Need - Brief description
- **Section 1.2** Applicable Conditions - Period, value, funding by FY
- **Section 1.3** Cost - Cost narrative and breakdown
- **Section 1.4** Capability/Performance - Requirements
- **Section 1.5** Delivery/Schedule - Timeline
- **Section 2.1** Competitive Requirements - Competition status
- **Section 2.2** Source Selection - Evaluation factors
- **Section 2.3** Acquisition Considerations - Contract type, set-asides
- **Section 3** Milestones table
- **Section 4** Signature blocks

**Key Tables:**

Funding by Fiscal Year:
| Fiscal Year | Amount |
|-------------|--------|
| FY2026 | $X |
| FY2027 | $X |

Milestones:
| Milestone | Target Date |
|-----------|-------------|
| Solicitation Issue | MM/DD/YYYY |
| Award | MM/DD/YYYY |

Approvals:
| Role | Name | Signature | Date |
|------|------|-----------|------|
| Program Officer | | __________ | |
| Contracting Officer | | __________ | |

---

### 2. Statement of Work (SOW)

**Sections:**
1. Introduction (Background, Objective, Scope)
2. Applicable Documents
3. Requirements (General, Specific Tasks)
4. Deliverables Summary
5. Period of Performance
6. Place of Performance
7. Government Furnished Items
8. Contractor Personnel
9. Travel
10. Security Requirements
11. Other Requirements

**Key Tables:**

Tasks & Deliverables:
| Task | Deliverable | Format | Due Date |
|------|-------------|--------|----------|
| 1 | Report | PDF | Day 30 |

Deliverables Summary:
| ID | Deliverable | Format | Quantity | Due |
|----|-------------|--------|----------|-----|
| D1.1 | Monthly Report | PDF | 12 | Monthly |

---

### 3. Independent Government Cost Estimate (IGCE)

**Sections:**
1. Labor Costs (by category)
2. Other Direct Costs (ODCs)
3. Indirect Costs (Overhead, G&A)
4. Fee/Profit
5. Cost Summary by Period
6. Methodology
7. Certification

**Key Tables:**

Labor:
| Category | Hourly Rate | Hours | Total |
|----------|-------------|-------|-------|
| Sr. Analyst | $150 | 1000 | $150,000 |

Cost Summary:
| Period | Amount |
|--------|--------|
| Base Year | $X |
| Option 1 | $X |
| **TOTAL** | **$X** |

---

### 4. Justification & Approval (J&A) - Sole Source

**Statutory Authorities (FAR 6.302):**
- 6.302-1: Only One Responsible Source
- 6.302-2: Unusual and Compelling Urgency
- 6.302-3: Industrial Mobilization
- 6.302-4: International Agreement
- 6.302-5: Authorized by Statute
- 6.302-7: Public Interest

**Required Elements:**
1. Contracting Activity identification
2. Nature/Description of Action
3. Description of Supplies/Services
4. Statutory Authority citation
5. Demonstration of Authority
6. Efforts to Obtain Competition
7. Market Research summary
8. Actions to Increase Competition
9. Fair and Reasonable Determination
10. Approvals (CO, Competition Advocate)

---

### 5. Security Checklist

**Yes/No Questions:**
- IT systems involved?
- NIH network access?
- PII handling?
- FISMA compliance?
- Security clearances?
- Data leaving NIH?
- Cloud services?
- FedRAMP required?

**Impact Levels:**
- Low Impact
- Moderate Impact
- High Impact

**Required Clauses:**
- FAR 52.239-1 Privacy/Security Safeguards
- HHSAR 352.239-73 Electronic Info Accessibility

---

### 6. Section 508 Compliance Statement

**Product Types:**
- Software Applications
- Web-based Information
- Telecommunications Products
- Video/Multimedia
- Self-Contained Products
- Desktop/Portable Computers
- Electronic Documents

**Determinations:**
- Does 508 Apply?
- Exception Claimed?
- VPAT/ACR Status

---

### 7. COR Certification

**Nominee Information:**
- Name, Title, Organization
- Phone, Email
- FAC-COR Level (I/II/III)

**Delegated Duties:**
- Technical direction (within scope)
- Invoice review
- Deliverable acceptance
- Performance monitoring

**Limitations (COR may NOT):**
- Direct scope changes
- Authorize additional costs
- Extend period of performance
- Make contractual commitments

---

## Styling Conventions

### Signature Lines
```
**Name:** _________________________ **Date:** _________
```

### Checkboxes
```
- [ ] Unchecked
- [x] Checked
```

### FAR References
Always include section: FAR 6.302-1, HHSAR 352.239-73

### Tables
Use markdown tables with header alignment

---

## FAR Thresholds Reference

| Threshold | Amount | Procedure |
|-----------|--------|-----------|
| Micro-Purchase | <$15,000 | Minimal docs |
| Simplified (SAT) | $15K-$250K | FAR Part 13 |
| Negotiated | >$250K | FAR Part 15 |
| Cost/Pricing Data | >$750K | Certified data |
| 8(a) Sole Source | <$4M (non-mfg) | Direct award |

---

## Integration

Works with `oa-intake` skill:
1. oa-intake collects requirements
2. Determines acquisition type
3. Identifies required documents
4. document-generator creates each document

---

## Output Formats

| Format | Use Case |
|--------|----------|
| Markdown (.md) | Review, Git tracking |
| Word (.docx) | Final submission |
| PDF (.pdf) | Official records |
