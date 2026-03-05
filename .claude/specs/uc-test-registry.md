# EAGLE Use Case → Test Registry

> Maps each use case to its required tests across all 4 test suites.
> Use this to verify UC coverage before releases.

## How to Use

- **Pre-release checklist**: Run all tests tagged for the UCs in scope
- **Gap identification**: Any UC with empty cells needs test development
- **CI integration**: pytest markers can filter by UC tag

## Legend

| Suite | Runner | Cost | Speed |
|-------|--------|------|-------|
| Pytest | `python -m pytest tests/ -v` | $0 | <60s |
| Eval | `python tests/test_strands_eval.py --tests N` | ~$0.50/test | 5-15min |
| Playwright | `npx playwright test` | $0 | 1-5min |
| MCP Browser | `/mcp-browser:eagle-*-test` | $0 | 5-20min |

---

## MVP 1 Use Cases (High Priority)

### UC-01: New Acquisition Package
- **Jira**: EAGLE-3 (epic), EAGLE-4, EAGLE-5, EAGLE-6, EAGLE-8, EAGLE-9, EAGLE-10
- **Actor**: Core (Requester)
- **Pytest**:
  - `test_compliance_matrix.py::TestGetRequirements` (threshold logic, document requirements, compliance items)
  - `test_compliance_matrix.py::TestSuggestVehicle` (vehicle recommendation)
  - `test_compliance_matrix.py::TestExecuteOperation::test_query_dispatches_to_get_requirements`
- **Eval**:
  - Test 9: `test_9_oa_intake_workflow` -- OA intake (CT scanner scenario)
  - Test 10: `test_10_legal_counsel_skill` -- sole source J&A review
  - Test 11: `test_11_market_intelligence_skill` -- vendor research
  - Test 12: `test_12_tech_review_skill` -- SOW requirements translation
  - Test 13: `test_13_public_interest_skill` -- fairness & transparency
  - Test 14: `test_14_document_generator_skill` -- AP generation
  - Test 15: `test_15_supervisor_multi_skill_chain` -- UC-01 end-to-end ($500K IT, 3-year PoP)
  - Test 19: `test_19_document_generation` -- document generation tool
  - Test 35: `test_35_uc01_new_acquisition_package` -- $2.5M CT scanner, negotiated CPFF, 13 docs required, TINA triggered
- **Playwright**:
  - `uc-intake.spec.ts` -- OA intake via quick action, pathway analysis
  - `uc-document.spec.ts` -- SOW generation via quick action
  - `uc-far-search.spec.ts` -- FAR/DFARS search via quick action
  - `intake.spec.ts` -- home page, backend tools/health endpoints
  - `documents.spec.ts` -- documents page structure, filters, cards
  - `workflows.spec.ts` -- acquisition packages page, filter tabs, cards
- **MCP Browser**:
  - `eagle-intake-test` -- full intake journey (quick actions, send, follow-up, session persistence)
  - `eagle-document-test` -- document generation, viewer, refinement, Word download
  - `eagle-specialist-skills-test` -- legal, market, tech review, public interest (mirrors eval 10-13)
  - `eagle-smoke-test` -- end-to-end smoke (phases 3-7: chat, quick action, session, documents, workflows)
- **Status**: COVERED

### UC-02: Micro-Purchase (<$15K Fast Path)
- **Jira**: EAGLE-15
- **Actor**: Core (Requester)
- **Pytest**:
  - `test_compliance_matrix.py::TestGetRequirements::test_micro_purchase_valid` ($10K micro FFP)
  - `test_compliance_matrix.py::TestGetRequirements::test_micro_purchase_exceeds_mpt_error` ($20K error)
  - `test_compliance_matrix.py::TestConstants::test_methods_has_expected_ids` (includes "micro")
- **Eval**:
  - Test 21: `test_21_uc02_micro_purchase` -- $13.8K lab supplies, purchase card, fast path
- **Playwright**:
  - `uc-micro-purchase.spec.ts` -- $13.8K lab supplies, simplified process, purchase request generation
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-02 phase (micro-purchase threshold, purchase card, FAR 13)
- **Status**: COVERED

