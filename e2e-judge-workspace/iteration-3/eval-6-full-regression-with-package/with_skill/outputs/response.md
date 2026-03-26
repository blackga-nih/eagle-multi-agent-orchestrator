# Full Visual Regression -- All Journeys with S3 Upload

## Command

```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys all \
  --upload-s3
```

Auth credentials are read from environment variables -- never hardcode them:

```bash
export EAGLE_TEST_EMAIL="your-test-user@example.com"
export EAGLE_TEST_PASSWORD="your-test-password"
```

These must correspond to a real user in the Cognito pool `us-east-1_ChGLHtmmp` (`eagle-users-dev`). You can also pass `--auth-email` / `--auth-password` flags, but env vars are preferred to avoid passwords appearing in shell history.

---

## All 7 Available Journeys

| # | Journey | Description | ~Screenshots |
|---|---------|-------------|-------------|
| 1 | **login** | Login page load, Cognito auth form, post-auth redirect to home | 3 |
| 2 | **home** | Home page with welcome message and feature cards, sidebar navigation, card click navigation | 4-5 |
| 3 | **chat** | Full multi-turn chat interaction: 2 user messages with pre-send screenshots, agent streaming captured at 30-second intervals, tool use cards, final conversation view | 10-15+ |
| 4 | **admin** | Admin dashboard plus 5 sub-pages: skills management, templates, trace viewer, test results, cost tracking | 6-7 |
| 5 | **documents** | Document listing page, single document detail view (if docs exist), document templates page | 3-4 |
| 6 | **responsive** | Home, chat, and admin pages rendered at mobile (375x812) and tablet (768x1024) viewports | 6 |
| 7 | **acquisition_package** | Full UC-1 acquisition package lifecycle from intake through export (detailed below) | 25-35+ |

**Total screenshots for `--journeys all`: approximately 57-75+**, depending on streaming durations and conditional UI elements.

---

## Acquisition Package Journey -- Full Lifecycle Detail

The `acquisition_package` journey is the most comprehensive test in the suite. It exercises the entire UC-1 acquisition lifecycle end-to-end across 6 phases and 7 chat turns:

### Phase 1: Intake
- Navigates to `/chat/`, starts a new session
- Sends intake message: "$750K cloud hosting services for research data platform"
- Captures EAGLE's clarifying questions response
- Sends detailed answers: 3-year base + 2 option years, FedRAMP High, full and open competition, fixed-price
- Captures compliance analysis with acquisition pathway and threshold identification

### Phase 2: Document Generation
- Requests SOW generation -- captures streaming progress and tool result cards
- Requests IGCE, Market Research Report, and Acquisition Plan in a single turn
- Captures all 4 document generation completions with tool cards visible

### Phase 3: Document Checklist Check
- Clicks the Documents tab in the activity panel to verify checklist status
- Navigates to `/workflows` to see the acquisition package card with progress indicators
- Opens the package detail modal showing completed/pending status for each document

### Phase 4: Document Revision
- Returns to chat, requests SOW revision: add Section 508 accessibility + FedRAMP High as mandatory contractor qualification
- Captures SOW v2 generation and completion

### Phase 5: Finalize Package
- Sends finalization request ("All documents are ready for review")
- Captures status update and compliance validation response

### Phase 6: Export
- Requests full package export as ZIP file
- Captures export response with download link/instructions
- Navigates back to `/workflows` to verify final package status
- Opens package detail one final time to confirm all documents completed and package finalized/exported
- Takes final full conversation screenshot showing all 7 exchanges

This journey alone produces **25-35+ screenshots** across its 32 named capture steps (some steps are conditional on UI state, and streaming intervals add additional captures dynamically).

---

## Runtime Warning

| Scope | Estimated Time |
|-------|---------------|
| All journeys **excluding** acquisition_package (login, home, chat, admin, documents, responsive) | ~10-15 minutes |
| acquisition_package journey alone | ~10-15 minutes |
| **Full run (`--journeys all`)** | **~20-30 minutes** |

