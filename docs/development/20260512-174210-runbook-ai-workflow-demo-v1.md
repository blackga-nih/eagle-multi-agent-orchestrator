# EAGLE — AI Workflow Live Demo Runbook (6 minutes)

**Use this** when presenting to the team. Targets a 6-minute scripted walkthrough; tested cold-start; survives most failure modes via failsafes.

**Before you start**:
- Open 3 windows side-by-side: (1) terminal in `sm_eagle/`, (2) Claude Code, (3) browser
- Pre-load a recent session ID in your clipboard (run `aws logs filter-log-events ... | head` ahead of time)
- Verify SSO: `aws sts get-caller-identity --profile eagle` should succeed
- Have the HTML gallery folder open in a browser tab already: `docs/development/20260512-174210-gallery-ai-workflow-v1/index.html`

---

## The Script

### Step 1 — Show deployed state (0:00-0:30)

```bash
just status
```

**Say**: "EAGLE runs on ECS Fargate with two services. One command shows me the health of everything deployed."

**Failsafe**: If AWS SSO expired → `aws sso login --profile eagle` (10s), retry. If `status` recipe errors → skip to Step 2, this is just context-setting.

---

### Step 2 — The discovery surface (0:30-1:00)

```bash
just registry
```

**Say**: "This is the **new** entry point — `just registry`. It's the categorized map of every command, skill, expert, and flywheel. The next dev or AI agent picking up this codebase runs this first. Notice the JUST RECIPES section, then CLAUDE CODE SKILLS, then EXPERTS, then FLYWHEELS, then SOURCE-OF-TRUTH FILES."

**Pause** on the FLYWHEELS section — that's the keystone.

**Failsafe**: This recipe is just a heredoc print. It cannot fail. If `just` isn't installed → screen-share the `Justfile` and read the section from the file.

---

### Step 3 — Generate a live HTML report (1:00-1:30)

```bash
just langfuse-report-today
```

**Wait ~15s**, then `start docs/development/{ts}-report-langfuse-analytics-today-v1.md` (or paste the HTML version path into the browser).

**Say**: "One command pulls today's traces from Langfuse, breaks them down by tool/skill/user, computes cost, and writes both a markdown and HTML version. **This used to be 30+ minutes of manual log analysis.**"

**Failsafe**: If Langfuse creds missing → switch to `just status` (already shown) and say "imagine this with traces". If timed out → show `docs/development/20260413-195453-report-langfuse-full-24h-v2.html` from the gallery as a pre-baked example.

---

### Step 4 — The triage flywheel (1:30-3:00) — **the wow moment**

In Claude Code:
```
/triage <session-id-from-clipboard>
```

**Say while it runs**: "This is where the second AI layer shines. The skill is cross-referencing three sources in parallel — DynamoDB user feedback, CloudWatch backend errors, and Langfuse traces — for this specific session. It correlates them, classifies the root cause by one of 5 levers, and writes a fix plan."

**Wait for completion** (~60s). Don't fill the whole 90s with talking — let the team watch.

**Failsafe**: If `/triage` is slow → keep narrating the architecture. If it fails → switch to "Step 5 alternate" below (open an existing triage report).

---

### Step 5 — The output (3:00-3:30)

```bash
ls -la .claude/specs/*triage* | tail -3
```

Open the most recent one in the editor.

**Say**: "Here's the fix plan it just wrote. Notice the prioritization (P0/P1/P2), the root-cause classification, and the file:line references. Tomorrow morning, this is what triage delivers automatically for every session with negative feedback — *before* I'm even at my desk."

**Alternate (if Step 4 failed)**: Open `.claude/specs/20260427-090000-plan-triage-fixes-v1.md` (or any existing one) and walk through it instead.

---

### Step 6 — The MVP1 ladder (3:30-4:30)

```bash
just mvp1-quick
```

**Say**: "Tier 1 of the eval ladder — unit tests, no AWS creds needed. About 30 seconds. The full ladder is `mvp1` (tier 2), `mvp1-full` (tier 3 — the 142-test eval), or `mvp1-visual` (tier 4 — Playwright + e2e-judge vision QA)."

