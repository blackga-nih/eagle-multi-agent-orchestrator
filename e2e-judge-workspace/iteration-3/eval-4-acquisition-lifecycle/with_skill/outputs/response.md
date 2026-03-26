# E2E Judge: Full Acquisition Package Lifecycle Test

## 1. Exact Command to Run

```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys acquisition_package
```

If running from the EC2 dev box inside the VPC, the above internal ALB URL is correct. For local development testing against a local frontend, substitute `--base-url http://localhost:3000`.

Optional flags to consider:
- `--headed` to watch the browser window during execution (useful for debugging)
- `--purge-cache` to force fresh Sonnet evaluations for every screenshot
- `--upload-s3` to push results to S3 for the `/admin/e2e-judge` dashboard
- `-v` for verbose logging
- `--output <dir>` to customize the output directory

---

## 2. Why Credentials Are NOT Passed on the Command Line

The test user credentials (`EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD`) are read from **environment variables**, not passed as CLI arguments. This is by design for three reasons:

1. **Security**: Command-line arguments are visible in `ps` output, shell history (`~/.bash_history`), and process listings. Environment variables are scoped to the process and not logged by default.
2. **CI/CD compatibility**: In GitHub Actions or other CI pipelines, secrets are injected as environment variables, never as plaintext arguments.
3. **Convenience**: The orchestrator checks `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` environment variables automatically. The `--auth-email` and `--auth-password` flags exist as overrides but should only be used for one-off debugging.

Since the task states that `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` are already set in the environment, the orchestrator will pick them up automatically without any additional flags. The credentials authenticate against the Cognito user pool `us-east-1_ChGLHtmmp` (the `eagle-users-dev` pool).

---

## 3. All 7 Phases of the `acquisition_package` Journey

The `acquisition_package` journey is defined in `server/tests/e2e_judge_journeys.py` and tests the complete UC-1 acquisition lifecycle. It involves **7 user messages** sent across **6 distinct phases**, plus navigation checks on the `/workflows` page. Here is the detailed breakdown:

### Phase 1: Intake (Messages 1 and 2)

**Message 1 -- Acquisition Intake ($750K Cloud Hosting)**

The journey starts by navigating to `/chat/`, clicking "New Chat" if available, and typing:

> "I need to procure cloud hosting services for our research data platform. Estimated value around $750,000."

This represents the initial intake for a large, above-SAT (Simplified Acquisition Threshold) procurement. EAGLE's supervisor agent routes this to the intake specialist, which asks clarifying questions about contract type, period of performance, competition strategy, security requirements, and existing vehicles.

**Message 2 -- Clarifying Question Answers**

The user responds with detailed acquisition parameters:

> "3-year base period plus 2 option years, starting October 2026. No existing vehicles -- new standalone contract. We need FedRAMP High for PII and genomics research data. Full and open competition preferred. Fixed-price."

EAGLE processes these details and returns a **compliance analysis**: the recommended acquisition pathway (full and open FAR Part 15 negotiated procurement given the $750K value), applicable thresholds (above SAT at $250K, below TINA at $750K), and identifies the required document set (SOW, IGCE, Market Research Report, Acquisition Plan). The journey captures both the initial response and a scrolled view to verify the full compliance analysis and document checklist are visible.

### Phase 2: Document Generation (Messages 3 and 4)

**Message 3 -- SOW Generation**

> "Generate the Statement of Work for this cloud hosting acquisition."

EAGLE invokes the document generation subagent, which calls the `create_document` tool to produce a Statement of Work. The SOW is generated based on the intake details: cloud hosting for research data, FedRAMP High, 3+2 year period, fixed-price. The journey waits up to **180 seconds** (3 minutes) for this step, capturing 30-second interval screenshots during the streaming wait. After completion, it captures the tool result card with the document link.

**Message 4 -- Remaining Documents (IGCE, Market Research, Acquisition Plan)**

> "Now generate the IGCE, Market Research Report, and Acquisition Plan."

This triggers generation of three documents in sequence. The wait timeout is extended to **300 seconds** (5 minutes) since generating three documents takes significantly longer. The journey captures interval screenshots every 30 seconds during this extended wait, then captures the final state showing all tool result cards.

### Phase 3: Document Checklist Check (Navigation)

No chat message is sent in this phase. Instead, the journey:

1. **Checks the Documents tab** in the chat's activity panel (right sidebar) if a "Documents" tab button is visible. This shows the in-chat document checklist with status indicators per document type.
2. **Navigates to `/workflows`** to see the package card. The workflows page shows acquisition package cards with progress indicators.
3. **Clicks on the package card** matching "cloud" or "Cloud" or "hosting" to open the detail modal, which displays the per-document checklist with completed/pending status for each document type (SOW, IGCE, MR, AP).
4. Closes the modal.

