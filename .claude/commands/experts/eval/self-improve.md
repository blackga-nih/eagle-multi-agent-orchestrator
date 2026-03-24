---
description: "Closed-loop agent self-improvement: diagnose eval failures, prioritize by root cause, fix agent/skill/routing code, and re-validate"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent
argument-hint: "[--diagnose | --fix | --full] [--tests N,N] [--dry-run]"
model: opus
---

# Eval Expert - Self-Improve (Closed Loop)

> Analyze eval results, classify failures by root cause, edit agent prompts/skill workflows/routing logic, and re-run affected tests to validate fixes.

## Purpose

This is NOT a documentation-only update. This command closes the loop: eval failures drive actual code changes to agent prompts, skill workflows, supervisor routing, and tool configurations. The expertise.md update is a side effect, not the goal.

**Old pattern (open loop)**: Run tests -> record learnings in expertise.md -> hope someone reads them
**New pattern (closed loop)**: Run tests -> diagnose root cause -> edit agent/skill code -> re-run to validate -> record learnings

## Usage

```
/experts:eval:self-improve --diagnose                    # Phase 1 only: classify failures, no edits
/experts:eval:self-improve --fix                         # Phase 1+2+3: diagnose, prioritize, fix
/experts:eval:self-improve --full                        # All 4 phases: diagnose, prioritize, fix, validate
/experts:eval:self-improve --full --tests 61,62,63       # Focus on specific tests
/experts:eval:self-improve --dry-run                     # Show what would change, don't edit
```

## Variables

- `FLAGS`: $ARGUMENTS
- `EVAL_FILE`: `server/tests/test_strands_eval.py`
- `PUBLISHER_FILE`: `server/tests/eval_aws_publisher.py`
- `HELPERS_FILE`: `server/tests/eval_helpers.py`
- `SERVICE_FILE`: `server/app/strands_agentic_service.py`
- `PLUGIN_DIR`: `eagle-plugin/`

---

## The 5 Levers

These are the things you can actually change to improve agent behavior. Every fix must target one or more of these:

| # | Lever | File(s) | What it controls |
|---|-------|---------|-----------------|
| 1 | **Agent prompts** | `eagle-plugin/agents/*/agent.md` | Specialist behavior, domain knowledge, output format |
| 2 | **Skill workflows** | `eagle-plugin/skills/*/SKILL.md` | Step-by-step workflow instructions, tool usage patterns |
| 3 | **Supervisor routing** | `eagle-plugin/agents/supervisor/agent.md` | FAST vs DEEP delegation rules, which specialist handles what |
| 4 | **Trigger patterns** | YAML frontmatter in agent/skill `.md` files | When a specialist is activated (keyword matching) |
| 5 | **Skill context budget** | `MAX_SKILL_PROMPT_CHARS` in `strands_agentic_service.py` | How much of each skill prompt survives truncation (currently 4000 chars) |

### Lever Details

**Lever 1 — Agent Prompts** (`eagle-plugin/agents/*/agent.md`):
- 8 agents: supervisor, oa-intake, legal-counsel, market-intelligence, tech-translator, policy-analyst, public-interest, document-generator
- Each has domain knowledge, behavioral rules, and output format instructions
- Fix: Add missing domain knowledge, clarify ambiguous instructions, add examples

**Lever 2 — Skill Workflows** (`eagle-plugin/skills/*/SKILL.md`):
- 5+ skills with step-by-step workflows
- Skills are loaded as system_prompt content for specialist subagents
- Fix: Reorder steps, add tool-usage instructions, add FAR/DFARS references

**Lever 3 — Supervisor Routing** (`eagle-plugin/agents/supervisor/agent.md`):
- FAST path: direct tool calls (search_far, knowledge_search, web_search, query_compliance_matrix)
- DEEP path: spawn specialist subagent for complex analysis
- Fix: Adjust routing rules, add/remove FAST-path tools, clarify delegation criteria

**Lever 4 — Trigger Patterns** (YAML frontmatter):
- `triggers:` field in agent/skill YAML controls keyword activation
- Fix: Add missing trigger keywords, remove false-positive triggers

