---
name: knowledge-retrieval
description: Search the knowledge base for policies, procedures, past acquisitions, regulatory guidance, and technical documentation using semantic search.
triggers:
  - "search", "find", "look up", "what is"
  - "policy", "procedure", "regulation"
  - "past acquisition", "example", "precedent", "similar"
  - "tell me about", "explain"
---

# Knowledge Retrieval Skill

Search the comprehensive knowledge base for federal acquisition regulations, policies, procedures, past acquisitions, and technical documentation.

## Knowledge Base Contents

### 1. Federal Acquisition Regulation (FAR)
- **Complete Text:** All 53 parts with current amendments
- **Historical Versions:** Regulatory changes and effective dates
- **Interpretation Guidance:** GAO decisions, court cases, agency guidance
- **Cross-References:** Related sections and implementing procedures

### 2. Defense Federal Acquisition Regulation Supplement (DFARS)
- **Complete Supplement:** All DOD-specific requirements
- **Procedures Guidance:** DFARS-PGI implementation details
- **Policy Updates:** Recent changes and transition guidance
- **DOD-Specific Clauses:** Required flow-downs and certifications

### 3. HHS Acquisition Regulation (HHSAR)
- **HHS-Specific Procedures:** Department-level policies
- **NIH/NCI Guidance:** Institute-specific requirements
- **Research Contracting:** R&D-specific provisions
- **Human Subjects/Animal Welfare:** Special requirements

### 4. Agency-Specific Guidance
- **NIH Acquisition Manual:** Institute-specific procedures
- **NCI Acquisition Policies:** Cancer research acquisition guidance
- **Past Performance Data:** Historical contractor performance
- **Lessons Learned:** Acquisition outcomes and improvements

### 5. Templates & Tools
- **Contract Templates:** Pre-approved language and clauses
- **Evaluation Criteria:** Standard templates by acquisition type
- **Checklists:** Quality assurance and compliance verification
- **Decision Trees:** Structured decision-making frameworks

---

## Search Capabilities

### Semantic Search

Uses vector embeddings to find conceptually similar content, not just keyword matches.

**Query Types:**

#### Regulatory Questions
- "What are the requirements for limited competition?"
- "When is market research required?"
- "How do I justify a sole source acquisition?"
- "What clauses are required for cost-reimbursement contracts?"

#### Procedural Questions
- "What is the process for source selection?"
- "How do I conduct an acquisition review?"
- "What approvals are needed for IDIQ contracts?"
- "How do I document past performance evaluations?"

#### Comparative Analysis
- "Compare fixed-price vs cost-reimbursement contracts"
- "What's the difference between SAT and full competition?"
- "GSA Schedule vs direct contracting analysis"
- "Commercial vs non-commercial acquisition procedures"

#### Precedent Searches
- "Find similar acquisitions for medical equipment"
- "Past awards for IT services over $500K"
- "Examples of successful 8(a) procurements"

---

## Search Parameters

### Basic Search
```json
{
  "query": "natural language search query",
  "max_results": 5
}
```

### Filtered Search
```json
{
  "query": "competition requirements",
  "filters": {
    "source": "FAR",           // FAR, DFARS, HHSAR, POLICY
    "part": "6",               // Specific FAR part
    "type": "regulation",      // regulation, guidance, template, precedent
    "date_range": "2024-01-01" // Documents from this date forward
  },
  "max_results": 10
}
```

---

## Response Format

### Search Results Structure
```json
{
  "query": "search query",
  "results_count": 5,
  "results": [
    {
      "document_id": "FAR-6.302-1",
      "title": "FAR 6.302-1 - Only One Responsible Source",
      "excerpt": "Contracting officers may solicit from a single source...",
      "confidence": 0.92,
      "source": "FAR Part 6",
      "effective_date": "2024-01-01",
      "related_sections": ["FAR 6.303", "FAR 6.304"]
    }
  ],
  "metadata": {
    "search_time_ms": 234,
    "index_date": "2024-01-15"
  }
}
```

### Confidence Levels

| Confidence | Meaning | Citation Approach |
|------------|---------|-------------------|
| 0.95+ | Exact/near-exact match | Cite directly with full reference |
| 0.85-0.94 | Strong semantic match | Cite with confidence |
| 0.75-0.84 | Good match | Cite with qualifications |
| 0.60-0.74 | Relevant but not definitive | Suggest further research |
| < 0.60 | Weak match | Recommend manual search |

---

## Citation Guidelines

### High Confidence (>0.90)
> "Per FAR 6.102(a), contracting officers shall provide for full and open competition through use of competitive procedures..." ✅

### Medium Confidence (0.75-0.90)
> "Based on FAR Part 6 guidance (similar provisions in 6.102), competition is generally required..." ⚠️

