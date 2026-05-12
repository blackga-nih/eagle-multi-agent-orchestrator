# MVP1 Next Steps — Informed by Session Telemetry

**Date:** 2026-05-12
**Source:** Developer Claude Code session history (`~/.claude/projects/<encoded>/`) over the Apr 10 – May 12 window, queried via [`pp-claude-sessions`](../../.claude/skills/pp-claude-sessions/) against a sanitized [`claude-handoff`](../../.claude/skills/claude-handoff/) bundle.
**Scope:** This is a developer-tooling artifact — not user-facing application content. It uses dev IDE telemetry as one input to a project-planning narrative. It is not wired into the EAGLE runtime; see `eagle-plugin/` for application skills/agents.

---

Before listing what's next, here's what the work has actually looked like over the past month. These numbers come from the [`pp-claude-sessions`](../../.claude/skills/pp-claude-sessions/) CLI run against a scrubbed [`claude-handoff`](../../.claude/skills/claude-handoff/) bundle of the originating dev's `~/.claude/projects/<encoded>/` directory. The CLI is read-only Python 3.10+ (stdlib only) and the bundle is itself scrubbed of credentials before any byte leaves the host.

## What 32 days of MVP1 work looks like (Apr 10 – May 12)

```bash
python ~/.claude/skills/pp-claude-sessions/query.py \
  --src ./session-history/jsonl --agent stats
```

| Metric | Value |
|---|---|
| Sessions | **52** |
| Total messages | **39,147** (15,423 user · 23,724 assistant) |
| Tool invocations | **13,813** across 23 distinct tools |
| Date range | 2026-04-10 → 2026-05-12 |
| Cadence | 11–13 new sessions/week (ISO weeks 16–19) |

```bash
python ~/.claude/skills/pp-claude-sessions/query.py --src ./session-history/jsonl --agent tools
```

| Tool | Uses | Share |
|------|-----:|------:|
| Bash | 6,413 | 46% |
| Read | 2,707 | 20% |
| Edit | 1,283 | 9% |
| Grep | 1,176 | 9% |
| TaskUpdate / TaskCreate | 1,282 | 9% |
| Write | 190 | 1% |

> **Signal:** Bash + Read + Grep account for **75% of tool use**. The MVP1 dev loop is heavily exploratory/diagnostic — read a file, grep a pattern, run a script. That's appropriate for an integration phase but suggests room to lift the most-repeated shell incantations into proper skills/agents (the same printing-press pattern this CLI uses).

## Where MVP1 attention is concentrated

```bash
python ~/.claude/skills/pp-claude-sessions/query.py --src ./session-history/jsonl --agent search "<term>" --limit 0
```

| MVP1 surface | Mentions | Sessions |
|---|---:|---:|
| `SOW` | 1,257 | — |
| `IGCE` | 909 | — |
| `intake` | 801 | — |
| `document generation` / `doc-gen` | 523 | 30 |
| `market research` | 513 | — |
| `compliance matrix` | 277 | 30 |
| `sole source` | 280 | — |
| `MVP1` (literal, case-sensitive) | 57 | 14 |

> **Signal:** The compliance matrix and the doc-gen pipeline are the two MVP1 surfaces with the broadest cross-session footprint (each in **30 of 52 sessions**). Both are also where the [`weekly-changelog`](weekly-changelog.md) shows the most churn — KB-first cascade, deterministic decision tree, native Office editing, Bedrock PDF parsing, IGCE position-based generation.

## Branches that mention MVP1 explicitly

| Branch | Sessions referencing MVP1 |
|---|---:|
| `main` | 7 |
| `new-baseline-apr-13` | 4 |
| `ci/pytest-testmon-incremental-tests` | 1 |
| `fix/unique-user-tests-ci-reload-20260422` | 1 |
| `docs/playground-presentations-20260414-v2` | 1 |

> **Signal:** MVP1 framing shows up most on `main` (production-tracking work) and the **`new-baseline-apr-13`** baseline branch — confirming what the changelog already implies: the baseline scoring (V4 → V9 reaching 96%) is the gating signal for "is MVP1 ready."

---

## What's left for MVP1

Three workstreams, ordered by what the session data and the [project compliance-matrix memo](../../memory/project_compliance_matrix_improvements.md) say is closest to landing:

### 1. Compliance matrix — finish phases 3–6

Phases 1 and 2 are landed. Pending per [`memory/project_compliance_matrix_improvements.md`](../../memory/project_compliance_matrix_improvements.md):