**Lever 5 — Context Budget** (`MAX_SKILL_PROMPT_CHARS`):
- Currently 4000 chars -- 9 of 15 skills exceed this and get truncated
- `_truncate_skill()` at line ~1131 of strands_agentic_service.py
- Fix: Increase budget (costs more tokens), or restructure skills to put critical content first

---

## Root Cause Categories

Every failing test maps to one of these root causes:

| Code | Root Cause | Typical Lever | Example |
|------|-----------|---------------|---------|
| `ROUTING` | Supervisor sent query to wrong specialist or used FAST when DEEP was needed | Lever 3 (supervisor routing) | Test expects legal_counsel but supervisor answered directly |
| `PROMPT` | Specialist's prompt lacks required domain knowledge or instructions | Lever 1 (agent prompts) | Legal agent doesn't mention FAR 6.302 for sole source |
| `TOOL` | Expected tool wasn't called, or tool returned wrong data | Lever 2 (skill workflows) | Document generator doesn't call create_document |
| `TRUNCATION` | Skill prompt was truncated, losing critical instructions | Lever 5 (context budget) | OA-intake skill loses steps 8-12 of its workflow |
| `DATA` | Test assertion is wrong or threshold too strict for the model | Test file only | Haiku can't reliably produce 5/8 indicators |
| `BUDGET` | Total prompt exceeds context window or cost threshold | Lever 5 + Lever 1 | Supervisor prompt + skill prompts exceed model's context |

---

## Phase 1: DIAGNOSE

Classify every failing test by root cause.

### Step 1.1: Gather Results

```bash
# Option A: Read latest results file
cat data/eval/results/latest.json 2>/dev/null | python -m json.tool | head -100

# Option B: Run targeted eval (if no recent results)
cd server && python tests/test_strands_eval.py --model us.anthropic.claude-3-5-haiku-20241022-v1:0 --tests {failing_test_ids} 2>&1
```

### Step 1.2: For Each Failing Test, Classify Root Cause

Read the test function to understand what it expects, then read the test output to understand what happened:

1. **Read the test function** in `test_strands_eval.py`:
   - What prompt does it send?
   - What text assertions does it check? (PRESENT/ABSENT keywords)
   - What tool calls does it expect?
   - What threshold does it use?

2. **Read the test output** (from results JSON or stdout):
   - Did the agent respond at all? (`summary_ok` check)
   - Which assertions passed vs failed?
   - Was a tool called? Which one?
   - Was the query routed to the right specialist?

3. **Classify** using the root cause table above. Use this decision tree:

```
Did the agent respond at all?
  No -> ROUTING (query went to wrong agent that couldn't answer)
  Yes ->
    Was the right specialist invoked?
      No -> ROUTING
      Yes ->
        Did the specialist call the expected tools?
          No ->
            Is the tool mentioned in the skill prompt?
              No -> TOOL (skill workflow missing tool instruction)
              Yes, but skill is >4000 chars ->
                Is the tool instruction in the truncated portion?
                  Yes -> TRUNCATION
                  No -> PROMPT (specialist ignored instruction)
              Yes, and skill is <4000 chars -> PROMPT
          Yes ->
            Are the text assertions reasonable for this model?
              No -> DATA (threshold too strict)
              Yes -> PROMPT (specialist produced wrong content)
```

### Step 1.3: Build Diagnosis Table

```
| Test | Name | Root Cause | Lever | Detail |
|------|------|-----------|-------|--------|
| 61 | uc01_new_acquisition_e2e | ROUTING | 3 | Supervisor answered directly instead of delegating to oa-intake |
| 73 | generate_sow_with_sections | TRUNCATION | 5 | SOW template in doc-gen skill is at char 4200, gets cut |
| 84 | legal_risk_rating_propagates | PROMPT | 1 | Legal agent prompt doesn't mention risk ratings |
```

---

## Phase 2: PRIORITIZE

Rank fixes by impact (how many tests they unblock) and cost (how risky the change is).

### Priority Rules

