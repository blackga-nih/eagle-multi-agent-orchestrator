# Plan: Bake Decision Tree into Compliance Skill

**Type:** plan  
**Slug:** compliance-decision-tree-matrix  
**Generated:** 2026-02-25

---

## 1. Current state

- **Compliance Skill** (agent source of truth): `eagle-plugin/skills/compliance/SKILL.md`. Covers FAR/DFAR/HHSAR, clauses by threshold, competition, vehicles, socioeconomic. It does **not** yet encode the full contract-requirements-matrix decision logic (e.g. $7.5M IDIQ, $150K VETS 4212, special factors, letter contract, GAO protest).
- **Contract requirements matrix**: `contract-requirements-matrix.html` — staff-facing, interactive. Contains the authoritative decision tree (THRESHOLDS, getRequirements(), TYPES, warnings/errors).
- **Deployment expert** at `.claude/commands/experts/deployment/` is the pattern for infra (plan / question / expertise / self-improve). The decision tree is **not** a new expert; it is domain logic owned by the Compliance Skill.

---

## 2. Target

- **Compliance agent** = Compliance **Skill**. The “compliance agent” in sequence diagrams is the skill invoked by the supervisor; its definition is `eagle-plugin/skills/compliance/SKILL.md`. “Baked into the compliance agents” means **baked into that single Compliance Skill**.

---

## 3. Implementation steps

| Step | Action |
|------|--------|
| **A** | Add a **canonical condensed** representation of the decision tree (e.g. under `eagle-plugin/skills/compliance/` or `eagle-plugin/data/`) — JSON or structured markdown: thresholds (all 14, including $150K, $7.5M), requirement rules (condition → document/warning/error + citation), and the 10 contract types (including FP/AF, Letter) with minimal attributes. |
| **B** | In **Compliance Skill** (`SKILL.md`), add a **“Decision tree (matrix alignment)”** section that: (1) states Compliance uses the **same** logic as the contract-requirements matrix for threshold → method → type → required docs/warnings; (2) enumerates the key thresholds and rules (or points to the condensed artifact); (3) documents special factors (animal welfare, foreign, conference), letter-contract rules, and IDIQ >$10M protest warning so the agent can reference them without reading the HTML. |
| **C** | Leave the matrix HTML as the **staff-facing UI**; the condensed artifact is the **agent-facing spec** so that OA Intake / Compliance flow “references the matrix” via that spec and the skill text. |
| **D** | **Do not** create a separate “decision tree” expert (no new expert command set). Deployment-style experts are for infra; the tree is domain logic owned by the Compliance Skill. |
| **E** | Optionally: in OA Intake Skill, add one line that for determination outcomes it defers to Compliance and the **same** matrix decision tree so eval and matrix stay in sync. |

---

## 4. Success criteria

- One place for “what the matrix says”: the condensed decision-tree spec + Compliance Skill text.
- Compliance is the single agent that “references the matrix”; no second expert.
- Matrix and Compliance (and thus OA Intake when it defers to Compliance) stay aligned on thresholds, required documents, and warnings.

---

## 5. Validation

- After implementation: spot-check that for representative scenarios (e.g. $85K simplified + sole source + FFP; $200K + animal welfare; letter + micro) the Compliance Skill text and the matrix yield the same required docs and warnings.
