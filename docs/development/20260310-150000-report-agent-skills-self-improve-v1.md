# Agent Skills Self-Improvement — State of the Art Report

> **Date**: 2026-03-10
> **Branch**: fix/fast-path-kb-tools
> **Purpose**: Evaluate Anthropic's Agent Skills spec against EAGLE's current self-improve pattern; identify gaps and upgrade path.

---

## TL;DR

There is **no built-in self-improvement mechanism** in Agent Skills or Claude Code. EAGLE's `/experts:{domain}:self-improve` commands are a custom pattern that is architecturally ahead of anything Anthropic has shipped. The main gap is that self-improve is manually triggered — not wired to session end.

---

## 1. Official Sources Checked

| Source | Retrieved |
|--------|-----------|
| `code.claude.com/docs/en/skills` | ✅ Full content |
| `agentskills.io/specification` | ✅ Full content |
| `anthropic.com/news/claude-code-skills` | ✅ |
| `claude.ai/blog/skills` (Oct 16, 2025) | ✅ |
| Claude Code changelog 2025–2026 | ✅ |

---

## 2. Complete SKILL.md Front Matter Reference

### Open Standard (agentskills.io) — 6 fields

| Field | Required | Notes |
|-------|----------|-------|
| `name` | Yes | Max 64 chars, lowercase + hyphens |
| `description` | Yes | Max 1024 chars |
| `license` | No | License name or file reference |
| `compatibility` | No | Max 500 chars |
| `metadata` | No | Arbitrary key-value map |
| `allowed-tools` | No | Space-delimited, experimental |

### Claude Code Extensions — 7 additional fields

| Field | Default | Notes |
|-------|---------|-------|
| `argument-hint` | — | Autocomplete hint shown in slash menu |
| `disable-model-invocation` | `false` | `true` = skill not loaded into context; user-only via `/name` |
| `user-invocable` | `true` | `false` = hidden from `/` menu entirely |
| `model` | inherited | Override model for this skill only |
| `context` | — | Set to `fork` to run in isolated subagent |
| `agent` | — | Which subagent type when `context: fork` |
| `hooks` | — | Skill lifecycle hooks |

**There is no `self-improve`, `auto-update`, `reflect`, or any autonomous-rewrite key in either spec.**

---

## 3. Key Mechanism: How `description` Drives Auto-Invocation

Official docs quote:
> *"Skill descriptions are loaded into context so Claude knows what's available, but full skill content only loads when invoked."*

- Every session loads all skill `description` fields (unless `disable-model-invocation: true`)
- Claude uses **semantic matching** — standard language model inference — to decide if a skill is relevant
- No keyword-matching engine; matching quality depends entirely on description quality
- Docs advise: *"Check the description includes keywords users would naturally say"*

### Context Budget

> *"The budget scales dynamically at **2% of the context window**, with a fallback of 16,000 characters."*

- 200K context window → ~4,000 tokens for all skill descriptions combined
- Overflow: some skills are excluded. Check with `/context` command.
- Override via `SLASH_COMMAND_TOOL_CHAR_BUDGET` env var.

**Implication for EAGLE**: With ~150+ skills/commands in context, the 2% budget is a real constraint. Short, precise descriptions beat long ones.

---

## 4. Bundled Claude Code Skills (No Self-Improvement)

| Skill | What it does |
|-------|-------------|
| `/simplify` | Parallel review agents for code reuse, quality, efficiency |
| `/batch <instruction>` | Large-scale parallel codebase changes via git worktrees |
| `/debug [description]` | Troubleshoots the Claude Code session itself |
| `/loop [interval] <prompt>` | Recurring scheduled prompts |
| `/claude-api` | Loads Claude API reference into context |

None of these rewrite skill files. There is no built-in `/improve-skill` or `/update-skill`.

---

## 5. The Roadmap Quote

From Anthropic's engineering post, October 16, 2025:
> *"Looking further ahead, we hope to enable agents to create, edit, and evaluate Skills on their own, letting them codify their own patterns of behavior into reusable capabilities."*

This is a **stated aspiration**, not a shipped feature as of March 2026.

---

## 6. EAGLE's Current Position

### What EAGLE has built (custom, not Anthropic-native)