### Phase 4: Document Revision (Message 5)

**Message 5 -- SOW v2 Revision (Section 508 + FedRAMP)**

The journey navigates back to `/chat/`, scrolls to the bottom of the conversation, and sends:

> "The SOW needs a Section 508 accessibility requirement added under the technical requirements. Also add FedRAMP High authorization as a mandatory contractor qualification. Please regenerate it."

This tests the revision workflow: EAGLE must understand the existing SOW context, apply the two requested changes (Section 508 accessibility compliance and FedRAMP High as a mandatory contractor qualification), and regenerate the SOW as version 2. The timeout is 180 seconds. The completed screenshot verifies the v2 SOW with the added requirements.

### Phase 5: Package Finalization (Message 6)

**Message 6 -- Finalize the Package**

> "Finalize the acquisition package. All documents are ready for review."

This tells EAGLE to finalize the package. The finalization step validates completeness (all required documents have been generated), updates the package status from "in-progress" to "finalized" or "ready for review," and confirms that the compliance requirements are satisfied. The journey waits up to 120 seconds and captures the finalization response showing the status update and compliance validation summary.

### Phase 6: Export and Final Verification (Message 7 + Navigation)

**Message 7 -- ZIP Export**

> "Export the complete acquisition package as a ZIP file."

This requests EAGLE to bundle all generated documents into a downloadable ZIP archive. The response includes a ZIP download link or instructions, and may reference a `manifest.json` file that catalogs the package contents (document names, versions, generation timestamps). The journey captures the export response showing the download mechanism.

**Final Workflows Page Check**

After the export message, the journey navigates back to `/workflows` to verify:
1. The package card reflects the updated status (finalized/exported).
2. Opens the package detail modal one more time to see the final state with all documents completed and the package status showing as finalized or exported.

**Full Conversation Screenshot**

Finally, the journey navigates back to `/chat/`, scrolls to the bottom, and captures the full multi-turn conversation showing all 7 exchanges.

---

## 4. Screenshot Strategy

The `acquisition_package` journey uses a deliberate, multi-layered screenshot strategy:

### Pre-Send Captures

Before **each** of the 7 user messages, a screenshot is taken with the message typed into the textarea but not yet sent. These "pre-send" screenshots serve as:
- Visual proof that the correct message content was composed
- Baseline for the UI state before each interaction
- Step names follow the pattern `XX_pre_send_{purpose}` (e.g., `02_pre_send_intake`, `06_pre_send_details`, `10_pre_send_sow`, etc.)

There are **7 pre-send screenshots** total (one per message).

### 30-Second Interval Captures During Streaming

During each streaming wait, the `wait_with_interval_screenshots()` utility captures a screenshot every **30 seconds** until the response completes (detected by the textarea becoming enabled again) or the timeout is reached. These interval screenshots:

- Show streaming progress (partial responses, tool execution cards appearing)
- Provide evidence of reasonable response times
- Step names follow the pattern `XX_{a,b,c,...}_interval_{elapsed}s`
- Suffixes cycle through `a, b, c, ...` for each interval shot within a single wait

The number of interval screenshots varies by phase:
- Short responses (intake, clarifying): 0-2 interval shots (~30-60s)
- SOW generation: 1-4 interval shots (up to 180s timeout)
- Multi-doc generation: 2-8 interval shots (up to 300s timeout)
- Revision, finalize, export: 0-3 interval shots each

### Post-Completion Captures

After each response completes, a screenshot is taken showing the final response. Some steps also include a "scrolled" variant to capture content below the fold (e.g., `09_compliance_scrolled`).

### Navigation Captures

Screenshots are taken at each page navigation point: the `/workflows` page, package detail modal, and the final full-conversation view.

---

## 5. Approximate Screenshot Count (25-35+)

The journey produces approximately **25-35+ screenshots**. Here is the step-by-step breakdown:

| Step | Screenshot Name(s) | Count |
|------|-------------------|-------|
| Chat ready | `01_chat_ready` | 1 |
| Pre-send intake | `02_pre_send_intake` | 1 |
| Intake streaming | `03_intake_streaming` | 1 |
| Intake wait intervals | `04_{a,b,...}_interval_*` | 0-2 |
| Intake response | `05_intake_response` | 1 |
| Pre-send details | `06_pre_send_details` | 1 |
| Compliance wait intervals | `07_{a,b,...}_interval_*` | 0-2 |
| Compliance response | `08_compliance_response` | 1 |
| Compliance scrolled | `09_compliance_scrolled` | 1 |
| Pre-send SOW | `10_pre_send_sow` | 1 |
| SOW streaming | `11_sow_streaming` | 1 |
| SOW wait intervals | `12_{a,b,...}_interval_*` | 1-4 |
| SOW complete | `13_sow_complete` | 1 |
| SOW tool cards | `14_sow_tool_cards` | 0-1 |
| Pre-send remaining | `15_pre_send_remaining` | 1 |
| Multi-doc wait intervals | `16_{a,b,...}_interval_*` | 2-8 |
| All docs complete | `17_all_docs_complete` | 1 |
| Checklist panel | `18_checklist_panel` | 0-1 |
| Workflows page | `19_workflows_page` | 1 |
| Package detail modal | `20_package_detail` | 0-1 |
| Pre-send revision | `21_pre_send_revision` | 1 |
| Revision wait intervals | `22_{a,b,...}_interval_*` | 1-3 |
| SOW v2 complete | `23_sow_v2_complete` | 1 |
| Pre-send finalize | `24_pre_send_finalize` | 1 |
| Finalize wait intervals | `25_{a,b,...}_interval_*` | 0-2 |
| Finalize response | `26_finalize_response` | 1 |
| Pre-send export | `27_pre_send_export` | 1 |
| Export wait intervals | `28_{a,b,...}_interval_*` | 0-2 |
| Export response | `29_export_response` | 1 |
| Final workflows | `30_final_workflows` | 1 |
| Final package detail | `31_final_package_detail` | 0-1 |
| Full conversation | `32_full_conversation` | 1 |
| **Total** | | **~25-35+** |

### Why This Journey Is Significantly Longer Than Others

The `acquisition_package` journey is the longest journey in the suite for several reasons:

1. **7 chat turns vs. 2**: The `chat` journey sends 2 messages; this one sends 7. Each message requires a send, a streaming wait, and a completion capture.
2. **Extended timeouts**: Document generation steps have timeouts of 180-300 seconds (vs. 120 seconds for simple chat), reflecting real-world generation times for complex procurement documents.
3. **Multi-document generation**: Message 4 triggers generation of 3 documents simultaneously, which can take up to 5 minutes.
4. **Page navigation**: The journey leaves the chat page twice to check `/workflows`, adding navigation wait time and additional screenshots.
5. **Total runtime**: Expected wall-clock time is **10-15 minutes**, compared to ~2-3 minutes for the `chat` journey or ~30 seconds for `login`.
6. **Interval screenshots accumulate**: With 7 streaming waits and 30-second intervals, the number of interval screenshots can vary widely depending on agent response speed.

---

## 6. Cost Estimate

### Vision Judge Costs (Sonnet evaluating screenshots)
- ~30 screenshots at ~$0.004 per screenshot = **~$0.12**
- Cached repeat runs: **$0** (SHA-256 hash match skips Sonnet calls)

### EAGLE App Costs (Haiku 4.5 responding during the test)
- 7 chat turns, some involving document generation tool calls
- Haiku 4.5 at ~$0.001/response for simple responses, more for document generation
- Estimated: **~$0.02-0.05** for app-side inference

### Total for a Single Run
- First run (no cache): **~$0.14-0.17**
- Cached repeat run (identical UI renders): **~$0.02-0.05** (only app costs, no judge costs)

### Full Suite with acquisition_package
- The SKILL.md estimates ~$0.30 + app costs for a full run with all journeys (~70+ screenshots total)
- Running `acquisition_package` alone is roughly half of the total suite cost

---

## 7. Output Files

The orchestrator produces three categories of output, all under the `data/e2e-judge/` directory at the repository root:

### Results JSON
- **Path**: `data/e2e-judge/results/{run-id}.json` (also copied to `latest.json`)
- **Contents**: Structured run results including:
  - Run metadata (run ID, timestamp, base URL, journeys executed)
  - Per-screenshot judgments: verdict (pass/fail), confidence (0-1), reasoning, UI quality score (1-10), issues list
  - Aggregate statistics: total screenshots, pass/fail counts, average quality score
  - Cache hit/miss counts

### Markdown Report
- **Path**: `data/e2e-judge/results/{run-id}-report.md`
- **Contents**: Human-readable summary of the run with:
  - Overall pass/fail status
  - Per-journey breakdown
  - Per-screenshot verdict table
  - Issues and recommendations
  - Cost breakdown

### Screenshots Directory
- **Path**: `data/e2e-judge/screenshots/{run-id}/acquisition_package/{step}.png`
- **Contents**: Full-page PNG screenshots at 1440x900 viewport, one per captured step
- **Naming**: Step names like `01_chat_ready.png`, `02_pre_send_intake.png`, `13_sow_complete.png`, etc.

