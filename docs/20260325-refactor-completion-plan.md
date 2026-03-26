# Refactor Completion Plan

Date: 2026-03-25
Status: Draft
Scope: Remaining work needed to consider the March 2026 refactor complete
Source references:
- `docs/20260319-codebase-refactor-audit.md`
- `docs/refactor_0319.md`
- `docs/plans/20260318-chat-thread-phase1-stabilization-plan.md`
- `docs/plans/20260318-chat-thread-phase2-concurrent-generation-plan.md`
- `docs/plans/20260320-chat-persistence-implementation-plan.md`

---

## Executive Summary

The codebase has partially implemented the refactor direction from the March 19 audit, but it is not complete.

The biggest remaining gaps are:

1. The active Strands runtime still depends heavily on `agentic_service.py`.
2. Workspace override resolution was renamed at the store layer but not fully updated in the Strands runtime.
3. Backend router extraction has started, but `main.py` is still the real application hub.
4. Frontend chat stabilization landed on the primary path, but the app still carries two live chat stacks.
5. Shared backend/frontend abstractions exist, but several old implementations still remain active beside them.
6. Asset duplication called out in the audit still exists for templates and diagrams.
7. Validation and test environments are not in a state that reliably prove the refactor is safe.

The refactor should not be considered complete until the active runtime no longer relies on renamed or deprecated boundaries and the intended module ownership is actually enforced in production paths.

---

## What Appears Complete

These areas show meaningful progress and should be preserved:

### 1. Chat thread persistence and runtime isolation on the primary `/chat` path

Implemented pieces:
- Explicit session-scoped persistence in `client/hooks/use-local-cache.ts`
- Session context updated to accept explicit `sessionId`
- Per-session runtime reducer in `client/contexts/chat-runtime-context.tsx`
- Session-scoped transport manager in `client/lib/chat-stream-manager.ts`
- Sidebar streaming indicator in `client/components/layout/sidebar-nav.tsx`
- Main chat route using the new simple chat stack in `client/app/chat/page.tsx`

Implication:
- The Phase 1 / Phase 2 chat-thread stabilization work mostly landed for the main user path.

### 2. Shared AWS client extraction exists

Implemented piece:
- `server/app/db_client.py`

Implication:
- The intended direction exists, but adoption is incomplete.

### 3. Workspace override naming cleanup exists at the store layer

Implemented piece:
- `server/app/workspace_override_store.py`

Implication:
- The rename happened, but downstream callers were not fully updated.

### 4. Router package exists

Implemented piece:
- `server/app/routers/`

Implication:
- Structural extraction started, but the application composition has not caught up.

---

## Remaining Work by Priority

## Priority 0: Fix live regressions created or exposed by the refactor

These are not optional cleanup tasks. They are active correctness risks.

### P0.1 Update all stale `wspc_store` imports to `workspace_override_store`

Problem:
- The renamed workspace override module is still referenced by the old import path inside the active Strands runtime.
- Those imports are wrapped in `try/except`, so the app can silently degrade instead of crashing.

Current evidence:
- `server/app/strands_agentic_service.py:3090`
- `server/app/strands_agentic_service.py:3217`

Current behavior:
- When `workspace_id` is provided, prompt resolution attempts to import `.wspc_store`.
- That import no longer exists.
- The code falls back to bundled prompts and logs a warning.
- Result: workspace-level prompt overrides may be ignored in live requests.

Why this matters:
- This is a feature-loss risk after the rename.
- It undermines one of the refactor’s intended improvements: clearer workspace override ownership.

Required work:
1. Replace all `from .wspc_store import ...` imports with `from .workspace_override_store import ...`.
2. Replace stale log messages referencing `wspc_store`.
3. Search for all remaining references to `wspc_store` in backend docs and runtime code.
4. Add or update tests that prove workspace overrides affect:
   - skill prompt resolution
   - supervisor prompt resolution
   - fallback behavior when no override exists

Definition of done:
- No active runtime import references `wspc_store`.
- Workspace override tests pass against the Strands path.
- Logs use the new module name consistently.

### P0.2 Eliminate silent fallback for missing renamed modules in critical prompt paths

Problem:
- The runtime currently hides import/path mistakes behind broad exception handling.

