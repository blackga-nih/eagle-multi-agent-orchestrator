# Projects and Chats UX Plan (ChatGPT-Style)

Branch target: `feature/projects-and-chats-ui`
Primary scope: frontend UX architecture, project/chat navigation, project-level context, and supporting APIs.

## 1. Executive Summary

Introduce a first-class `Project` container with multiple chats underneath, similar to ChatGPT Projects:

1. Users can create a project (for example, "Acquisition Package - CT Scanner").
2. Users can create many chats inside that project.
3. Project-level context (documents, package linkage, sources) is shared across chats.
4. Session/chat remains lightweight, but project becomes the context anchor.

This is the UX layer that complements the canonical document/package backend flow.

## 2. Product Objectives

1. Make "attach to existing package" practical even with many packages.
2. Reduce context fragmentation across multiple chats on one acquisition effort.
3. Separate random Q&A chats from package-bound work.
4. Keep navigation simple and familiar for users already using ChatGPT-style UIs.

## 3. User Experience Model

## 3.1 Core Concepts

1. `Project` = top-level container for a business effort.
2. `Chat` = conversational thread inside project.
3. `Package` = acquisition artifact lifecycle object (can be linked 1:1 or 1:many depending policy).

Recommended default policy:

1. Project may have one `primary_package_id`.
2. Chats inherit project package context by default.
3. Individual chat can override to one-off mode.

## 3.2 Navigation Layout

Left rail:

1. Global actions (`New chat`, `Search chats`).
2. Projects section:
   - `New project`
   - Project list (recently updated, searchable)
3. Within selected project:
   - `New chat in <Project>`
   - Chat list (sortable/filterable)
   - Optional Sources tab

Main pane:

1. Project header (`name`, `status`, `linked package`, metadata chips).
2. Chat transcript/editor area.
3. Context indicators:
   - `Package mode on/off`
   - `Active package`
   - `Docs generated in project`

## 3.3 Key User Flows

### Flow A: Create new project and first chat

1. User clicks `New project`.
2. Enters project name and optional package linkage.
3. Lands in empty project view.
4. Clicks `New chat in project`.
5. Chat starts with inherited project context.

### Flow B: Attach chat to existing package in project

1. Chat asks to generate package doc and no active package is set.
2. UI opens attach modal scoped to project:
   - recent packages
   - search by id/title
   - filters by status/owner
3. User selects package and confirms.
4. Chat metadata and project metadata update.

### Flow C: One-off random question inside project

1. User asks FAR question.
2. Chat remains in project but no package mutation occurs.
3. Results available in chat history; no artifact checklist updates.

## 4. Data Model Changes

## 4.1 New Entities

### PROJECT#

Proposed DynamoDB shape:

1. `PK = PROJECT#{tenant_id}`
2. `SK = PROJECT#{project_id}`
3. Attributes:
   - `project_id`
   - `tenant_id`
   - `owner_user_id`
   - `name`
   - `description`
   - `status` (`active`, `archived`)
   - `primary_package_id` (nullable)
   - `created_at`, `updated_at`
   - `last_activity_at`

GSI suggestions:

1. `GSI1PK = TENANT#{tenant_id}`, `GSI1SK = PROJECT#{updated_at}#{project_id}`
2. `GSI2PK = USER#{tenant_id}#{owner_user_id}`, `GSI2SK = PROJECT#{updated_at}#{project_id}`

### CHAT-PROJECT LINK

Option A (recommended): augment existing session item:

1. Add `project_id` to `SESSION#...` item.
2. Add `active_package_id` and `chat_mode` (`project`, `standalone`).

Option B: separate link item for multi-project per session (not needed initially).

## 4.2 Existing Entity Extensions

1. `PACKAGE#` add optional `project_id`.
2. `DOCUMENT#` add optional `project_id`.
3. `SESSION#` add:
   - `project_id`
   - `active_package_id`
   - `chat_mode`

## 5. API Changes

## 5.1 Project APIs

1. `GET /api/projects`
   - query: `limit`, `cursor`, `q`, `status`
2. `POST /api/projects`
3. `GET /api/projects/{project_id}`
4. `PUT /api/projects/{project_id}`
5. `DELETE /api/projects/{project_id}` (soft delete/archive recommended)
6. `POST /api/projects/{project_id}/activate`

## 5.2 Project Chat APIs

1. `GET /api/projects/{project_id}/chats`
2. `POST /api/projects/{project_id}/chats`
   - creates session bound to project
3. `POST /api/chats/{session_id}/move-project`
   - move standalone chat into project

## 5.3 Project Package Link APIs

1. `POST /api/projects/{project_id}/attach-package`
2. `POST /api/projects/{project_id}/detach-package`
3. `GET /api/projects/{project_id}/packages` (optional)

## 5.4 Search APIs for Attach Flow

1. `GET /api/packages/search`
   - query: `q`, `status`, `owner`, `updated_after`, `limit`, `cursor`
