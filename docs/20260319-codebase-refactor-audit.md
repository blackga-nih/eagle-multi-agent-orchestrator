# Codebase Refactor Audit

Status: Historical analysis. Use [`20260325-refactor-completion-plan.md`](/Users/hoquemi/Desktop/sm_eagle/docs/20260325-refactor-completion-plan.md) for current execution status and [`refactor-status-index.md`](/Users/hoquemi/Desktop/sm_eagle/docs/refactor-status-index.md) for document routing.

Date: 2026-03-19
Scope: repository structure, active runtime paths, frontend state layers, backend service boundaries, infrastructure overlap, documentation duplication, and source-control hygiene.

## Executive Summary

The codebase has a workable product core, but it is carrying too much transitional architecture in the active tree. The biggest problems are not isolated style issues; they are structural:

1. The backend runtime is concentrated into a few oversized files with unclear ownership boundaries.
2. Legacy and active orchestration paths still depend on each other, which keeps deprecated code in the production path.
3. The frontend contains two chat systems plus an older MCP-oriented conversation stack, each with separate persistence and state models.
4. Templates, diagrams, and architecture references are duplicated across multiple directories with no enforced single source of truth.
5. The repo includes generated artifacts and mixed-purpose infrastructure/documentation that make maintenance harder than it needs to be.

The first refactor goal should be simplification, not rewriting. The codebase needs clearer module boundaries, a retirement plan for legacy paths, and one canonical home for shared assets.

## Audit Method

This report is based on a direct repository audit of:

- active backend modules in `server/app/`
- active frontend routes, hooks, contexts, and component trees in `client/`
- infrastructure definitions in `infrastructure/`
- operational tooling in `Justfile` and deployment files
- documentation and plugin assets in `docs/` and `eagle-plugin/`

This is a static audit. It identifies refactor candidates with strong evidence from the source tree, but it does not replace runtime profiling or full behavioral regression testing.

## Highest-Priority Findings

### 1. Backend entrypoints are far too large and own too many responsibilities

Evidence:

- `server/app/main.py` is about 3,383 lines.
- `server/app/strands_agentic_service.py` is about 2,888 lines.
- `server/app/agentic_service.py` is about 3,736 lines.

Why this matters:

- `main.py` is acting as API composition root, route implementation, startup/shutdown lifecycle, telemetry entrypoint, feature flag layer, and migration compatibility layer.
- Changes in one concern increase regression risk in unrelated areas.
- Tests become harder to isolate because composition and behavior live in the same file.

Refactor direction:

- Split `main.py` into routers by domain: chat, sessions, admin, templates, workspaces, documents, health.
- Add a narrow application factory or bootstrapping module that wires middleware, startup hooks, config, and routers.
- Move route-local business logic into service modules rather than keeping behavior embedded in handlers.

### 2. Deprecated orchestration still anchors active code paths

Evidence:

- `README.md` declares `strands_agentic_service.py` active and `agentic_service.py` deprecated.
- `server/app/strands_agentic_service.py` still imports and reuses pieces from `agentic_service.py`.
- `server/app/eagle_tools_mcp.py` delegates to `execute_tool()` from `agentic_service.py`.
- `server/app/mcp_agent_integration.py` imports `AgenticService` from `agentic_service.py`.
- Multiple docs and issue trackers already note the need to remove this dependency.

Why this matters:

- The deprecated file cannot actually be archived.
- Tool execution, model exports, and compatibility helpers remain entangled.
- New work risks reinforcing the old abstraction instead of finishing the migration.

Refactor direction:

- Extract shared tool execution into a dedicated module, for example `server/app/tool_dispatch.py`.
- Move model/config exports to a small shared config module.
- Treat `agentic_service.py` as a compatibility adapter only, then retire it once imports are removed.
- Do not allow new feature work inside `agentic_service.py`.

### 3. Frontend has overlapping chat architectures

Evidence:

- `client/app/chat/page.tsx` uses `components/chat-simple/simple-chat-interface.tsx`.
- `client/app/chat-advanced/page.tsx` uses `components/chat/chat-interface.tsx`.
- `simple-chat-interface.tsx` is about 777 lines.
- `chat-interface.tsx` is about 712 lines.
- Both manage overlapping concerns: message state, streaming state, slash commands, session persistence, and generated document handling.

Why this matters:

- Parallel chat implementations drift quickly.
- Fixes to streaming, persistence, or document generation logic must be duplicated.
- The UI likely has one strategic path, but the code still maintains two first-class implementations.