```
/experts:{domain}:self-improve
  1. Reads expertise.md (current knowledge base)
  2. Reads recent session transcript or diff
  3. Identifies new patterns, fixes, corrections
  4. Rewrites expertise.md with updated knowledge
  5. Human reviews diff before merge
```

This is the **evaluator-optimizer loop** from Anthropic's own *Building Effective Agents* research — one of the 5 canonical agentic patterns. EAGLE implements it across **13 domains**:
`aws` · `backend` · `claude-sdk` · `cloudwatch` · `deployment` · `eval` · `frontend` · `git` · `hooks` · `sse` · `strands` · `tac` · `test`

### Gap Analysis

| Capability | Anthropic | EAGLE |
|-----------|-----------|-------|
| Skills with descriptions | ✅ shipped | ✅ all fixed Mar 2026 |
| Manual self-improve loop | ❌ not shipped | ✅ 13 domains |
| Session-end auto trigger | ❌ not shipped | ❌ missing |
| Cross-domain propagation | ❌ not shipped | ⚠️ partial (`parallel_expert_self_improve`) |
| Agent-authored new skills | ❌ roadmap only | ❌ missing |
| Context budget awareness | ✅ 2% dynamic | ⚠️ not enforced — 150+ skills at risk |

---

## 7. Recommended Upgrades (Priority Order)

### P1 — Session-end auto self-improve hook
Wire a `Stop` hook that fires after every session. The hook identifies which expert domains were touched (by scanning session git diff) and queues `self-improve` for those domains.

```json
// .claude/settings.json
{
  "hooks": {
    "Stop": [{ "command": "python C:/path/to/.claude/hooks/post_session_self_improve.py" }]
  }
}
```

### P2 — Context budget audit
With 150+ skills, some are being excluded from context. Run `/context` to find out which. Shorten descriptions over 200 chars. Consider setting `disable-model-invocation: true` on internal reference files (`expertise.md`, `_index.md`) to reclaim budget.

> **Note**: As of March 2026, `_index.md` and `expertise.md` files across all 13 domains now have descriptions. This may be *adding* budget pressure. Consider whether these files should use `user-invocable: false` instead to remove them from the skills list entirely.

### P3 — Cross-domain learning log
Add `.claude/context/cross-domain-learnings.md`. Any `self-improve` command that discovers something cross-cutting appends to it. `parallel_expert_self_improve` reads it first as shared context.

### P4 — Pattern-to-skill promotion
When a fix/pattern appears 3+ times in session transcripts, have `self-improve` propose a new skill file instead of just updating `expertise.md`. Human approves → new reusable command is created. This is exactly what Anthropic described as future work.

---

## 8. The `disable-model-invocation` vs `user-invocable` Distinction

These two keys are often confused:

| Key | Effect on context | Effect on `/` menu |
|-----|-------------------|-------------------|
| `disable-model-invocation: true` | Description NOT loaded | Still appears in `/` menu |
| `user-invocable: false` | Description NOT loaded | Hidden from `/` menu |

**Practical use in EAGLE:**
- `pull-remote`, `sync` → already have `disable-model-invocation: true` ✅ (side-effect git ops, user must invoke explicitly)
- `expertise.md`, `_index.md` → candidates for `user-invocable: false` (internal files, never user-invoked)

---

## Sources

- [Introducing Agent Skills — Anthropic Blog](https://claude.ai/blog/skills) (Oct 16, 2025)
- [Equipping agents for the real world with Agent Skills — Anthropic Engineering](https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills) (Oct 16, 2025)
- [Extend Claude with skills — Claude Code Docs](https://code.claude.com/docs/en/skills)
- [Agent Skills Open Standard](https://agentskills.io/specification)
- [Enabling Claude Code to work more autonomously](https://www.anthropic.com/news/enabling-claude-code-to-work-more-autonomously) (Sep 29, 2025)
- [Building Effective Agents — Anthropic Research](https://www.anthropic.com/research/building-effective-agents)
- [Agent Skills Open Standard announcement — SiliconANGLE](https://siliconangle.com/2025/12/18/anthropic-makes-agent-skills-open-standard/) (Dec 18, 2025)