### Lower Confidence (<0.75)
> "This situation may relate to competition requirements in FAR Part 6, but recommend reviewing specific sections..." 🔍

### Multi-Source Synthesis
When multiple sources provide relevant information:

```markdown
**Competition Requirements Summary** (based on 3 sources):

1. **FAR 6.102** (Confidence: 0.94) - Basic requirement for full and open competition
2. **FAR 6.302-1** (Confidence: 0.89) - Only one responsible source exception
3. **GAO Decision B-12345** (Confidence: 0.82) - Precedent for similar situation

**Key Takeaways:**
- Full competition is the default requirement
- Limited exceptions require specific justification
- Document rationale thoroughly for review
```

---

## Common Search Scenarios

### Scenario 1: Competition Requirements

**User:** "What are the FAR requirements for sole source justification?"

**Search:** `sole source justification requirements FAR`

**Response:**
```markdown
Found 5 relevant sections:

### 1. FAR 6.302 - Circumstances Permitting Other Than Full Competition
**Confidence:** 0.95
Seven exceptions to full and open competition:
- 6.302-1: Only one responsible source
- 6.302-2: Unusual and compelling urgency
- [Additional exceptions...]

### 2. FAR 6.303 - Justifications
**Confidence:** 0.92
Written J&A required with:
- Description of supplies/services
- Authority cited
- Demonstration of unique qualifications
- Market research summary

### 3. FAR 6.304 - Approval of Justifications
**Confidence:** 0.90
Approval thresholds:
- ≤$750K: Contracting Officer
- ≤$15M: Competition Advocate
- [Full threshold list...]
```

### Scenario 2: Small Business Set-Aside

**User:** "Should a $500K IT service be set aside for small business?"

**Search:** `small business set-aside IT services $500K`

**Response:**
```markdown
### Analysis Summary

**FAR 19.502-2** (Confidence: 0.93)
For IT services valued at $500K:
- Above SAT ($250K) - requires competition analysis
- Below 8(a) sole source limit ($4.5M for services)

**Recommended Approach:**
1. Conduct market research for small business sources
2. Check SBA size standard for NAICS 541511/541512 ($34M)
3. If 2+ capable small businesses identified → Set-aside
4. If not → Document rationale for full and open

**Related Considerations:**
- NITAAC small business tracks available
- Consider HUBZone, SDVOSB, WOSB set-asides
```

### Scenario 3: Document Template

**User:** "Find a template for market research report"

**Search:** `market research report template FAR 10`

**Response:**
```markdown
### Market Research Report Template (FAR Part 10)

**Location:** data/templates/market-research-template.md

**Key Sections:**
1. Description of Need
2. Sources Consulted
3. Potential Sources Identified
4. Commercial Availability Analysis
5. Small Business Analysis
6. Recommended Acquisition Strategy

**FAR Reference:** FAR 10.002 - Procedures

Would you like me to retrieve the full template?
```

---

## Source Validation

### Always Verify
1. **Currency:** Check if regulation has been updated
2. **Applicability:** Confirm applies to HHS/NIH
3. **Context:** Consider full regulatory context
4. **Precedent:** Note any conflicting interpretations

### Verification Steps
```markdown
**Source:** FAR 6.302-1
**Verified:** Current as of [date]
**Applicability:** All federal agencies including HHS/NIH
**Notes:** Check HHSAR for any supplements

⚠️ For complex regulatory questions, recommend CO/legal review
```

---

## Integration Notes

### From Other Skills

**From OA Intake:**
- Search for similar acquisitions
- Find applicable regulations
- Retrieve templates

**From Compliance:**
- Detailed regulatory research
- Precedent searches
- Policy clarifications

**From Document Generator:**
- Template retrieval
- Clause language
- Standard wording

### Error Handling

When search returns no results:
```markdown
I couldn't find directly relevant documents for that query.

**Suggestions:**
- Try different search terms
- Search for broader topic first
- Check acquisition.gov for current FAR

**For complex questions:**
- Consult with Contracting Officer
- Request legal review
- Contact Competition Advocate
```

---

## Knowledge Base Maintenance

### Content Sources
- acquisition.gov (official FAR/DFARS)
- hhs.gov/grants/contracts (HHSAR)
- nih.gov (NIH-specific policies)
- FPDS.gov (past awards, aggregated)
- Internal lessons learned database

### Update Frequency
- FAR/DFARS: Monthly (when published)
- Policy documents: Quarterly
- Templates: As revised
- Precedents: Continuous addition

### Quality Assurance
- All citations verified against source
- Effective dates tracked
- Superseded content marked
- Cross-references maintained