Refactor direction:

- Decide which chat experience is canonical.
- Extract shared chat primitives: composer, transcript state, stream reducer, tool event handling, session sync, and document result handling.
- Move the non-canonical UI behind an explicit legacy/experimental boundary or remove it.

### 4. Frontend persistence is fragmented across multiple storage models

Evidence:

- `client/contexts/session-context.tsx` uses `use-local-cache.ts`.
- `client/hooks/use-local-cache.ts` writes to IndexedDB and localStorage.
- `client/lib/document-store.ts` separately manages localStorage for documents/packages.
- `client/hooks/use-agent-session.ts` plus `client/lib/conversation-store.ts` plus `client/lib/conversation-sync.ts` implement another persistence stack for MCP-style sessions.

Why this matters:

- The app now has multiple competing client persistence abstractions.
- Session, document, and conversation state are not centered around one domain model.
- It is difficult to reason about freshness, hydration, optimistic writes, and fallback behavior.

Refactor direction:

- Define a single client persistence strategy for the current product path.
- Consolidate chat session persistence and generated document persistence behind one storage facade.
- Move MCP/demo conversation persistence into an isolated feature area if it is still needed.
- Replace ad hoc fallback writes with explicit sync states and cache invalidation rules.

### 5. Templates are duplicated across the product and plugin trees

Evidence:

- `client/public/templates/`
- `eagle-plugin/data/templates/`
- The template filenames match one-for-one.

Why this matters:

- Content updates can silently diverge.
- The repo currently encourages copy-based reuse instead of a source-of-truth workflow.
- Template semantics already exist in several backend modules: `template_registry.py`, `template_service.py`, and `template_store.py`.

Refactor direction:

- Pick one canonical template source directory.
- Generate or sync the other consumer artifacts from that source during build or release.
- Add a small manifest describing template type, display label, version, and consumer targets.

### 6. Diagram source files are duplicated in multiple places

Evidence:

- `docs/architecture/diagrams/mermaid/`
- `docs/architecture/diagrams/mermaid-diagrams/mermaid/`
- `eagle-plugin/diagrams/mermaid/`
- Several files exist in all locations with the same names.

Why this matters:

- Design documentation becomes untrustworthy once multiple copies exist.
- The png renderings already differ in some matching files, which means drift is happening.

Refactor direction:

- Keep a single canonical source directory for diagram definitions.
- Treat rendered png files as generated artifacts.
- Replace duplicates elsewhere with links, generated outputs, or documented export steps.

### 7. The backend document/template layer has overlapping abstractions

Evidence:

- `template_registry.py`
- `template_service.py`
- `template_store.py`
- `document_store.py`
- `document_service.py`
- `document_ai_edit_service.py`
- `spreadsheet_edit_service.py`

Why this matters:

- The distinction between registry, storage, population, versioning, and editing is not obvious.
- The legacy agent layer also performs template/document responsibilities directly.
- Domain logic is split across service, store, and orchestration files without a clean boundary.

Refactor direction:

- Create explicit layers:
  - registry/catalog for known template metadata
  - persistence for tenant/customized templates
  - rendering/population for docx/xlsx/markdown generation
  - document lifecycle/versioning
- Remove direct template orchestration from chat-agent modules.
- Standardize naming: use `repository` or `store` consistently, and reserve `service` for business logic.

### 8. Workspace customization has naming and boundary problems

Evidence:

- `workspace_store.py`
- `wspc_store.py`
- both are active in imports from `main.py` and `strands_agentic_service.py`

Why this matters:

- Abbreviated module names obscure intent.
- Workspace entity lifecycle and workspace override lifecycle are split in a way that is not obvious from names.
- This is small but high-friction technical debt in a central admin/customization area.

Refactor direction:

- Rename `wspc_store.py` to something explicit such as `workspace_override_store.py`.
- Group related workspace modules into a subpackage.
- Add typed interfaces for “workspace”, “override”, and “resolved prompt source”.

### 9. Repository hygiene is weaker than it should be

Evidence:

- Tracked generated artifacts include `client/playwright-report/index.html` and `client/test-results/.last-run.json`.
- The repo tree contains local/generated directories like `.next`, `node_modules`, `.venv`, `.pytest_cache`, and `__pycache__` within working directories.
- The root still contains non-code clutter and scratch-like files.

Why this matters:

- Noise reduces signal in code review and repository navigation.
- Generated artifacts in git increase churn and merge conflicts.
- New contributors have a harder time separating source from output.

