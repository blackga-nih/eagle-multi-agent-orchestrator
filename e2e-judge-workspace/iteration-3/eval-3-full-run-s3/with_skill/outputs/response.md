# Full Visual Regression Test — All Journeys with S3 Upload

Here is a complete walkthrough for running the E2E Judge visual regression pipeline against all EAGLE pages, uploading results to S3, and viewing them on the dashboard.

---

## 1. Command

From the `server/` directory, run:

```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys all \
  --upload-s3
```

This targets the deployed ALB inside the VPC and pushes all results (screenshots, JSON, Markdown report) to the S3 eval bucket so the dashboard can display them.

---

## 2. Available Journeys

The `--journeys all` flag runs every registered journey. Here is each one with what it covers and the expected screenshot count:

| # | Journey | Description | ~Screenshots |
|---|---------|-------------|-------------|
| 1 | `login` | Login page rendering, Cognito authentication flow, post-login redirect to home | 3 |
| 2 | `home` | Home page layout, feature cards, sidebar navigation elements | 4-5 |
| 3 | `chat` | Multi-turn chat interaction: sends 2 messages, captures pre-send screenshots before each message, then captures at 30-second intervals during streaming responses | 10-15+ |
| 4 | `admin` | Admin dashboard and all sub-pages including skills management, templates, traces viewer, and cost tracking | 6-7 |
| 5 | `documents` | Document list page, document detail view, templates listing | 3-4 |
| 6 | `responsive` | Key pages rendered at mobile viewport (375px) and tablet viewport (768px) to verify responsive layout | 6 |
| 7 | `acquisition_package` | Full UC-1 acquisition lifecycle end-to-end: intake form, document generation (SOW/IGCE/AP), checklist review, revision cycle, finalization, and export | 25-35+ |

**Total screenshots for a full run: approximately 57-75+**, depending on streaming timing and chat response lengths.

---

## 3. Viewing Results on the Dashboard

Once the run completes with `--upload-s3`, results are viewable at:

```
http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com/admin/e2e-judge
```

The `/admin/e2e-judge` dashboard displays:
- Per-journey pass/fail status and UI quality scores
- Individual screenshot thumbnails with Sonnet's verdict, confidence, and reasoning
- Historical run comparison (via `latest.json` and timestamped run files)
- Any flagged issues or regressions

---

## 4. ALB URL

The deployed EAGLE application is accessible inside the VPC at:

```
http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com
```

This is an internal ALB — you must be on an EC2 dev box within the VPC or connected via VPN to reach it. The E2E judge pipeline runs against this URL by default when targeting the deployed environment.

---

## 5. Authentication via Environment Variables

Authentication uses real Cognito credentials from the `eagle-users-dev` pool (`us-east-1_ChGLHtmmp`). Set these env vars before running:

```bash
export EAGLE_TEST_EMAIL="your-test-user@nih.gov"
export EAGLE_TEST_PASSWORD="your-test-password"
```

Alternatively, pass them as CLI flags:

```bash
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys all \
  --upload-s3 \
  --auth-email "your-test-user@nih.gov" \
  --auth-password "your-test-password"
```

Never hardcode passwords in scripts or commit them to the repository. Env vars are the preferred approach.

AWS credentials must also be available with `bedrock:InvokeModel` permission (typically from the EC2 instance role or your AWS SSO `eagle` profile).

---

## 6. Screenshot Strategy Details

The E2E Judge uses a deliberate multi-point screenshot strategy to catch both static rendering issues and dynamic streaming behavior:

- **Static pages** (login, home, admin, documents): Screenshot is taken after `wait_until="networkidle"` to ensure all assets are loaded and the page is fully rendered.

- **Chat journey — pre-send screenshots**: Before each message is sent, a screenshot is captured of the input area with the typed message. This validates the chat input UI, placeholder text, and send button state.

- **Chat journey — 30-second interval captures during streaming**: After sending a message, the pipeline captures screenshots at 30-second intervals while the agent is streaming its response. This catches:
  - Streaming text rendering correctness
  - Tool-use display (sub-agent invocations, progress indicators)
  - Layout stability during long responses
  - Final response state once streaming completes

- **Responsive journey**: The same pages are revisited at 375px (mobile) and 768px (tablet) viewports to verify responsive CSS breakpoints.

- **Acquisition package journey**: Screenshots are captured at each lifecycle phase transition (intake complete, generation started, generation complete, checklist displayed, revision submitted, finalized, exported) — resulting in the highest screenshot count of any journey.

Each screenshot is SHA-256 hashed for caching. If the UI looks pixel-identical to a previous run, the cached Sonnet judgment is reused at zero cost.

---

## 7. Cost Estimate for a Full Run

The pipeline uses two models with different cost profiles:

| Component | Model | Cost per unit | Units (full run) | Subtotal |
|-----------|-------|---------------|-------------------|----------|
| Vision judge evaluations | Claude Sonnet (via Bedrock) | ~$0.004/screenshot | ~57-75 screenshots | ~$0.23-$0.30 |
| EAGLE app responses (chat + acquisition_package) | Haiku 4.5 (via Bedrock) | ~$0.001/response | ~9-10 chat turns | ~$0.01 |
| **Total (first run, no cache)** | | | | **~$0.24-$0.31** |
| **Cached repeat run** | | | | **$0.00** |

Key cost notes:
- The `acquisition_package` journey alone accounts for roughly half the total cost (~25-35 screenshots + 7 chat turns).
- Cached runs are free — if the UI has not changed pixel-for-pixel, SHA-256 hashes match and no Sonnet calls are made.
- Cache TTL is 7 days by default (configurable via `E2E_JUDGE_CACHE_TTL_DAYS`).
- Use `--purge-cache` if you want to force fresh evaluations regardless of cache state.

---

## 8. Warning: acquisition_package Is the Longest Journey

The `acquisition_package` journey is significantly longer than all other journeys combined. It tests the full UC-1 acquisition lifecycle end-to-end:

1. Intake form submission
2. Document generation (SOW, IGCE, AP)
3. Checklist review
4. Revision cycle
5. Finalization
6. Export

This involves **7 chat turns** with the EAGLE agent, takes approximately **10-15 minutes** to complete, and produces **25-35+ screenshots**. When running `--journeys all`, budget extra time and cost for this journey. If you want a quick smoke test first, run the shorter journeys:

```bash
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys login,home,chat,admin,documents,responsive \
  --upload-s3
```

Then run `acquisition_package` separately once the shorter journeys pass:

```bash
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys acquisition_package \
  --upload-s3
```

---

## 9. Output Artifacts

After the run completes, results are written locally and (with `--upload-s3`) pushed to S3:

| Artifact | Local Path | Purpose |
|----------|-----------|---------|
| Results JSON | `data/e2e-judge/results/{run-id}.json` | Machine-readable pass/fail + scores |
| Latest symlink | `data/e2e-judge/results/latest.json` | Always points to most recent run |
| Markdown report | `data/e2e-judge/results/{run-id}-report.md` | Human-readable summary |
| Screenshots | `data/e2e-judge/screenshots/{run-id}/{journey}/{step}.png` | Raw captures |
| Cache | `data/e2e-judge/cache/{sha256}.json` | Cached Sonnet judgments (7-day TTL) |

Each screenshot judgment includes:
- `verdict`: pass or fail
- `confidence`: 0.0-1.0
- `reasoning`: Sonnet's explanation of what it sees
- `ui_quality_score`: 1-10
- `issues`: Array of any problems detected
- `cached`: Whether this was a cache hit