Current evidence:
- `server/app/strands_agentic_service.py:3088-3094`
- `server/app/strands_agentic_service.py:3215-3220`

Why this matters:
- Silent fallback makes real regressions look like configuration misses.
- Users can lose workspace behavior without an obvious operational signal.

Required work:
1. Narrow exception handling around workspace prompt resolution.
2. Distinguish:
   - missing override data
   - store/network errors
   - code/import regressions
3. Promote code/import regressions to explicit error logging with high visibility.
4. Add telemetry or structured logging for prompt-source selection.

Definition of done:
- Workspace resolution failures are observable and attributable.
- Code-path regressions cannot hide as normal fallback behavior.

---

## Priority 1: Finish the backend runtime migration off deprecated orchestration

This is the largest unfinished refactor item.

### P1.1 Remove direct imports from `agentic_service.py` in the active Strands runtime

Problem:
- The active runtime is still coupled to the deprecated orchestration layer.

Current evidence:
- `server/app/strands_agentic_service.py:938`
- `server/app/strands_agentic_service.py:985`
- `server/app/strands_agentic_service.py:1568`
- `server/app/strands_agentic_service.py:1675`
- `server/app/strands_agentic_service.py:2264`
- `server/app/strands_agentic_service.py:2922`

Current behavior:
- The Strands service still imports `_exec_create_document`, `_exec_search_far`, and `TOOL_DISPATCH` from `agentic_service.py`.

Why this matters:
- `agentic_service.py` is still part of the production path.
- The deprecated module cannot be retired.
- New runtime behavior still depends on a monolith the refactor intended to isolate.
- It raises regression risk because legacy and active concerns remain entangled.

Required work:
1. Define a canonical shared dispatch boundary for tools used by Strands.
2. Move active tool handlers out of `agentic_service.py` into dedicated modules, likely under:
   - `server/app/tools/`
   - or a new `server/app/tool_dispatch/` package
3. Replace all Strands imports of `agentic_service` with imports from that new boundary.
4. Limit `agentic_service.py` to compatibility-only usage, or archive it entirely after active imports are removed.

Suggested extraction groups:
- document tools
  - `create_document`
  - `edit_docx_document`
  - document lookup/changelog/finalization
- research tools
  - `search_far`
  - web/knowledge/retrieval dispatch
- intake/workflow tools
  - intake state
  - package/finalization workflows
- admin/configuration tools
  - manage skills
  - manage prompts
  - manage templates

Definition of done:
- `strands_agentic_service.py` no longer imports from `agentic_service.py`.
- `eagle_tools_mcp.py` no longer depends on `agentic_service.py` directly or indirectly for active tools.
- `agentic_service.py` is explicitly marked compatibility-only or archived.

### P1.2 Replace `TOOL_DISPATCH` monolith usage with explicit tool modules

Problem:
- Tool registration is still effectively controlled by `agentic_service.py`.

Current evidence:
- `server/app/agentic_service.py:3787`
- `server/app/strands_agentic_service.py:1738`
- `server/app/strands_agentic_service.py:2309`
- `server/app/strands_agentic_service.py:2505`
- multiple later call sites

Why this matters:
- One large dispatch table keeps ownership unclear.
- It prevents clear runtime boundaries.
- It makes partial migration easy to start and easy never to finish.

Required work:
1. Create explicit registration for active tools outside `agentic_service.py`.
2. Group tools by domain and ownership.
3. Make the Strands runtime consume a single active registry owned by active modules.
4. Keep any legacy registry behind a compatibility adapter only.

Definition of done:
- The active tool registry lives outside `agentic_service.py`.
- The active Strands path does not import `TOOL_DISPATCH` from legacy code.

### P1.3 Clarify the role of `sdk_agentic_service.py`

Problem:
- The codebase now has:
  - `agentic_service.py`
  - `sdk_agentic_service.py`
  - `strands_agentic_service.py`

Why this matters:
- The migration path is not fully closed.
- Future work can accidentally target the wrong orchestration layer.

Required work:
1. Decide whether `sdk_agentic_service.py` is:
   - compatibility-only
   - reference-only
   - still supported
2. Mark that status in code comments and documentation.
3. Remove any runtime references if it is no longer active.