Refactor direction:

- Remove tracked test artifacts from version control.
- Tighten `.gitignore` enforcement and add a cleanup pass in CI or pre-commit.
- Keep root-level content to product code, core docs, and top-level operational files only.

### 10. Infrastructure options are overlapping and not clearly tiered

Evidence:

- `infrastructure/cdk-eagle/` is the primary CDK path.
- `infrastructure/cdk/` is deprecated but still present.
- `infrastructure/cloud_formation/` remains documented for stack creation.
- `infrastructure/terraform/` also exists.

Why this matters:

- Multiple IaC systems are acceptable only when ownership and support status are explicit.
- Right now the tree looks like four parallel approaches rather than one active approach plus archived references.

Refactor direction:

- Mark each infrastructure path with one of: active, reference-only, experimental, archived.
- Move reference-only systems under an `archive/` or `reference/` boundary.
- Make `README.md` and `docs/codebase-structure.md` match the real support policy.

### 11. The `Justfile` mixes platform assumptions and concerns

Evidence:

- Some recipes are standard Docker/Linux flows.
- Other recipes use Windows-specific commands like `taskkill` and `netstat -ano` inside bash recipes.
- Commands for dev, deploy, AWS validation, smoke tests, and local process management all live together.

Why this matters:

- Shared developer tooling becomes unpredictable across environments.
- A single task runner is useful, but it needs cleaner portability boundaries.

Refactor direction:

- Split recipes into portable core tasks and OS-specific wrappers.
- Prefer scripts in `scripts/` for complex logic rather than embedding long shell programs in `Justfile`.
- Group commands by concern: local dev, validation, deploy, infrastructure.

## Medium-Priority Findings

### 12. Documentation has drift between intended and actual architecture

Evidence:

- `docs/codebase-structure.md` describes a cleaner structure than the current runtime and repo organization actually enforce.
- multiple planning docs still reference earlier active paths such as `sdk_agentic_service.py` or older architecture assumptions.

Refactor direction:

- Keep architecture docs versioned or stamped by status.
- Archive superseded plans more aggressively.
- Maintain one current-system document for contributors.

### 13. Client mock/demo and production concerns are mixed together

Evidence:

- `client/lib/mock-data.ts` is one of the largest frontend files.
- admin and MCP/demo-oriented features coexist in the same application tree.

Refactor direction:

- Separate mock/demo fixtures from production app code.
- Gate demo-only features explicitly.
- Keep admin, experimental, and user-facing domains modular.

### 14. Directory naming is inconsistent and sometimes misleading

Examples:

- `client/` and `server/` are fine, but older docs suggest a different structure.
- `wspc_store.py` is opaque.
- `legacy`, `deprecated`, `reference`, and active files are not consistently grouped.

Refactor direction:

- Use naming to communicate lifecycle and responsibility.
- Reserve `legacy/`, `archive/`, or `reference/` for code that is not on the active path.

## Redundancy Map

The clearest redundant areas today are:

| Area | Redundancy | Risk | Recommendation |
| --- | --- | --- | --- |
| Chat UI | `chat/` and `chat-simple/` implementations | High | Make one canonical, extract shared core, archive the other |
| Agent runtime | `agentic_service.py`, `sdk_agentic_service.py`, `strands_agentic_service.py` | High | Extract shared tool/config layers and retire non-active adapters |
| Client persistence | `use-local-cache`, `document-store`, `use-agent-session` + conversation store | High | Consolidate around one active persistence model |
| Templates | `client/public/templates` and `eagle-plugin/data/templates` | High | One canonical source plus generated consumers |
| Diagrams | docs mermaid paths and plugin mermaid paths | Medium | One source directory plus generated outputs |
| Infrastructure | CDK, deprecated CDK, Terraform, CloudFormation | Medium | Explicit active/reference/archive split |
| Workspace customization | `workspace_store` and `wspc_store` | Medium | Rename and regroup under one workspace package |
| Docs/plans | multiple historical plans remain mixed with current guidance | Medium | Archive or index by status |

## Recommended Refactor Plan

### Phase 0: Stabilize the repository shape

Goals:

- stop adding to structural debt
- define active vs deprecated surfaces

Actions:

1. Declare canonical runtime paths in docs:
   - active chat UI
   - active backend orchestration path
   - active infrastructure path
2. Add a “do not add new features here” note to deprecated modules.
3. Remove tracked test artifacts from git.
4. Add a short refactor ownership document in `docs/` naming active and deprecated subsystems.

