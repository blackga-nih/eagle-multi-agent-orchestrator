# E2E Judge Response — Implicit Visual Check

## Skill Recognition

Your request to "do a quick visual check of the admin dashboard and chat page to make sure nothing looks broken" maps directly to the **e2e-judge** skill. The key signals:

- **"visual check"** -- this is screenshot-based visual QA, exactly what e2e-judge does
- **"make sure nothing looks broken"** -- pass/fail evaluation of UI quality, the core purpose of the vision judge pipeline
- **"deployed URL"** -- e2e-judge targets the deployed ALB URL, not localhost

No need to mention "e2e-judge" by name. The skill description explicitly says to activate for "visual QA", "UI validation", "visual regression", or when someone wants to "check if the deployed EAGLE app looks correct." This request hits all of those triggers.

---

## Journey Mapping

You mentioned two areas to check. Here is how they map to e2e-judge journeys:

| Your request | Journey name | What it captures |
|--------------|-------------|-----------------|
| "admin dashboard" | `admin` | Admin dashboard + sub-pages (skills, templates, traces, costs) -- ~6-7 screenshots |
| "chat page" | `chat` | Multi-turn chat: 2 messages, pre-send screenshots, 30s streaming intervals -- ~10-15+ screenshots |

Since you said "quick visual check," I will run only these two journeys rather than `--journeys all`, which would also include `login`, `home`, `documents`, `responsive`, and `acquisition_package` (the last one alone takes 10-15 minutes and 25-35+ screenshots).

---

## Command to Run

```bash
cd server/
python -m tests.e2e_judge_orchestrator \
  --base-url http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com \
  --journeys admin,chat
```

### Flag Breakdown

| Flag | Value | Why |
|------|-------|-----|
| `--base-url` | `http://internal-eaglec-front-...elb.amazonaws.com` | The deployed ALB URL inside the VPC. This is the production-like target you just deployed to. |
| `--journeys` | `admin,chat` | Only the two journeys you asked about. Keeps the run fast and focused. |

### Flags NOT used (and why)

| Flag | Why omitted |
|------|-------------|
| `--headed` | Not debugging; headless is fine for a quick check |
| `--purge-cache` | You want a fresh check after a deployment, but the cache is SHA-256 based on pixel content. If your frontend change actually changed the UI, the hashes will differ and the cache will miss automatically. If the pages look identical to last run, a cache hit is the correct behavior -- it confirms nothing visually changed. |
| `--upload-s3` | Not requested. If you want results viewable at `/admin/e2e-judge` on the deployed app, I can re-run with `--upload-s3`. |
| `--auth-email/--auth-password` | These come from `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` env vars, which should already be set on this machine. If not, I will prompt you for credentials. |
| `-v` | Not needed for a quick check. If something fails, I can re-run with verbose logging. |

### Authentication Note

The orchestrator authenticates against Cognito pool `us-east-1_ChGLHtmmp` (the `eagle-users-dev` pool). Credentials are read from `EAGLE_TEST_EMAIL` / `EAGLE_TEST_PASSWORD` environment variables. I will not hardcode passwords in the command -- if the env vars are not set, I will ask you for them before running.

---

## What the Pipeline Does

1. **Playwright** launches headless Chromium, authenticates via Cognito, and navigates through each journey step
2. **Screenshots** are captured at every meaningful step (page loads, after interactions, after data appears)
3. Each screenshot is **SHA-256 hashed** and checked against the local file cache (`data/e2e-judge/cache/{sha256}.json`)
4. **Cache miss**: the screenshot is sent to Claude Sonnet via Bedrock converse (image content block) for structured evaluation
5. **Cache hit**: the previous judgment is reused instantly (free)
6. Results are written to `data/e2e-judge/results/{run-id}.json` and a markdown report at `data/e2e-judge/results/{run-id}-report.md`

---

## Verdict Explanations

Each screenshot produces a structured judgment with these fields:

### `verdict` (the key outcome)