The `acquisition_package` journey is the dominant cost in runtime. It involves 7 separate chat turns, each requiring the agent to process, stream a response (often with document generation tool calls), and wait for completion. Document generation turns (SOW, IGCE, MR, AP) can each take 30-90 seconds, and the journey includes 5-minute timeouts for the multi-document generation step.

Plan accordingly -- this is not a quick smoke test. If you only need UI layout validation without the full lifecycle, run `--journeys login,home,chat,admin,documents,responsive` instead.

---

## Cost Estimate

| Run Scope | Vision Judge (Sonnet) | App Responses (Haiku 4.5) | Approximate Total |
|-----------|----------------------|--------------------------|-------------------|
| All journeys **without** acquisition_package (~40 screenshots) | ~$0.16 | minimal | ~$0.16 |
| acquisition_package only (~30 screenshots, 7 chat turns) | ~$0.12 | ~$0.007 | ~$0.13 |
| **Full run with all 7 journeys (~70+ screenshots)** | **~$0.28** | **~$0.007** | **~$0.30+** |
| Cached repeat run (identical UI) | $0 | $0 | $0 |

Cost breakdown:
- **Sonnet vision evaluation**: ~$0.004 per screenshot (image content block via Bedrock converse)
- **Haiku 4.5 app responses**: ~$0.001 per agent response (only incurred during chat/acquisition_package journeys that interact with the EAGLE agent)
- **Cached runs**: Screenshots are hashed by SHA-256. If the UI hasn't changed pixel-for-pixel, cached judgments are reused at zero cost. Cache TTL is 7 days (configurable via `E2E_JUDGE_CACHE_TTL_DAYS`).

---

## Authentication

Authentication uses environment variables -- credentials are **never hardcoded** in the command or source code:

```bash
export EAGLE_TEST_EMAIL="..."
export EAGLE_TEST_PASSWORD="..."
```

These must be valid credentials in the Cognito user pool `us-east-1_ChGLHtmmp` (`eagle-users-dev`). The orchestrator uses these to authenticate the Playwright browser session against the deployed app's Cognito login flow.

If the env vars are not set and no `--auth-email` / `--auth-password` flags are provided, the orchestrator will fail at the login step.

---

## Viewing Results

After the run completes with `--upload-s3`, results (JSON, markdown report, and all screenshots) are pushed to the S3 eval bucket.

**View results in the deployed app at:**

```
/admin/e2e-judge
```

This is the E2E Judge dashboard on the admin panel, which renders the uploaded results with screenshot thumbnails, pass/fail verdicts, confidence scores, and UI quality ratings for each step.

---

## Output Files

All output is written under `server/data/e2e-judge/`:

| Path | Content |
|------|---------|
| `data/e2e-judge/results/{run-id}.json` | Full structured results -- every step with verdict, confidence, reasoning, ui_quality_score, issues |
| `data/e2e-judge/results/latest.json` | Symlink/copy to most recent run (for dashboard consumption) |
| `data/e2e-judge/results/{run-id}-report.md` | Human-readable markdown report with summary stats and per-journey breakdown |
| `data/e2e-judge/screenshots/{run-id}/{journey}/{step}.png` | Raw screenshots organized by journey and step name |
| `data/e2e-judge/cache/{sha256}.json` | Cached vision judgments keyed by screenshot content hash (7-day TTL) |

Each step in the results JSON contains a structured judgment:

```json
{
  "verdict": "pass",
  "confidence": 0.92,
  "reasoning": "Chat page loads correctly with sidebar, input area, and welcome message",
  "ui_quality_score": 8,
  "issues": [],
  "cached": false
}
```

When `--upload-s3` is active, all of the above (results JSON, report, and screenshots) are uploaded to the S3 eval bucket for access via the `/admin/e2e-judge` dashboard.