### Phase 1: Break up the backend monoliths

Goals:

- reduce regression risk
- make service boundaries explicit

Actions:

1. Extract FastAPI routers from `server/app/main.py` into a `routers/` package.
2. Create a shared config/bootstrap module for app setup and lifecycle.
3. Extract tool dispatch from `agentic_service.py`.
4. Move document/template orchestration out of agent runtime files into domain services.
5. Rename and reorganize workspace modules.

Exit criteria:

- `main.py` becomes mostly composition code.
- `agentic_service.py` is no longer imported by active runtime paths except an explicit compatibility adapter if still required.

### Phase 2: Consolidate frontend chat and persistence

Goals:

- remove duplicate product flows
- unify state handling

Actions:

1. Choose one chat UI as the supported experience.
2. Extract shared chat engine logic:
   - stream event reducer
   - tool call tracking
   - document generation/result normalization
   - session save/hydrate logic
3. Merge storage strategies behind one facade for sessions and generated docs.
4. Isolate MCP/demo conversation flows into a feature boundary or archive them.

Exit criteria:

- one primary chat implementation
- one persistence model for active user sessions

### Phase 3: Canonicalize shared assets

Goals:

- eliminate silent content drift

Actions:

1. Make templates single-source.
2. Make diagrams single-source.
3. Add generation/export scripts for consumer copies if copies are still required.
4. Document the ownership model for plugin-shared assets.

### Phase 4: Simplify repo operations and infrastructure posture

Goals:

- make the repo easier to operate and navigate

Actions:

1. Split `Justfile` by portability and concern.
2. Move reference-only infrastructure under an explicit archive/reference directory.
3. Update root and docs to match actual operational paths.
4. Remove stale or superseded planning docs from the “current” surface area.

## Suggested Target Architecture

This is the direction I would recommend, without forcing a full rewrite:

```text
server/app/
  api/
    routers/
      admin.py
      chat.py
      documents.py
      health.py
      templates.py
      workspaces.py
  core/
    config.py
    logging.py
    lifecycle.py
  domains/
    chat/
    documents/
    templates/
    workspaces/
    telemetry/
  integrations/
    aws/
    mcp/
    bedrock/
  legacy/
    agentic_service.py
    sdk_agentic_service.py

client/
  app/
  features/
    chat/
    documents/
    admin/
  shared/
    ui/
    hooks/
    lib/
  legacy/
    mcp/
```

The important part is not the exact folder names. The important part is moving from “files named by history” to “modules grouped by domain and lifecycle.”

## Best-Practice Rules To Adopt During Refactor

1. No new feature work in deprecated modules.
2. One source of truth for every shared asset class: templates, diagrams, config manifests.
3. One active chat path and one active client persistence model.
4. Router files should stay thin; business logic belongs in domain services.
5. Compatibility layers may call into active services, but active services should not call back into deprecated layers.
6. Generated artifacts must not be committed unless there is an explicit product reason.
7. Docs must declare status: current, reference, archived, or superseded.

## Recommended Work Order

If the goal is to improve maintainability with the least disruption, do the work in this order:

1. Backend extraction of `main.py` and tool dispatch separation.
2. Remove active dependencies on `agentic_service.py`.
3. Choose and consolidate the frontend chat path.
4. Unify client persistence.
5. Canonicalize templates and diagrams.
6. Clean infrastructure/reference boundaries.
7. Clean repo artifacts and documentation status markers.

## Quick Wins

These can be done immediately and safely:

- untrack `client/playwright-report/` and `client/test-results/`
- rename `wspc_store.py`
- add deprecation guards/comments to `agentic_service.py` and `sdk_agentic_service.py`
- create a single template source directory decision
- document which chat route is the supported one
- reduce `main.py` by extracting routers without changing behavior

## Longer-Term Risks If Left As-Is

- Every new feature will become slower to ship because too many layers must be updated together.
- Legacy compatibility code will continue to block cleanup.
- Asset drift will create subtle product inconsistencies.
- Onboarding and debugging costs will keep increasing.
- Tests will be harder to trust because the codebase does not cleanly reflect the supported architecture.

## Proposed Next Deliverables

After this report, the next useful artifacts would be:

1. A backend refactor plan for `server/app/main.py` and orchestration extraction.
2. A frontend consolidation plan for `chat-simple` vs `chat`.
3. A canonical asset ownership plan for templates and diagrams.
4. A cleanup PR that handles repo hygiene and low-risk renames first.