### UC-03: Option Exercise Package
- **Jira**: EAGLE-20 (epic, acquisition package by type)
- **Actor**: Core/CO
- **Pytest**: ---
- **Eval**:
  - Test 22: `test_22_uc03_option_exercise` -- option year 3, cost escalation, COR change
- **Playwright**:
  - `uc-option-exercise.spec.ts` -- option year 3, NCI-2024-0847, cost escalation, COR change
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-03 phase (option exercise, escalation, COR, package docs)
- **Status**: PARTIAL (no deterministic backend logic to unit test — LLM-driven workflow)

### UC-04: Contract Modification
- **Jira**: EAGLE-17
- **Actor**: Core/CO
- **Pytest**: --- (no deterministic backend logic — LLM-driven workflow)
- **Eval**:
  - Test 23: `test_23_uc04_contract_modification` -- add $150K funding, extend PoP 6 months
- **Playwright**:
  - `uc-contract-modification.spec.ts` -- add $150K, extend PoP 6 months, bilateral mod
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-04 phase (modification type, funding, PoP extension, scope)
- **Status**: PARTIAL (no deterministic backend logic to unit test — LLM-driven workflow)

---

## Phase 2 Use Cases

### UC-05: CO Package Review & Findings
- **Jira**: Related to EAGLE-9 (validate compliance)
- **Actor**: CO
- **Pytest**:
  - `test_compliance_matrix.py::TestGetRequirements` (all compliance/threshold tests support package review)
  - `test_compliance_matrix.py::TestSearchFar` (FAR clause lookup for findings)
- **Eval**:
  - Test 24: `test_24_uc05_co_package_review` -- $487.5K IT, cost mismatch, PoP inconsistency, stale market research, missing FAR 52.219
- **Playwright**: ---
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-05 phase (findings, severity, IGCE mismatch, FAR clause gap)
- **Status**: COVERED

### UC-06: Address Supervisor Findings
- **Jira**: ---
- **Actor**: CO
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

### UC-07: Contract Close-Out
- **Jira**: ---
- **Actor**: CO
- **Pytest**: ---
- **Eval**:
  - Test 25: `test_25_uc07_contract_closeout` -- FAR 4.804 checklist, release of claims, patent/property reports, COR final assessment
- **Playwright**: ---
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-07 phase (FAR 4.804, release of claims, patent, property, COR)
- **Status**: PARTIAL (eval + MCP browser only, no pytest)

### UC-08: Government Shutdown Notification
- **Jira**: ---
- **Actor**: CO
- **Pytest**: ---
- **Eval**:
  - Test 26: `test_26_uc08_shutdown_notification` -- 200+ contracts, 4 categories (FFP continue, incremental stop, CR stop, excepted), email templates
- **Playwright**: ---
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-08 phase (shutdown, FFP, stop work, excepted, templates)
- **Status**: PARTIAL (eval + MCP browser only, no pytest)

---

## Phase 3 Use Cases

### UC-09: Technical Score Sheet Consolidation
- **Jira**: ---
- **Actor**: CO
- **Pytest**: ---
- **Eval**:
  - Test 27: `test_27_uc09_score_consolidation` -- 180 score sheets, 9 reviewers, 20 proposals, variance analysis, question deduplication
- **Playwright**: ---
- **MCP Browser**:
  - `eagle-uc-workflows-test` -- UC-09 phase (score consolidation, evaluation factors, variance, deduplication)
- **Status**: PARTIAL (eval + MCP browser only, no pytest)

### UC-10: Policy Analysis
- **Jira**: ---
- **Actor**: Policy
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

---

## Future Use Cases

### UC-11: Knowledge Base Maintenance
- **Jira**: ---
- **Actor**: System
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

### UC-12: Usage Analysis
- **Jira**: ---
- **Actor**: System
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

### UC-13: FFRDC Modifications
- **Jira**: ---
- **Actor**: CO
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

