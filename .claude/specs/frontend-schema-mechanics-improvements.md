# Frontend Plan: Schema & Mechanics Improvements

## Overview

- Area: Types, Schema, Data Flow, Component Mechanics
- Type Files Audited: `schema.ts`, `chat.ts`, `stream.ts`, `admin.ts`, `conversation.ts`, `mcp.ts`, `index.ts`
- Components Audited: Chat, ActivityPanel, Feedback, Admin pages

---

## Idea 1: Prune Dead Types & Consolidate Type Barrel

**Problem**: `schema.ts` is a 596-line file where ~60% of the exported types are **never imported** anywhere. Types like `UserGroup`, `UserGroupMember`, `UserExpertise`, `WorkflowTemplate`, `DocumentVersion`, `AgentSkill`, `SystemPrompt`, `ConversationTurn`, `AuditLog`, `FileAttachment`, `DeploymentHistory`, and most request/response types (`CreateWorkflowRequest`, `UpdateWorkflowRequest`, `SubmitRequirementRequest`, etc.) have zero consumers. Meanwhile, the barrel `types/index.ts` only re-exports `schema.ts` and `stream.ts` — it misses `admin.ts`, `chat.ts`, `conversation.ts`, `mcp.ts`, `expertise.ts`.

**Changes**:

| File | Change |
|------|--------|
| `client/types/schema.ts` | Move unused interfaces into a `schema-archive.ts` file (or delete outright). Keep only types with real consumers: `FeedbackType`, `AIFeedback`, `DocumentType`, `DocumentStatus`, `WorkflowStatus`, `AcquisitionType`, `UrgencyLevel`, `User`, `UserRole`, `Workflow`, `Document`, `RequirementSubmission`, `ReviewStatus`, `SubmissionSource`, color constants, `AcquisitionFormData` |
| `client/types/index.ts` | Re-export `admin.ts`, `chat.ts`, `conversation.ts` so consumers can import from `@/types` instead of deep paths |

**Impact**: Smaller schema.ts (~150 lines vs 596), clearer barrel, no dead code confusing new contributors.

---

## Idea 2: Unify the Duplicate `AcquisitionData` / `AcquisitionFormData` Types

**Problem**: Two nearly-identical interfaces exist:
- `AcquisitionFormData` in `schema.ts` (snake_case keys: `estimated_value`, `equipment_type`)
- `AcquisitionData` in `chat-interface.tsx` (camelCase keys: `estimatedValue`, `equipmentType`)

Both describe the same intake form shape. The chat component defines its own and re-exports it, so imports get the camelCase version. `schema.ts` has the snake_case version plus a `acquisitionFormToWorkflow()` converter, but this converter is also never called.

**Changes**:

| File | Change |
|------|--------|
| `client/types/schema.ts` | Rename `AcquisitionFormData` → `AcquisitionData`, switch to camelCase keys to match actual usage, delete the unused `acquisitionFormToWorkflow()` function |
| `client/components/chat/chat-interface.tsx` | Remove the local `AcquisitionData` definition, import from `@/types/schema` |
| Any file importing `AcquisitionData` from chat-interface | Redirect import to `@/types/schema` |

**Impact**: Single source of truth for the intake form shape. Eliminates silent drift between two definitions.

---

## Idea 3: Add a `DocumentType` Exhaustive Map to Replace Scattered Hardcoded Lists

**Problem**: Document type lists are hardcoded in multiple places:
- `activity-panel.tsx` has a `DOC_TYPE_ICONS` map with 10 types
- `document-checklist.tsx` has its own document type list
- `schema.ts` `DocumentType` union has only 6 types: `sow | igce | market_research | acquisition_plan | justification | funding_doc`
- The backend `create_document` tool supports 10 types (including `eval_criteria`, `security_checklist`, `section_508`, `cor_certification`, `contract_type_justification`)

The schema type is incomplete and components silently handle extras via fallback.

**Changes**:

| File | Change |
|------|--------|
| `client/types/schema.ts` | Expand `DocumentType` union to all 10 types the backend supports |
| `client/types/schema.ts` | Add a `DOCUMENT_TYPE_LABELS: Record<DocumentType, string>` map (human names) |
| `client/types/schema.ts` | Add a `DOCUMENT_TYPE_ICONS: Record<DocumentType, string>` map (lucide icon names) |
| `client/components/chat-simple/activity-panel.tsx` | Import `DOCUMENT_TYPE_LABELS` and `DOCUMENT_TYPE_ICONS` instead of hardcoding `DOC_TYPE_ICONS` locally |
| `client/components/checklist/document-checklist.tsx` | Import from shared map |

**Impact**: Backend adds a new doc type → one place to update in the frontend. TypeScript catches any missing entries at compile time.

---

## Idea 4: Type-Safe Feedback API with Zod Runtime Validation

**Problem**: The new feedback modal submits `{ rating, page, feedback_type, comment, session_id }` as raw JSON. The Next.js API route just forwards it without validation. The backend Pydantic model catches invalid data, but the error surfaces as a generic 422 — no client-side feedback until the server rejects it. Same pattern exists for other API routes (`/api/invoke`, session routes).

**Changes**:

| File | Change |
|------|--------|
| `client/lib/api-schemas.ts` (new) | Define Zod schemas for API request/response shapes: `FeedbackSubmitSchema`, `SessionCreateSchema`, etc. |
| `client/app/api/feedback/route.ts` | Parse body through `FeedbackSubmitSchema.safeParse()` before forwarding — return 400 with field-level errors on failure |
| `client/components/feedback/feedback-modal.tsx` | Validate locally before POST — show inline field errors (e.g. "Rating required") instead of waiting for server round-trip |
| `package.json` | Add `zod` dependency (lightweight, zero-dep, ~13KB gzipped) |

**Impact**: Instant client-side validation, typed API contracts, better error messages. Pattern reusable for all API routes.

---

## Idea 5: Extract Keyboard Shortcut Registry from Scattered `useEffect` Listeners

**Problem**: Keyboard shortcuts are registered via individual `useEffect` hooks scattered across components:
- `simple-chat-interface.tsx`: Ctrl+K (command palette)
- `feedback-modal.tsx`: Ctrl+J (feedback)
- `modal.tsx`: Escape (close)
- Various admin pages may add their own

Each registers/unregisters its own `keydown` listener independently. No central registry means: (a) no way to show "all shortcuts" to the user, (b) potential conflicts go undetected, (c) shortcuts don't respect focus context (e.g. Ctrl+J fires even when typing in a textarea with Ctrl held).

**Changes**:

| File | Change |
|------|--------|
| `client/hooks/use-keyboard-shortcut.ts` (new) | Centralized hook: `useKeyboardShortcut(combo, handler, options?)`. Options: `{ enabled, preventDefault, ignoreInputs }`. Maintains a module-level registry for conflict detection. |
| `client/components/feedback/feedback-modal.tsx` | Replace raw `useEffect` with `useKeyboardShortcut('ctrl+j', toggle)` |
| `client/components/chat-simple/command-palette.tsx` | Replace raw `useEffect` with `useKeyboardShortcut('ctrl+k', toggle)` |
| `client/components/ui/modal.tsx` | Replace raw `useEffect` with `useKeyboardShortcut('escape', onClose, { enabled: isOpen })` |
| `client/components/ui/keyboard-shortcuts-help.tsx` (new) | Optional: render all registered shortcuts in a help overlay (Ctrl+/) |

**Impact**: Single pattern for all shortcuts, conflict detection, input-aware suppression, discoverable shortcuts list.

---

## Verification

```bash
# After any of these changes:
cd client && npx tsc --noEmit          # Type check
cd client && npm run build             # Full build
cd client && npx playwright test       # E2E (if applicable)
```

## Priority Ranking

| # | Idea | Effort | Impact | Risk |
|---|------|--------|--------|------|
| 1 | Prune dead types + barrel | Low | Medium | Low |
| 3 | Exhaustive DocumentType map | Low | High | Low |
| 2 | Unify AcquisitionData | Medium | Medium | Low |
| 5 | Keyboard shortcut registry | Medium | Medium | Low |
| 4 | Zod runtime validation | Medium | High | Low (additive) |
