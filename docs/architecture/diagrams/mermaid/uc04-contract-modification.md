# UC-04: Contract Modification Request

**Use Case:** Add funding and extend period of performance on existing contract
**Key Pattern:** Different entry point (existing contract), Compliance validation, parallel document generation
**Actors:** COR/CO, Supervisor Agent, OA Intake Skill, Compliance Agent, Document Generator Skill

```mermaid
sequenceDiagram
    actor User as COR / CO
    participant UI as Eagle UI
    participant Sup as Supervisor Agent
    participant Intake as OA Intake Skill
    participant Comp as Compliance Agent
    participant DocGen as Document Generator Skill
    participant S3 as S3 / Package Store

    Note over User,S3: UC-04: Contract Modification Request

    User->>UI: "I need to modify contract HHSN261201500003I"
    UI->>Sup: New session - modification intent
    Sup->>Sup: Detect intent: contract modification
    Sup->>Intake: Delegate (modification mode)

    rect rgb(240, 248, 255)
        Note over Intake: Modification Type Collection
        Intake->>UI: "What type of modification?"
        Note right of Intake: ○ Add funding<br/>○ Extend period of performance<br/>○ Change scope<br/>○ Administrative change<br/>○ Multiple changes
        User->>UI: "Add funding and extend PoP by 6 months"
        UI->>Intake: Modification details
    end

    rect rgb(245, 255, 245)
        Note over Intake: Modification Details
        Intake->>UI: "How much additional funding?"
        User->>UI: "$150K for FY2026"
        Intake->>UI: "New end date?"
        User->>UI: "September 30, 2027"
        Intake->>UI: "Is this within the existing scope?"
        User->>UI: "Yes, same work continuing"
    end

    Intake->>Intake: Determine: bilateral mod,<br/>within scope, no J&A needed

    rect rgb(255, 245, 255)
        Note over Sup,Comp: Compliance Validation
        Sup->>Comp: Validate modification approach
        Comp->>Comp: Check FAR compliance:<br/>- Within scope? ✓ No J&A<br/>- Funding type valid? ✓<br/>- Option exercise or new funds?<br/>- Bilateral vs unilateral?
        Comp->>Sup: Validated: Standard bilateral mod<br/>No additional justifications needed
    end

    Sup->>DocGen: Generate modification package

    par Generate Documents in Parallel
        DocGen->>DocGen: Modification Cover Page (SF-30)
        DocGen->>DocGen: Updated IGCE (cost mod)
        DocGen->>DocGen: Funds Certification
        DocGen->>DocGen: Updated AP (if needed)
    end

    DocGen->>S3: Store modification package
    S3-->>DocGen: Download URLs

    DocGen->>UI: Package ready
    UI->>User: Modification package:<br/>✓ SF-30 Mod Cover Page<br/>✓ Updated IGCE<br/>✓ Funds Certification<br/>✓ COR Recommendation Memo

    Note over UI: Checklist: All items ✓<br/>Ready for CO signature
```