### UC-14: Conforming Modifications
- **Jira**: ---
- **Actor**: CO (FFRDC)
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

### UC-15: Leadership Dashboard
- **Jira**: ---
- **Actor**: Leadership
- **Pytest**: ---
- **Eval**: ---
- **Playwright**:
  - `admin-dashboard.spec.ts` -- stat cards, quick actions (partial overlap with dashboard metrics)
- **MCP Browser**:
  - `eagle-admin-test` -- admin dashboard, stat cards, system health, cost tracking
- **Status**: PARTIAL (admin dashboard exists but no leadership-specific views)

### UC-16: Solicitation Q&A Processing
- **Jira**: ---
- **Actor**: CO
- **Pytest**: ---
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**: ---
- **Status**: GAP

---

## Cross-Cutting Concerns

### Authentication (EAGLE-1)
- **Pytest**: `test_new_endpoints.py` (REQUIRE_AUTH=false fixture validates auth bypass)
- **Eval**: Test 1 (`test_1_session_creation`) -- session creation with tenant context
- **Playwright**: `navigation.spec.ts` -- backend health/connectivity checks
- **MCP Browser**:
  - `eagle-login-test` -- full login flow (valid/invalid credentials, demo panel, session persistence)
  - `eagle-smoke-test` -- Phase 1 login
  - `eagle-tier-gating-test` -- standard vs premium login, tier labels

### Document Generation (EAGLE-8)
- **Pytest**: `test_compliance_matrix.py::TestGetRequirements` (documents_required lists per scenario)
- **Eval**:
  - Test 14: `test_14_document_generator_skill` -- AP generation
  - Test 19: `test_19_document_generation` -- document creation tool
- **Playwright**:
  - `uc-document.spec.ts` -- SOW generation via quick action
  - `documents.spec.ts` -- documents page structure
- **MCP Browser**:
  - `eagle-document-test` -- full document lifecycle (generate, view, refine, download)

### Compliance Validation (EAGLE-9)
- **Pytest**:
  - `test_compliance_matrix.py` -- all 5 test classes (38 tests total): requirements, FAR search, vehicle suggestion, execute_operation, constants
- **Eval**:
  - Test 24: `test_24_uc05_co_package_review` -- multi-finding compliance review
  - Tests 29-31: compliance matrix query, FAR search, vehicle suggestion
- **Playwright**:
  - `uc-far-search.spec.ts` -- FAR/DFARS search via quick action
- **MCP Browser**: ---

### Session Persistence (EAGLE-21)
- **Pytest**: ---
- **Eval**:
  - Test 1: `test_1_session_creation` -- session creation
  - Test 2: `test_2_session_resume` -- session resume (multi-turn)
- **Playwright**:
  - `session-memory.spec.ts` -- multi-turn memory (APOLLO-PRIME/STARGATE), session_id continuity
- **MCP Browser**:
  - `eagle-session-test` -- session isolation, memory, skill invocation, slash commands
  - `eagle-session-memory-test` -- multi-turn memory (codename recall), session_id consistency, new chat isolation
  - `eagle-smoke-test` -- Phase 5 session persistence, Phase 13 reload persistence

### FAR/Threshold Logic
- **Pytest**:
  - `test_compliance_matrix.py::TestGetRequirements::test_threshold_500k_triggers_sat_not_tina`
  - `test_compliance_matrix.py::TestGetRequirements::test_threshold_3m_triggers_tina`
  - `test_compliance_matrix.py::TestGetRequirements::test_micro_purchase_exceeds_mpt_error`
  - `test_compliance_matrix.py::TestGetRequirements::test_sap_exceeds_sat_error`
  - `test_compliance_matrix.py::TestSearchFar` -- FAR keyword search
  - `test_compliance_matrix.py::TestConstants::test_threshold_tiers_sorted_ascending`
- **Eval**:
  - Tests 29-31: compliance matrix operations (query, search_far, suggest_vehicle)
- **Playwright**:
  - `uc-far-search.spec.ts` -- FAR search via quick action