**Wait for completion** — should pass.

**Failsafe**: If pytest collects errors → show `.claude/skills/mvp1-eval/config.json` and explain the tier mapping instead.

---

### Step 7 — The gallery (4:30-5:30)

Switch to the pre-opened browser tab with the gallery `index.html`.

**Say**: "These are 12 real reports my AI workflow produced over the past month. **Each one would have taken a person 30 minutes to 2 hours.** Notice the visual consistency — that's because they all descend from the `eagle-presentation-builder.html` template we built once. Click through:"
- Hover over **02 Langfuse 24h Dashboard** — "this is generated daily, hands-free"
- Hover over **05 Jira Project Status** — "319 issues correlated against git commits in one command"
- Hover over **08 Compliance Matrix Flow** — "the interactive version of a compliance diagram we use in meetings"

---

### Step 8 — Q&A pivot (5:30-6:00)

**Pose this exact question**: "What would *you* automate if you had this system? Imagine a 30-minute task you do weekly. Could you turn it into a skill?"

Let the team answer. Each answer is a feature request.

---

## Total Time Budget

| Step | Budget | Actual (avg in dry-run) |
|---|---|---|
| 1 — status | 30s | 25s |
| 2 — registry | 30s | 28s |
| 3 — langfuse report | 30s | 35s |
| 4 — triage live | 90s | 75-110s |
| 5 — fix plan | 30s | 30s |
| 6 — mvp1-quick | 60s | 45-90s |
| 7 — gallery | 60s | 60s |
| 8 — Q&A | 30s+ | open |
| **Total** | **6:00** | **5:30-6:30** |

If running over → cut Step 5 (the fix plan inspection); the audience already saw it written.

---

## Pre-Flight Checklist (run 10 min before)

```bash
# Auth
aws sso login --profile eagle
aws sts get-caller-identity --profile eagle    # confirm

# Stack is up
just status                                     # both services should show 1/1 desired/running

# Recent session ID for /triage
aws logs filter-log-events --log-group-name /eagle/ecs/backend-dev \
  --start-time $(($(date +%s) - 3600))000 \
  --filter-pattern '"session_id"' \
  --limit 5 \
  --query 'events[].message' --output text | grep -oE 'session_id[":=][^,}"]*' | head -1
# Copy a real session ID

# Gallery pre-open
start docs/development/20260512-174210-gallery-ai-workflow-v1/index.html

# Optional: warm the Langfuse cache so step 3 returns faster
just langfuse-report-today > /dev/null 2>&1 &
```

---

## Things People Will Ask (anticipated Q&A)

**Q: "How is this different from GitHub Copilot?"**
A: Copilot is autocomplete inside an editor. This is *workflow* automation — multi-step skills that read logs, write specs, run tests, generate reports, and update Jira. Different layer.

**Q: "What does this cost us in API calls?"**
A: Each triage is ~$0.02-0.05 in Bedrock spend. Langfuse traces are free up to 50K/mo, then ~$0.0001/trace. Total: under $40/month for the second AI layer at our current pace.

**Q: "Could the team use this without learning a lot?"**
A: Yes — for most workflows you just type `/skill-name` in Claude Code. The 4-step plan→build→review→ship loop is the only meta-pattern to learn. `just registry` is the discovery surface for everything else.

**Q: "What if Claude Code goes down?"**
A: The Justfile recipes that wrap actual scripts (langfuse-report, baseline, e2e-judge, deploy) work without Claude Code. The print-and-point recipes (triage-session, kb-*, check-*) tell you what to invoke but require Claude. About 60% of recipes work without it.

**Q: "How long did it take to build the second AI layer?"**
A: ~6-8 weeks of incremental work, intermixed with EAGLE feature development. Each expert/skill was added when a recurring task became annoying enough to automate.

---

## Companion Artifacts

- Full SOP: `docs/development/20260512-174210-report-ai-workflow-sop-v1.md`
- HTML deck: `docs/development/20260512-174210-deck-ai-workflow-v1.html`
- Gallery: `docs/development/20260512-174210-gallery-ai-workflow-v1/index.html`