2. Must return concise metadata for fast picker rendering.

## 6. Frontend Implementation Plan

## 6.1 Route Structure

Suggested Next.js routes:

1. `/projects` (project index)
2. `/projects/[projectId]` (project overview)
3. `/projects/[projectId]/chat/[sessionId]` (chat in project)
4. Keep `/chat` for standalone mode.

## 6.2 State Management

Extend session/context layer:

1. `activeProjectId`
2. `activeChatId`
3. `projectList`
4. `projectChatsById`
5. `projectPackageContext`

Rules:

1. Opening a project sets `activeProjectId`.
2. New chat from project binds session to that project.
3. Chat stream requests include project metadata in payload or headers.

## 6.3 Components

Add:

1. `ProjectSidebarSection`
2. `ProjectSwitcher`
3. `ProjectHeader`
4. `ProjectChatList`
5. `AttachPackageModal`
6. `ContextBadgeBar` (mode/package/project indicators)

Update:

1. `chat-history-dropdown` to support project grouping.
2. `simple-chat-interface` to show inherited project context.
3. `document/activity panels` to filter by active project.

## 6.4 UI Behavior Specifications

1. Project list supports search + keyboard navigation.
2. New chat in project opens immediately with project chip visible.
3. Attach package modal appears only when needed (not every doc generation).
4. If project has primary package, default attach silently unless user overrides.
5. Explicit "Generate one-off draft" bypasses package context for current turn.

## 7. Interaction with Canonical Backend Flow

This branch should consume canonical APIs but can be merged independently via flags:

1. `FEATURE_PROJECTS_UI`
2. `FEATURE_PROJECT_PACKAGE_LINKS`

When canonical backend is unavailable:

1. UI can still render project shells.
2. Package attach actions should show feature disabled or fallback messaging.

## 8. Migration and Backward Compatibility

## 8.1 Existing Sessions

1. Legacy sessions without `project_id` appear under "Standalone Chats".
2. Provide "Move to project" action from chat history.

## 8.2 Existing Local Cache

1. If localStorage session data exists, keep reading for continuity.
2. Add migration function that tags legacy sessions as standalone.
3. Avoid deleting local cached data during rollout.

## 9. Accessibility and Performance

1. Keyboard-first navigation for project/chat switching.
2. ARIA labels for sidebar, tabs, and modals.
3. Virtualized list rendering for large project/chat counts.
4. Cursor pagination for project and chat APIs.
5. Avoid loading all chats for all projects on initial page load.

## 10. Telemetry and Analytics

Track:

1. Project created, renamed, archived.
2. Chat created within project.
3. Package attached/detached.
4. Context switch events (project, chat, package).
5. Attach modal open/select/cancel funnel.

Quality metrics:

1. Time-to-first-response after project switch.
2. Attach selection latency.
3. Wrong-package correction rate.

## 11. Rollout Phases

1. Phase 1: Backend project entities + APIs behind flags.
2. Phase 2: Read-only project list and project shell UI.
3. Phase 3: Create project + create chat in project.
4. Phase 4: Attach package modal + project package context.
5. Phase 5: Full context badges and project-scoped docs/activity.
6. Phase 6: Promote projects as default workflow for package efforts.

## 12. Acceptance Criteria

1. User can create project and multiple chats under it.
2. User can attach project/chat to existing package via searchable picker.
3. Project context is visible and stable across chats.
4. Package-bound generation uses attached package by default.
5. Standalone chats still work without project overhead.
6. No major regressions in existing chat/session behavior.

## 13. Risks and Mitigations

1. Risk: UX complexity from too many context layers.
   Mitigation: persistent context bar + clear labels + conservative prompts.
2. Risk: performance degradation with many projects/chats.
   Mitigation: pagination, virtualization, indexed search APIs.
3. Risk: user confusion between standalone and project mode.
   Mitigation: explicit mode chip and one-click mode switch.

## 14. Suggested Ticket Breakdown

1. Define `PROJECT#` schema + CRUD store layer.
2. Add project APIs and tenant/user scoped queries.
3. Extend session schema with `project_id` and `active_package_id`.
4. Build sidebar project section and project switcher.
5. Build project detail page and project chat list.
6. Wire chat creation inside project.
7. Build package attach modal with search/filter/pagination.
8. Add context badges to chat UI.
9. Add "move standalone chat to project" UX.
10. Add E2E tests for core project workflows.
11. Add telemetry instrumentation and dashboards.

## 15. UX Notes for ChatGPT Feel

1. Keep interaction density low in left nav; avoid noisy metadata in list rows.
2. Show project name prominently in chat header.
3. Provide one clear CTA: `New chat in <Project>`.
4. Use tabs (`Chats`, `Sources`, optionally `Documents`) in project page.
5. Keep project shell lightweight: empty states and quick actions.
6. Do not force package attach at project creation; allow progressive setup.