1. **ROUTING fixes first** — one routing fix in supervisor/agent.md can unblock multiple tests
2. **TRUNCATION fixes second** — increasing budget or restructuring skill content is low-risk
3. **PROMPT fixes third** — adding domain knowledge to specialist prompts
4. **TOOL fixes fourth** — modifying skill workflows
5. **DATA fixes last** — adjusting test thresholds (only after confirming the agent is actually correct)

### Group by Lever

Group fixes that target the same file to minimize edits:

```
supervisor/agent.md:
  - Add explicit DEEP delegation rule for UC-01 intake queries
  - Add "risk rating" to legal-counsel routing triggers

legal-counsel/agent.md:
  - Add FAR 6.302 sole source knowledge
  - Add risk rating output format

MAX_SKILL_PROMPT_CHARS:
  - Consider increasing from 4000 to 6000 (impacts 9 skills)
```

---

## Phase 3: FIX

Apply changes to the actual agent/skill/routing files. **Show the user what you're changing and why before making edits.**

### Fix Template

For each fix:

1. **Read the current file** (agent.md, SKILL.md, or strands_agentic_service.py)
2. **Show the proposed change** to the user:
   ```
   FIX: {root_cause} -> {lever}
   File: eagle-plugin/agents/legal-counsel/agent.md
   Change: Add FAR 6.302 sole source authority knowledge
   Tests affected: 44, 84
   Risk: LOW (additive change, no existing behavior removed)
   ```
3. **Make the edit** using the Edit tool
4. **Log the change** for Phase 4 validation

### Fix Patterns by Root Cause

**ROUTING fix** (Lever 3 — supervisor/agent.md):
```markdown
# In the DEEP DELEGATION section, add:
- For acquisition intake queries (new package, requirements gathering, CT scanner, MRI):
  -> ALWAYS delegate to oa-intake specialist
- For legal questions (sole source, J&A, FAR authority, risk rating):
  -> ALWAYS delegate to legal-counsel specialist
```

**PROMPT fix** (Lever 1 — agents/*/agent.md):
```markdown
# In the specialist's domain knowledge section, add:
## FAR 6.302 — Sole Source Authority
- FAR 6.302-1: Only one responsible source
- Requires J&A document
- SPE approval required above $750K (simplified acquisition threshold)
```

**TRUNCATION fix** (Lever 5 — strands_agentic_service.py):
```python
# Option A: Increase budget
MAX_SKILL_PROMPT_CHARS = 6000  # was 4000

# Option B: Restructure skill to put critical content first
# (edit the SKILL.md to front-load essential instructions)
```

**TOOL fix** (Lever 2 — skills/*/SKILL.md):
```markdown
# In the workflow steps, add:
## Step 5: Generate Document
When the user requests a document (SOW, IGCE, AP, J&A):
1. Call `create_document` with document_type and content
2. Confirm the document was saved to S3
3. Provide the download link
```

**DATA fix** (test file only):
```python
# Lower threshold if the model is consistently producing
# correct content but missing one optional indicator
threshold = 3  # was 4 -- Haiku reliably hits 3/5 indicators
```

---

## Phase 4: VALIDATE

Re-run the affected tests to confirm the fixes work.

### Step 4.1: Re-run Affected Tests

```bash
cd server && python tests/test_strands_eval.py \
  --model us.anthropic.claude-3-5-haiku-20241022-v1:0 \
  --tests {comma_separated_affected_test_ids} 2>&1
```

### Step 4.2: Compare Results

| Test | Before | After | Fix Applied |
|------|--------|-------|-------------|
| 61 | FAIL | PASS | Supervisor routing rule added |
| 73 | FAIL | PASS | MAX_SKILL_PROMPT_CHARS increased to 6000 |
| 84 | FAIL | FAIL | Legal prompt updated but still missing risk format |

### Step 4.3: Iterate

If tests still fail after fixes:
1. Re-diagnose — was the root cause classification correct?
2. Check if the fix was applied correctly
3. Try a different lever
4. If the model simply can't produce the expected output, classify as DATA and adjust the test

### Step 4.4: Regression Check

Run a broader set to make sure fixes didn't break passing tests:

```bash
# Run the category containing the fixed tests
cd server && python tests/test_strands_eval.py \
  --model us.anthropic.claude-3-5-haiku-20241022-v1:0 \
  --tests {category_range} 2>&1
```