| Verdict | Meaning | Action needed |
|---------|---------|---------------|
| **`pass`** | The UI looks correct. Layout, content, interactive elements, and styling all appear as expected. No visual defects detected. | None -- your deployment is good for this page. |
| **`fail`** | Something is visibly broken. Examples: blank page, missing components, layout collapse, error messages displayed, broken images, unreadable text, overlapping elements. | Investigate immediately. The `reasoning` field will describe exactly what looks wrong and the `issues` array will list specific problems. |
| **`warning`** | The page renders but something is off. Examples: minor alignment issues, unexpected empty states, slow-loading placeholders still visible, slightly clipped text, non-critical styling differences. | Review the screenshot and reasoning. May be acceptable (e.g., empty state on a fresh environment) or may indicate a subtle regression. |

### Other fields in the judgment

| Field | What it tells you |
|-------|-------------------|
| `confidence` | 0.0-1.0 score of how certain the judge is about its verdict. Below 0.7 means the judge found ambiguity. |
| `reasoning` | Free-text explanation of what the judge saw and why it chose the verdict. |
| `ui_quality_score` | 1-10 score for overall UI quality (layout, spacing, typography, color, responsiveness). |
| `issues` | Array of specific problems found. Empty array = no issues. |
| `cached` | `true` if this judgment was served from cache (identical screenshot seen before). `false` if Sonnet evaluated it fresh. |

### Interpreting results for your deployment

- **All pass**: Your frontend change deployed cleanly. Admin dashboard and chat page look correct.
- **All pass but all cached**: The pages look pixel-identical to the last run. If you expected visual changes, this might mean your deployment did not take effect, or the changes are on pages you did not test.
- **Mix of pass and warning**: Review the warnings. Common false positives include empty data states on dev environments or minor timing issues with loading spinners.
- **Any fail**: Something broke. Check the screenshot, read the reasoning, and compare against the previous passing run.

---

## Cost Estimate

### This run (admin + chat journeys)

| Component | Screenshots | Cost per screenshot | Estimated cost |
|-----------|-------------|--------------------:|---------------:|
| Sonnet vision (judge) | ~16-22 | ~$0.004 | ~$0.06-$0.09 |
| Haiku 4.5 (EAGLE app responses during chat journey) | ~2 chat turns | ~$0.001/response | ~$0.002 |
| **Total (fresh run, no cache hits)** | | | **~$0.07-$0.10** |

### If pages look the same as last run (all cache hits)

| Component | Cost |
|-----------|-----:|
| Sonnet vision | **$0.00** (all cached) |
| Haiku 4.5 | ~$0.002 (chat still sends messages) |
| **Total (fully cached)** | **~$0.002** |

### For comparison: full `--journeys all` run

| Scope | Fresh cost | Cached cost |
|-------|----------:|------------:|
| All journeys except acquisition_package (~40 screenshots) | ~$0.16 | ~$0.002 |
| All journeys including acquisition_package (~70+ screenshots) | ~$0.30 | ~$0.002 |

The cache makes repeated runs essentially free. Since you just deployed a frontend change, you will likely see a mix: cache misses on pages that changed, cache hits on pages that did not.

---

## Output Locations

After the run completes, you will find:

| Output | Path |
|--------|------|
| Results JSON | `server/data/e2e-judge/results/{run-id}.json` (+ `latest.json`) |
| Markdown report | `server/data/e2e-judge/results/{run-id}-report.md` |
| Screenshots | `server/data/e2e-judge/screenshots/{run-id}/admin/*.png` and `server/data/e2e-judge/screenshots/{run-id}/chat/*.png` |
| Cache | `server/data/e2e-judge/cache/{sha256}.json` |

---

## Ready to Run

Shall I go ahead and execute the command? Before I do, I will verify that `EAGLE_TEST_EMAIL` and `EAGLE_TEST_PASSWORD` environment variables are set. If they are not, I will need you to provide test credentials (a real user in the `eagle-users-dev` Cognito pool).

If you also want the results uploaded to S3 so they are viewable at `/admin/e2e-judge` on the deployed app, let me know and I will add the `--upload-s3` flag.