### Judge Cache
- **Path**: `data/e2e-judge/cache/{sha256}.json`
- **Contents**: Cached Sonnet judgments keyed by the SHA-256 hash of each screenshot's pixel data
- **TTL**: 7 days by default (configurable via `E2E_JUDGE_CACHE_TTL_DAYS`)

If `--upload-s3` is used, results and screenshots are also pushed to the S3 eval bucket, viewable at `/admin/e2e-judge` on the deployed app.

---

## 8. What the Document Checklist Check Verifies

The document checklist check (Phase 3, steps 18-20) verifies two things:

### In-Chat Documents Panel (Step 18)
If a "Documents" tab exists in the chat's right-side activity panel, the journey clicks it and captures the panel. This verifies:
- The panel lists generated documents with their types (SOW, IGCE, MR, AP)
- Status indicators show which documents are completed vs. pending
- The panel is populated (not empty) after document generation

### Workflows Page Package Card (Steps 19-20)
The journey navigates to `/workflows` and:

1. **Captures the workflows page** (step 19): Verifies the acquisition package appears as a card with a progress indicator (e.g., "4/4 documents generated" or a progress bar).

2. **Opens the package detail modal** (step 20): Clicks on the package card matching "cloud"/"Cloud"/"hosting" text. The modal displays:
   - **Per-document checklist**: Each document type (SOW, IGCE, Market Research Report, Acquisition Plan) with a completed/pending status indicator
   - **Package metadata**: Title, estimated value, contract type, period of performance
   - **Overall package status**: Current state (e.g., "in progress", "documents complete")

The Sonnet vision judge evaluates these screenshots for correctness: are all 4 document types listed? Do the status indicators show "completed" for all generated documents? Is the package card present and properly formatted?

---

## 9. What the Finalize Step Does

The finalize step (Phase 5, Message 6) tests the package finalization workflow:

1. **User sends**: "Finalize the acquisition package. All documents are ready for review."

2. **EAGLE processes the request** through the supervisor, which routes to the appropriate subagent. The finalization process:
   - **Validates completeness**: Checks that all required documents for the acquisition pathway have been generated (SOW, IGCE, Market Research Report, Acquisition Plan for a full-and-open above-SAT procurement)
   - **Checks compliance**: Verifies that the documents meet the identified regulatory requirements (FAR/DFARS applicability, competition requirements, security requirements like FedRAMP High)
   - **Updates package status**: Changes the package status from "in progress" or "documents complete" to "finalized" or "ready for review"
   - **Returns a summary**: The response confirms what was validated, lists the finalized document set with versions, and states the new package status

3. **The screenshot** (step 26, `26_finalize_response`) captures this finalization response, and the Sonnet judge evaluates whether the response indicates successful finalization with appropriate status messaging.

The final workflows page check (Phase 6, step 30-31) then verifies that the status change persists on the `/workflows` page, confirming the backend actually updated the package record.

---

## 10. What the Export Step Tests

The export step (Phase 6, Message 7) tests the package export/download workflow:

1. **User sends**: "Export the complete acquisition package as a ZIP file."

2. **EAGLE processes the export request**, which involves:
   - Collecting all generated documents for the package (SOW v2, IGCE, Market Research Report, Acquisition Plan)
   - Bundling them into a ZIP archive
   - Generating a **`manifest.json`** file inside the ZIP that catalogs the package contents: document names, types, versions, generation timestamps, and package metadata
   - Providing a download link or download mechanism to the user

3. **The screenshot** (step 29, `29_export_response`) captures the export response, which should show:
   - A ZIP download link or button
   - A mention of `manifest.json` or package manifest
   - A list of included documents
   - File size or document count information

4. **What the Sonnet judge evaluates**:
   - Does the response indicate a successful export?
   - Is a download mechanism visible (link, button, or file reference)?
   - Is the package contents listing present?
   - Are all expected documents included in the export?

The export step is the final functional test of the acquisition lifecycle before the journey performs its closing verification screenshots on the `/workflows` page and the full conversation view.

---

## Summary

The `acquisition_package` journey is the most comprehensive E2E test in the EAGLE suite. It validates the entire UC-1 use case from initial procurement intake through document generation, revision, finalization, and export -- covering 7 chat interactions, 2 page navigation checks, and 25-35+ screenshots over approximately 10-15 minutes. The LLM-as-judge evaluation via Sonnet ensures not just functional correctness (documents get generated, statuses update) but also UI quality (layout, readability, proper rendering of tool cards and status indicators).
