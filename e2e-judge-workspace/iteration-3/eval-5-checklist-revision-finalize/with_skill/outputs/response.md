# E2E Judge: Document Checklist + Revision + Finalize Testing

## Yes -- the `acquisition_package` journey covers exactly this use case

The `acquisition_package` journey is a full UC-1 lifecycle test that runs through intake, document generation, checklist verification, revision, finalization, and export. The specific flow you are asking about -- verifying the document checklist shows the right status, then testing revision and finalize -- is covered in Phases 3 through 5 of this journey (steps 18-26 in the screenshot sequence).

You do not need to write a new journey or modify anything. The existing journey handles it end to end.

---

## How the journey works, step by step

### Phase 1-2: Intake + Document Generation (steps 01-17)

Before we can verify the checklist, the journey generates all four documents:

1. **Intake** (steps 01-09): Starts a new chat session, sends a $750K cloud hosting procurement request, answers clarifying questions (3-year base + 2 option years, FedRAMP High, full and open competition, fixed-price), and receives a compliance analysis identifying the required documents.

2. **SOW generation** (steps 10-14): Sends "Generate the Statement of Work for this cloud hosting acquisition." Waits up to 3 minutes for the SOW to generate with 30-second interval screenshots. Captures the tool result card showing the `create_document` call.

3. **IGCE + MR + AP generation** (steps 15-17): Sends "Now generate the IGCE, Market Research Report, and Acquisition Plan." Waits up to 5 minutes (these three docs generate in sequence). Captures the final state showing all four tool result cards.

### Phase 3: Document Checklist Verification (steps 18-20) -- `/workflows` page

This is the first part of what you are asking about. After all four documents are generated, the journey verifies the checklist in two places:

1. **In-chat Documents tab** (step 18): Clicks the "Documents" tab in the activity panel on the right side of the chat interface. Screenshots the document checklist panel, which shows status indicators (completed/pending) for each generated document type.

2. **`/workflows` page** (steps 19-20): Navigates to `{base_url}/workflows`. This is the dedicated package management page that shows:
   - The acquisition package card with an overall progress indicator
   - A per-document-type checklist (SOW, IGCE, Market Research, Acquisition Plan) with completed/pending status for each

   The journey then clicks on the package card (matching on "cloud" or "hosting" text) to open the **package detail modal**, which displays the full document checklist with completed/pending status for every document type. This is step 20 (`20_package_detail`), and the vision judge evaluates whether the checklist correctly shows all four documents as completed.

### Phase 4: Revision Flow (steps 21-23) -- SOW v2 with Section 508 + FedRAMP

After verifying the checklist, the journey goes back to the chat and tests document revision:

1. **Navigate back to chat** (step 21): Returns to `/chat/`, scrolls to the bottom of the existing conversation.

2. **Send revision request**: Types the following message:

   > "The SOW needs a Section 508 accessibility requirement added under the technical requirements. Also add FedRAMP High authorization as a mandatory contractor qualification. Please regenerate it."

   This tests two specific additions:
   - **Section 508 accessibility** -- added as a technical requirement in the SOW
   - **FedRAMP High authorization** -- added as a mandatory contractor qualification

3. **Wait for SOW v2** (steps 22-23): Waits up to 3 minutes with 30-second interval screenshots. The agent should regenerate the SOW as version 2 (the artifact naming convention `v2` prevents overwriting the original). Step 23 (`23_sow_v2_complete`) captures the final state and the vision judge evaluates whether the revision completed successfully.

### Phase 5: Finalize Flow (steps 24-26)

The finalize step tests the package completion workflow:

1. **Send finalize message** (step 24): Types:

   > "Finalize the acquisition package. All documents are ready for review."

2. **Wait for finalize response** (steps 25-26): Waits up to 2 minutes. The agent should:
   - Validate package completeness (all required documents present)
   - Update the package status (from "in_progress" to "finalized" or similar)
   - Confirm compliance checks pass

3. **Capture finalize result** (step 26 -- `26_finalize_response`): The vision judge checks that the response confirms status update and compliance validation.

### Phase 6: Final Verification (steps 27-32) -- Export + `/workflows` re-check