Definition of done:
- There is exactly one documented active orchestration runtime.
- All other orchestration modules have explicit support status.

---

## Priority 2: Finish the backend application boundary refactor

### P2.1 Move active API composition out of `main.py`

Problem:
- The audit called for `main.py` to become a narrow app factory and router bootstrap.
- That did not happen in practice.

Current evidence:
- `server/app/main.py` is still 4,263 lines.
- Only the streaming router is explicitly included:
  - `server/app/main.py:2656`
  - `server/app/main.py:2657`

Why this matters:
- `main.py` still owns too many concerns.
- The router package exists but is not the true entrypoint structure.
- This keeps the monolithic risk profile the refactor was meant to lower.

Required work:
1. Audit which endpoints are still implemented directly in `main.py`.
2. Move them into domain routers, at minimum:
   - chat
   - sessions
   - documents
   - templates
   - packages
   - admin
   - workspaces
   - health
   - analytics
3. Create an application factory or composition module responsible only for:
   - config loading
   - middleware
   - lifespan hooks
   - router inclusion
4. Leave thin compatibility shims only where migration sequencing requires it.

Definition of done:
- `main.py` is substantially reduced.
- Domain routers own route handlers.
- Application startup and route behavior are separated.

### P2.2 Ensure `server/app/routers/` is the real runtime path, not a side structure

Problem:
- The router package may currently be structural scaffolding rather than the actual application boundary.

Required work:
1. Map each router file to active endpoints.
2. Remove duplicate route implementations between routers and `main.py`.
3. Ensure router-level dependencies are consistently used.
4. Add endpoint smoke tests that validate router ownership.

Definition of done:
- Every active endpoint belongs to one clear router module.
- There is no duplicated route logic in `main.py`.

---

## Priority 3: Consolidate frontend chat architecture

Status:
- Completed for active route ownership and shared-type decoupling.
- `/chat` is the supported chat entrypoint.
- `/chat-advanced` is a compatibility redirect to `/chat`.
- The legacy advanced component tree has been removed; only shared controls still used by the simple chat runtime remain.

### P3.1 Decide whether `chat-advanced` remains supported

Problem:
- Two chat stacks were live:
  - `/chat` used `SimpleChatInterface`
  - `/chat-advanced` used `ChatInterface`

Current state:
- `client/app/chat/page.tsx` remains the supported chat route.
- `client/app/chat-advanced/page.tsx` now redirects to `/chat`.
- The removed `client/components/chat/chat-interface.tsx` stack no longer participates in production routing.

Why this matters:
- Streaming, persistence, and UX improvements must still be evaluated twice.
- Shared types still depend on the legacy advanced component file.
- The audit explicitly called this overlap out as a refactor target.

Completed work:
1. `chat-advanced` was treated as removable from active architecture.
2. The route was reduced to a compatibility redirect.
3. The dead advanced component tree was deleted after shared dependencies were removed.

Definition of done:
- There is one clearly documented primary chat architecture.
- Non-primary chat code is either isolated or removed.

Status:
- Done.

### P3.2 Remove shared frontend type coupling to `chat-interface.tsx`

Problem:
- Shared contexts and hooks previously imported types from the legacy advanced chat component.

Current state:
- Shared contexts, hooks, checklist, summary, and hydration modules now use shared types from `client/types/chat.ts` and `client/types/schema.ts`.
- Production code no longer imports shared types from `@/components/chat/chat-interface`.

Why this matters:
- Shared application state still depends on a UI component file.
- This prevents clean separation between shared domain types and presentation code.

Completed work:
1. Shared message, document, and acquisition types were standardized on `client/types/chat.ts` and `client/types/schema.ts`.
2. Shared hooks and contexts were updated to consume those types directly.
3. The remaining type-only coupling in the legacy message list was removed before that file was deleted.

Definition of done:
- Contexts, hooks, and stores do not import types from component implementation files.

Status:
- Done.

### P3.3 Finish chat runtime adoption consistently

Problem:
- The simple chat path uses the new runtime model.
- The advanced path previously had its own request tracking and local streaming logic.

Why this matters:
- The codebase still carries duplicate solutions to the same problem.