- **MCP Browser**: ---

### Feedback
- **Pytest**:
  - `test_new_endpoints.py::TestFeedbackEndpoints` -- POST/GET /api/feedback (5 tests)
  - `test_feedback_store.py` -- feedback store unit tests
- **Eval**: ---
- **Playwright**: ---
- **MCP Browser**:
  - `eagle-feedback-test` -- Ctrl+J modal, type pills, submit, cancel, reset

### Tier Gating
- **Pytest**: ---
- **Eval**:
  - Test 6: `test_6_tier_gated_tools` -- tier-gated tool access
- **Playwright**: ---
- **MCP Browser**:
  - `eagle-tier-gating-test` -- standard vs premium tier labels, mcp_server_access, admin dashboard access

### Subagent Orchestration
- **Pytest**: ---
- **Eval**:
  - Test 4: `test_4_subagent_orchestration` -- agents-as-tools dispatch
  - Test 7: `test_7_skill_loading` -- skill loading via system_prompt
  - Test 8: `test_8_subagent_tool_tracking` -- subagent tool tracking
  - Test 15: `test_15_supervisor_multi_skill_chain` -- multi-skill chain
  - Test 28: `test_28_strands_skill_tool_orchestration` -- Strands architecture
  - Test 32: `test_32_admin_manager_skill_registered` -- admin-manager skill registration
- **Playwright**: ---
- **MCP Browser**: ---

### AWS Infrastructure (S3, DynamoDB, CloudWatch)
- **Pytest**: ---
- **Eval**:
  - Test 5: `test_5_cost_tracking` -- cost/usage tracking
  - Test 16: `test_16_s3_document_ops` -- S3 document operations
  - Test 17: `test_17_dynamodb_intake_ops` -- DynamoDB intake operations
  - Test 18: `test_18_cloudwatch_logs_ops` -- CloudWatch logs
  - Test 20: `test_20_cloudwatch_e2e_verification` -- CloudWatch end-to-end
- **Playwright**: ---
- **MCP Browser**: ---

### Chat UI & Edge Cases
- **Pytest**:
  - `test_new_endpoints.py::TestFastTrivialRegex` -- trivial message regex detection
  - `test_new_endpoints.py::TestFastTrivialFunction` -- fast path with mocked Bedrock
  - `test_new_endpoints.py::TestGenerateTitle` -- session title generation
- **Eval**:
  - Test 3: `test_3_trace_observation` -- response structure validation
- **Playwright**:
  - `chat.spec.ts` -- chat page structure, new chat welcome, submit button state
  - `chat-features.spec.ts` -- chat feature tests
  - `keyboard-shortcuts.spec.ts` -- keyboard shortcut tests
- **MCP Browser**:
  - `eagle-chat-test` -- single message send/receive, streaming, response count validation
  - `eagle-edge-cases-test` -- empty/whitespace guards, streaming lock, Shift+Enter, long message (2000+ chars)
  - `eagle-command-palette-test` -- Ctrl+K palette, search, select

### Admin Dashboard
- **Pytest**: ---
- **Eval**:
  - Test 33: `test_33_workspace_store_default_creation` -- workspace store
  - Test 34: `test_34_store_crud_functions_exist` -- store CRUD smoke test
- **Playwright**:
  - `admin-dashboard.spec.ts` -- dashboard overview, metrics cards, quick actions, system health
  - `admin-workspaces.spec.ts` -- admin workspaces page
  - `admin-skills.spec.ts` -- admin skills page
  - `admin-templates.spec.ts` -- admin templates page
- **MCP Browser**:
  - `eagle-admin-test` -- admin dashboard, stat cards, system health, user management, cost tracking
  - `eagle-admin-workspaces-test` -- workspace list, create, activate, overrides
  - `eagle-admin-skills-test` -- skills tabs, bundled skills, custom skill creation
  - `eagle-admin-templates-test` -- template list, filter by type, custom template creation

---

## Coverage Summary Table