After finalization, the journey does a final round of verification:

1. **Export request** (steps 27-29): Asks EAGLE to export the package as a ZIP file.
2. **Final `/workflows` check** (steps 30-31): Navigates back to `/workflows` to verify the package status has been updated post-finalization. Opens the package detail modal one more time to confirm all documents show completed status and the package is marked as finalized/exported.
3. **Full conversation screenshot** (step 32): Returns to chat and captures the complete 7-turn conversation.

---

## Command to Run

```bash
cd C:/Users/blackga/Desktop/eagle/sm_eagle/server

# Set auth credentials via env vars -- NEVER hardcode passwords
export EAGLE_TEST_EMAIL="your-test-user@example.com"
export EAGLE_TEST_PASSWORD="your-test-password"

python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys acquisition_package
```

If you want to upload results to S3 so they appear on the `/admin/e2e-judge` dashboard:

```bash
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys acquisition_package \
  --upload-s3
```

For debugging with a visible browser window:

```bash
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys acquisition_package \
  --headed -v
```

### Authentication

Auth credentials come from environment variables:
- `EAGLE_TEST_EMAIL` -- Cognito user email in the `us-east-1_ChGLHtmmp` pool (`eagle-users-dev`)
- `EAGLE_TEST_PASSWORD` -- Cognito user password

You can also pass `--auth-email` / `--auth-password` flags, but env vars are preferred. **Never hardcode credentials in commands or scripts.**

---

## Cost and Timing Estimates

| Metric | Estimate |
|--------|----------|
| **Total screenshots** | 25-35+ (varies by streaming duration and interval captures) |
| **Vision judge cost** (Sonnet) | ~$0.10-0.14 (25-35 screenshots x ~$0.004/screenshot) |
| **EAGLE app cost** (Haiku 4.5) | ~$0.007 (7 chat turns x ~$0.001/response) |
| **Total estimated cost** | ~$0.11-0.15 per run |
| **Cached repeat runs** | $0 (screenshots are hashed by SHA-256; identical UI = free cache hit) |
| **Estimated duration** | 10-15 minutes (7 chat turns with streaming waits, plus page navigations) |

The `acquisition_package` journey is significantly longer than other journeys because it tests the full UC-1 acquisition lifecycle. The 5-minute timeout for the IGCE+MR+AP batch generation step (step 16) is typically the longest single wait.

---

## Key Pages Tested

| Page | What is verified |
|------|-----------------|
| `/chat/` | Intake conversation, document generation tool cards, revision request, finalize request |
| `/workflows` | Package card with progress, document checklist modal (SOW/IGCE/MR/AP status), post-finalize status update |
| Documents tab (in-chat panel) | Right-side activity panel showing generated document status indicators |

---

## Output Files

After the run completes, results are written to:

- **Results JSON**: `server/data/e2e-judge/results/{run-id}.json` (+ `latest.json`)
- **Markdown report**: `server/data/e2e-judge/results/{run-id}-report.md`
- **Screenshots**: `server/data/e2e-judge/screenshots/{run-id}/acquisition_package/{step}.png`
- **Cache**: `server/data/e2e-judge/cache/{sha256}.json`

Each screenshot gets a structured judgment from the vision judge:

```json
{
  "verdict": "pass",
  "confidence": 0.92,
  "reasoning": "Package detail modal shows document checklist with all 4 documents marked as completed...",
  "ui_quality_score": 8,
  "issues": [],
  "cached": false
}
```

---

## Summary

The `acquisition_package` journey already covers your exact use case. You do not need to create a separate journey for checklist + revision + finalize testing. Run `--journeys acquisition_package` and the pipeline will:

1. Generate all four documents (SOW, IGCE, MR, AP)
2. Navigate to `/workflows` and verify the document checklist shows correct completed/pending status per document type
3. Return to chat and request a SOW v2 revision adding Section 508 accessibility and FedRAMP High authorization
4. Send a finalize message, validate completeness, and confirm package status update
5. Re-check `/workflows` to verify the final package state
6. Produce a pass/fail judgment with confidence scores for every screenshot captured