Completed work:
1. The simple chat runtime remained the canonical implementation.
2. The advanced path was isolated as compatibility-only and then removed from the active component tree.
3. Shared runtime state remains owned by the simple chat architecture.

Definition of done:
- There is one supported runtime model for active chat behavior.

Status:
- Done.

Definition of done:
- Only one active chat runtime model exists for supported chat surfaces.

---

## Priority 4: Finish shared abstraction adoption

### P4.1 Complete adoption of `db_client.py`

Problem:
- The shared AWS client module exists, but duplicate singleton helpers still remain.

Current evidence:
- `server/app/tag_store.py`
- `server/app/template_service.py`
- `server/app/document_ai_edit_service.py`
- `server/app/spreadsheet_edit_service.py`
- `server/app/agentic_service.py`

Why this matters:
- The duplication reduction promised by the refactor is incomplete.
- Testing and configuration are still inconsistent across modules.

Required work:
1. Replace local `_get_dynamodb()` / `_get_s3()` helpers with imports from `db_client.py`.
2. Standardize helper usage for:
   - `get_table`
   - `get_s3`
   - `item_to_dict`
   - `now_iso`
3. Remove duplicate conversion/time helper implementations where possible.

Definition of done:
- No active store/service duplicates core AWS singleton patterns unless there is a documented exception.

### P4.2 Standardize naming and ownership for document/template services

Problem:
- The audit identified overlapping abstractions across:
  - `template_registry.py`
  - `template_service.py`
  - `template_store.py`
  - `document_store.py`
  - `document_service.py`
  - edit services

Why this matters:
- The boundary between registry, persistence, rendering, versioning, and editing is still not consistently obvious.

Required work:
1. Define ownership for each module family.
2. Document the expected layers:
   - registry/catalog
   - persistence
   - rendering/population
   - document lifecycle/versioning
   - edit/preview services
3. Move mis-owned functionality to the correct layer.
4. Rename modules if necessary for consistency.

Definition of done:
- A developer can infer responsibility from module names and package location.
- Chat/orchestration layers no longer own document logic directly.

---

## Priority 5: Complete repo hygiene and canonical asset ownership

### P5.1 Resolve duplicated template trees

Status:
- Partially completed.
- `eagle-plugin/data/templates/` remains intentionally retained as a backend schema/completeness input.
- Active runtime template loading for generation is owned by the S3/template registry path, not by a duplicate frontend/public template tree.
- Remaining work is mostly documentation and ownership labeling, not runtime behavior extraction.

Problem:
- Templates still exist in multiple source directories.

Current evidence:
- `client/public/templates/`
- `eagle-plugin/data/templates/`

Why this matters:
- Template drift remains possible.
- The audit’s “single source of truth” goal is not complete.

Current direction:
1. Treat S3/template-registry content as the runtime document-generation source.
2. Treat `eagle-plugin/data/templates/` as legacy schema guidance input consumed by `template_schema.py`.
3. Avoid introducing new manual consumer copies.
4. Document this split explicitly until or unless schema extraction moves fully to metadata sidecars.

Definition of done:
- One directory is the source of truth.
- Other copies are generated or eliminated.

### P5.2 Resolve duplicated diagram trees

Status:
- Completed for duplicate docs-owned authoring copies.
- Canonical docs-owned authoring paths are:
  - `docs/architecture/diagrams/excalidraw/`
  - `docs/architecture/diagrams/mermaid/`
- Duplicate copies under `docs/excalidraw-diagrams/` and `docs/architecture/diagrams/mermaid-diagrams/mermaid/` were removed.

Problem:
- Mermaid diagram sources still exist in multiple trees.

Current evidence:
- `docs/architecture/diagrams/mermaid/`
- `docs/architecture/diagrams/mermaid-diagrams/mermaid/`
- `eagle-plugin/diagrams/mermaid/`

Why this matters:
- Architecture docs can drift.
- The audit explicitly flagged this as an ongoing source-of-truth problem.

Completed work:
1. Chose `docs/architecture/diagrams/excalidraw/` and `docs/architecture/diagrams/mermaid/` as canonical docs-owned diagram sources.
2. Removed duplicate docs-owned authoring copies.
3. Updated top-level documentation to point at the canonical location.