| UC | Phase | Pytest | Eval | Playwright | MCP Browser | Status |
|----|-------|--------|------|------------|-------------|--------|
| UC-01 | MVP 1 | 16 tests (compliance) | 9, 10, 11, 12, 13, 14, 15, 19 | uc-intake, uc-document, uc-far-search, intake, documents, workflows | intake, document, specialist-skills, smoke | COVERED |
| UC-02 | MVP 1 | 3 tests (micro thresholds) | 21 | uc-micro-purchase | uc-workflows | COVERED |
| UC-03 | MVP 1 | --- | 22 | uc-option-exercise | uc-workflows | PARTIAL |
| UC-04 | MVP 1 | --- | 23 | uc-contract-modification | uc-workflows | PARTIAL |
| UC-05 | Phase 2 | compliance tests | 24 | --- | uc-workflows | COVERED |
| UC-06 | Phase 2 | --- | --- | --- | --- | GAP |
| UC-07 | Phase 2 | --- | 25 | --- | uc-workflows | PARTIAL |
| UC-08 | Phase 2 | --- | 26 | --- | uc-workflows | PARTIAL |
| UC-09 | Phase 3 | --- | 27 | --- | uc-workflows | PARTIAL |
| UC-10 | Phase 3 | --- | --- | --- | --- | GAP |
| UC-11 | Future | --- | --- | --- | --- | GAP |
| UC-12 | Future | --- | --- | --- | --- | GAP |
| UC-13 | Future | --- | --- | --- | --- | GAP |
| UC-14 | Future | --- | --- | --- | --- | GAP |
| UC-15 | Future | --- | --- | admin-dashboard | admin-test | PARTIAL |
| UC-16 | Future | --- | --- | --- | --- | GAP |

**Summary**: 3 COVERED, 6 PARTIAL, 7 GAP

---

## Jira → UC Mapping Reference

| Jira Key | Summary | UC |
|----------|---------|-----|
| EAGLE-1 | User Authentication and Role Selection | Cross-cutting (Auth) |
| EAGLE-2 | Display COR Acquisition Options | UC-01 |
| EAGLE-3 | UC-1 Create an acquisition package (Epic) | UC-01 |
| EAGLE-4 | Initiate a New Acquisition Package | UC-01 |
| EAGLE-5 | Capture Core Acquisition Data | UC-01 |
| EAGLE-6 | Handle Incomplete or Unknown Acquisition Data | UC-01 |
| EAGLE-7 | Chat with CO via Teams | Cross-cutting (Comms) |
| EAGLE-8 | Generate Acquisition Documentation | UC-01 (Doc Gen) |
| EAGLE-9 | Validate Acquisition Package for Compliance | UC-01 / UC-05 |
| EAGLE-10 | Download Acquisition Package | UC-01 |
| EAGLE-11 | Store Acquisition Package in SharePoint | UC-01 (future) |
| EAGLE-12 | Handle CO Return for Revision | UC-06 |
| EAGLE-13 | Audit Trail and Status Tracking | Cross-cutting |
| EAGLE-14 | Submit Package hyperlink to CO via Teams | Cross-cutting (Comms) |
| EAGLE-15 | Rapid GSA Schedule Purchase -- Micro Purchase | UC-02 |
| EAGLE-16 | New IT Services Acquisition -- Full Package | UC-01 |
| EAGLE-17 | Contract Modification Request | UC-04 |
| EAGLE-18 | Rapid GSA Schedule Purchase -- under SAT | UC-02 variant |
| EAGLE-19 | Configure Dedicated System Domain | UC-22 (Technical Config) |
| EAGLE-20 | Acquisition Package by Type (Epic) | UC-03 |
| EAGLE-21 | Session Persistence for User Conversations | Cross-cutting (Sessions) |
| EAGLE-22 | Technical Configuration (Epic) | Cross-cutting (Admin) |
| EAGLE-27 | Sole Source Justification < SAT | UC-01 variant |
| EAGLE-28 | Data Rights Determination | UC-01 variant |
| EAGLE-29 | IGCE Development for Complex Services | UC-01 variant |