- **Phase 3 — Tool consolidation.** Collapse the `search_far` + `knowledge_search` + `knowledge_fetch` chain into a single `compliance_lookup` call. The session log shows this chain invoked repeatedly inside `STEP 2 — Compliance Matrix` prompts; consolidation removes a TTFT tax and a class of orchestration errors.
- **Phase 4 — Citation verification.** Validate that each cited FAR/DFARS clause actually exists in the KB before the supervisor finalizes the matrix. Today the matrix can return a clause string the KB never indexed.
- **Phase 5 — Template fields.** Promote the matrix output from prose to structured fields (`socioeconomic_set_aside`, `competition_type`, `acquisition_threshold`, `naics`, `psc`, …) so downstream doc-gen (SOW, IGCE, AP) can read them without re-parsing.
- **Phase 6 — Confidence scoring.** Surface a `confidence` per matrix decision so the chat UI can flag low-confidence answers for CO review instead of presenting them as final.

### 2. Lock the baseline at 100% before MVP1 sign-off

`baseline-questions` skill last hit **V9 = 250/260 (96%)** (week of Apr 6). The remaining 4% is the gating bar:

- Re-run baseline against the latest `main` after compliance matrix Phase 4 (citation verify) lands.
- Add the 4 failing-question categories as targeted eval tests (`test_strands_eval.py` slot 138–142 already reserves Jira QA validation; reserve 143–146 for baseline regressions).
- Wire baseline into `mvp1-eval` Tier 4 so a regression blocks the deploy.

### 3. MVP1 UC coverage — close the gap from 14 → 21+

Eval tests **29–42** cover MVP1 UC scenarios (per the README's eval-suite section). 14 tests pass today. The 9 documented MVP1 use cases plus multi-turn copy-paste prompts mean the realistic UC test count should land in the **low-20s**. Pending UCs to wire as `test_strands_eval.py` cases:

- Multi-turn UC continuations (already drafted in [`docs/development/`](.) — promote the prompts into eval slots)
- Sole-source decision tree (`sole source` shows 280 mentions / 0 dedicated eval slot)
- Market research → SOW handoff (`market research` 513 mentions; pre-doc-gen handoff is a known weak spot)
- IGCE position-based generation regression (landed 2026-03-30; needs a guard test)
- Document changelog round-trip (DOCX/XLSX edit → save → re-open consistency)

### 4. Workflow hygiene to support items 1–3

Three low-cost wins surfaced by the tool-use distribution:

- **Cap shell exploration** — promote 5–10 of the most-repeated Bash incantations (find-config-file, list-DDB-keys, dump-recent-langfuse-trace) into named skills. Bash at 46% of tool use is a sign these grew organically; named skills make them rerunnable and discoverable.
- **Adopt `/pp-claude-sessions` for triage** — instead of "grep the project dir," start triage with `search --include-tools` over session history. Faster RCA on regressions like `EAGLE-74/77`.
- **Run the printing-press factory** on the FAR/DFARS public API (or the Acquisition.gov OpenAPI spec if one exists) to generate a typed CLI/MCP server, replacing the current ad-hoc `web_search` scope. This is the same pattern the `pp-claude-sessions` CLI uses, applied to an external read API.

---

## How to reproduce these numbers on your own bundle

```bash
# 1. Make a sanitized handoff bundle (gitignored)
/claude-handoff

# 2. Point the query CLI at it
python ~/.claude/skills/pp-claude-sessions/query.py \
  --src ./handoff-claude-*/session-history/jsonl --agent stats

# 3. Targeted searches (returns JSON envelope; pipe to jq or --select to filter)
python ~/.claude/skills/pp-claude-sessions/query.py \
  --src ./handoff-claude-*/session-history/jsonl --agent search "compliance matrix" --limit 5

# 4. Forensic mode — also matches inside Bash commands, Edit args, tool_use payloads
python ~/.claude/skills/pp-claude-sessions/query.py \
  --src ./handoff-claude-*/session-history/jsonl --agent search "Lb6sb" --include-tools
```

The CLI's `--verify` analogue in [`claude-handoff/scrub-jsonl.py`](../../.claude/skills/claude-handoff/scrub-jsonl.py) was caught on its first real run when `search` here surfaced a partial AWS secret that the original scrubber regex missed — the scrubber's rule set + `--verify` exit gate are now tightened against that whole class of leak.

---

## What this is NOT

- Not application content. None of this is wired into `eagle-plugin/`, `server/app/`, or `client/` — those remain untouched.
- Not a roadmap commitment. The "next steps" framing is a developer-side reading of where to spend effort. Authoritative MVP1 scope still flows through Jira + product.
- Not a metric system. These are one-time counts from a sanitized snapshot, not a live dashboard.