Remaining work:
1. Decide whether `eagle-plugin/diagrams/` is a generated/plugin-consumer tree or a separate plugin-owned artifact set.
2. Document the export/generation workflow if plugin copies are still required.

Definition of done:
- There is one canonical diagram source tree.
- Duplicate authoring copies are gone.

### P5.3 Clean up historical plans vs active plans in `docs/`

Problem:
- The audit called out documentation surface-area confusion.
- Plans and audits are mixed together without strong status signaling.

Why this matters:
- Engineers can follow stale guidance.
- Refactor completion is harder to assess when historical and active plans look equally current.

Required work:
1. Mark current plans explicitly as:
   - active
   - completed
   - superseded
   - archive/reference
2. Add a short `docs/` index for refactor ownership and current status.
3. Archive superseded planning docs from the active surface area.

Definition of done:
- An engineer can quickly tell which refactor docs are current and which are historical.

---

## Validation and Testing Work Needed

The refactor is not complete until the validation story is credible.

### V1. Restore a reliable local/backend test environment

Observed issues during review:
- `server/.venv/bin/pytest` can run, but:
  - `test_perf_simple_message.py` fails because `strands` is missing
  - `test_sdk_query_streaming.py` fails because async pytest support is not configured in the current environment

Why this matters:
- The repository cannot currently prove that the migrated runtime still works.
- Refactor completion without reliable validation is mostly cosmetic.

Required work:
1. Ensure the server venv includes required runtime/test dependencies.
2. Fix pytest async plugin/config mismatch.
3. Document the canonical test bootstrap path.
4. Make CI enforce the same runtime assumptions developers rely on locally.

Definition of done:
- Critical server tests run successfully in a clean local environment and CI.

### V2. Add targeted regression coverage for refactor-sensitive paths

Minimum required regression areas:
- workspace override prompt resolution on Strands path
- Strands tool dispatch without legacy monolith imports
- streaming/session isolation on `/chat`
- document generation and package flows after tool extraction
- MCP tool bridge behavior if still supported
- template and document lifecycle flows

Definition of done:
- Every major extracted/refactored boundary has at least one regression test proving behavior still works.

---

## Suggested Execution Order

The safest completion order is:

1. Fix the renamed workspace override imports and related fallback behavior.
2. Extract active tool dispatch out of `agentic_service.py`.
3. Reduce Strands runtime dependencies on legacy orchestration until zero.
4. Move live route handlers from `main.py` into the router package.
5. Decide the fate of `chat-advanced` and remove shared type coupling.
6. Finish `db_client.py` adoption and service/store boundary cleanup.
7. Remove duplicated templates and diagrams by establishing canonical ownership.
8. Repair and enforce the test environment.
9. Archive or re-label superseded plans and write a short refactor status index.

---

## Completion Criteria

The refactor should be considered complete only when all of the following are true:

1. The active Strands runtime does not import `agentic_service.py`.
2. Workspace override resolution uses `workspace_override_store.py` everywhere in active code.
3. `main.py` acts as an application bootstrap, not the primary route implementation surface.
4. Only one clearly supported chat architecture remains active, or multiple are explicitly isolated by support status.
5. Shared hooks and contexts do not depend on component implementation files for types.
6. `db_client.py` is the standard AWS client access path across active modules.
7. Templates and diagrams each have one canonical source of truth.
8. Critical regression tests pass in a reproducible environment.
9. Refactor-related docs clearly distinguish active guidance from historical analysis.

Active doc routing:
- Current execution/status source: [`refactor-status-index.md`](/Users/hoquemi/Desktop/sm_eagle/docs/refactor-status-index.md)
- Canonical asset ownership source: [`architecture/asset-ownership.md`](/Users/hoquemi/Desktop/sm_eagle/docs/architecture/asset-ownership.md)

---

## Recommended Next Deliverables

If this plan is to be executed as actual work, the next concrete deliverables should be:

1. A small PR fixing `wspc_store` references and adding workspace override regression tests.
2. A backend tool-dispatch extraction PR removing the first set of Strands imports from `agentic_service.py`.
3. A backend app-composition PR wiring active routers into the FastAPI app.
4. A repo-ownership cleanup PR for templates, diagrams, and doc status labeling.
