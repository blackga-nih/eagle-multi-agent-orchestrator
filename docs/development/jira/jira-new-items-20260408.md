# New EAGLE Jira Items — 2026-04-08

> Prepared from requested follow-up work items. Covers schema propagation, documentation refresh, and console resource audit.

---

## Proposed Tickets

### EAGLE-{TBD}: Enforce Canonical Schema Propagation for AI-Generated Data

- **Type**: Story
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Define and enforce a canonical schema for AI-generated data so approved keys and structure propagate across the app
- **Status**: To Do
- **Priority**: P1
- **Effort**: M
- **Assignee**: Unassigned
- **Expert Domain**: `backend`, `frontend`, `ai-schema`, `validation`
- **Description**: AI-generated structured data is currently inconsistent across the application. We are seeing schema drift in field names, casing, and labels, such as lowercase `sow` and unexpected variants like `Son` or `Sb Review`, because the AI is redefining keys instead of adhering to an approved schema. This creates instability in downstream systems that depend on predictable keys and structure, including backend processing, persistence, API responses, frontend rendering, filtering, and reporting. This task is to define and enforce a canonical schema for AI-generated data, then propagate that schema throughout the application so all producers and consumers use the same approved keys, casing, and structure.
- **Acceptance Criteria**:
  - [ ] A canonical schema is defined for the relevant AI-generated payloads
  - [ ] Approved keys, casing, enums, and nested structure are documented
  - [ ] AI output is constrained or validated against the canonical schema
  - [ ] Non-canonical keys are rejected, mapped, or normalized in a controlled way
  - [ ] Backend and frontend consumers are updated to rely on the canonical schema
  - [ ] Existing inconsistent key usage is identified and cleaned up where required
  - [ ] Tests cover schema validation and propagation behavior
- **Engineering Task Description**: Audit current AI-produced payloads, define the source-of-truth schema, update prompt/tool/output contracts so AI emits only approved keys, and add normalization plus validation at system boundaries before data is persisted or consumed. Refactor backend contracts and frontend types to use the canonical structure and add regression coverage to prevent future schema drift.

---

### EAGLE-{TBD}: Regenerate CI/CD Pipeline Documentation and Refresh README

- **Type**: Task
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Review the current CI/CD pipeline and update README plus related docs so they match the live system
- **Status**: To Do
- **Priority**: P2
- **Effort**: S
- **Assignee**: Unassigned
- **Expert Domain**: `docs`, `ci-cd`, `deployment`, `developer-experience`
- **Description**: Project documentation may no longer accurately reflect the current CI/CD pipeline, setup flow, and developer workflow. This task is to review the existing pipeline and repository documentation, then regenerate or rewrite the relevant docs so they match the current implementation and are useful for onboarding, development, and deployment. This should include the main `README` and any documentation that explains build, test, deploy, environments, and release flow.
- **Acceptance Criteria**:
  - [ ] Current CI/CD pipeline behavior is reviewed and documented accurately
  - [ ] `README` is updated to reflect the current project setup and workflow
  - [ ] Outdated or misleading pipeline and setup documentation is removed or corrected
  - [ ] Key developer and deployment steps are clearly documented
  - [ ] Documentation is consistent with the current repository and deployment behavior
- **Engineering Task Description**: Audit current CI/CD behavior and repository onboarding docs, then update the `README` and related documentation so they accurately describe setup, testing, deployment flow, environments, and operational expectations.

---

### EAGLE-{TBD}: Audit Console Resources for Orphaned Entries and Duplicates

- **Type**: Task
- **Epic**: [EAGLE-22] Technical Configuration
- **Summary**: Review console resources to identify orphaned, stale, or duplicate entries and produce a cleanup plan
- **Status**: To Do
- **Priority**: P2
- **Effort**: M
- **Assignee**: Unassigned
- **Expert Domain**: `aws`, `operations`, `infrastructure`, `cost-control`
- **Description**: We need to review the console and environment for stale, orphaned, or duplicated resources that may have accumulated over time. These can create confusion, operational risk, unnecessary cost, or misleading system state. This task is to inspect the current console resources, identify duplicates or resources no longer attached to active workflows, and document or clean up what should be retained versus removed.
- **Acceptance Criteria**:
  - [ ] Console resources are reviewed across the relevant environment or environments
  - [ ] Orphaned resources are identified and documented
  - [ ] Duplicate resources are identified and documented
  - [ ] A clear recommendation is made for cleanup, retention, or consolidation
  - [ ] Any approved cleanup is completed safely, or follow-up tasks are created
- **Engineering Task Description**: Perform an environment audit to identify orphaned, stale, or duplicate resources in the console, determine which resources are still actively in use, and produce a cleanup or consolidation plan with low-risk next actions.