---

## Phase 5: RECORD (Expertise Update)

After fixes are validated, update expertise.md with what was learned. This is the traditional self-improve step, but now it's informed by actual code changes.

### Update Sections

1. **Learnings -> patterns_that_work**: Record which levers worked for which root causes
2. **Learnings -> patterns_to_avoid**: Record approaches that didn't work
3. **Learnings -> tips**: Record specific fixes that helped
4. **Part 1 -> Test Suite Architecture**: Update test counts if tests were added/modified
5. **last_updated**: Update timestamp

```markdown
### patterns_that_work
- ROUTING: Adding explicit "ALWAYS delegate to {specialist}" rules in supervisor/agent.md
  for UC-specific queries prevents the supervisor from answering directly
  (discovered: {date}, tests: 61-72)

### tips
- When Haiku fails text assertions that Sonnet passes, check if the specialist prompt
  contains the expected keywords — Haiku follows prompts more literally and needs
  explicit keyword inclusion rather than implicit domain knowledge
```

---

## Report Format

```
## Self-Improve Report

### Mode: {diagnose | fix | full}
### Model: {model used}
### Tests Analyzed: {N}

### Diagnosis Summary

| Root Cause | Count | Tests |
|-----------|-------|-------|
| ROUTING   | 3     | 61, 63, 65 |
| PROMPT    | 5     | 44, 73, 84, 85, 87 |
| TRUNCATION| 2     | 73, 76 |
| TOOL      | 1     | 46 |
| DATA      | 4     | 77, 78, 80, 81 |
| BUDGET    | 0     | -- |

### Fixes Applied

| # | File | Lever | Change | Tests |
|---|------|-------|--------|-------|
| 1 | supervisor/agent.md | Routing | Added UC delegation rules | 61, 63, 65 |
| 2 | legal-counsel/agent.md | Prompt | Added FAR 6.302 knowledge | 44, 84 |
| 3 | strands_agentic_service.py | Budget | MAX_SKILL_PROMPT_CHARS 4000->6000 | 73, 76 |

### Validation Results

| Test | Before | After | Status |
|------|--------|-------|--------|
| 61 | FAIL | PASS | Fixed |
| 73 | FAIL | PASS | Fixed |
| 84 | FAIL | FAIL | Needs iteration |

### Pass Rate Change
- Before: 24/98 (24.5%)
- After:  37/98 (37.8%)
- Delta:  +13 tests (+13.3%)

### Learnings Recorded
- {N} patterns added to expertise.md
```

---

## Dry Run Mode

When `--dry-run` is set:
- Phase 1 (DIAGNOSE): runs normally, produces full diagnosis table
- Phase 2 (PRIORITIZE): runs normally, produces ranked fix list
- Phase 3 (FIX): shows proposed changes but does NOT edit files
- Phase 4 (VALIDATE): skipped entirely

Use dry-run to preview the diagnosis before committing to changes.

---

## Instructions

1. **Always read the test function first** -- understand what it expects before diagnosing why it failed
2. **Never skip Phase 1** -- misclassifying root cause leads to wasted fixes
3. **Show proposed changes to the user** before editing agent/skill files
4. **One lever at a time** -- don't change routing AND prompt in the same fix; isolate variables
5. **Re-run after every fix** -- don't batch multiple fixes then hope they all work
6. **DATA fixes are last resort** -- adjust test thresholds only after confirming the agent is actually correct and the assertion is too strict
7. **Preserve existing behavior** -- additive changes only unless removing something is clearly wrong
8. **Log everything** -- the diagnosis table and fix list are the artifacts that make this reproducible

---

## Integration with Other Commands

| Command | Relationship |
|---------|-------------|
| `/experts:eval:maintenance` | Run this first to get fresh results, then run self-improve |
| `/experts:eval:plan_build_improve` | Use for adding NEW tests; use self-improve for fixing EXISTING failures |
| `/experts:eval:add-test` | Use after self-improve if diagnosis reveals missing test coverage |
| `/experts:eval:question` | Use to understand test patterns before diagnosing |
