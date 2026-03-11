# Document Changelog Feature

**Date:** 2026-03-10
**Status:** Draft

---

## Problem

Documents in EAGLE lack detailed change tracking. Currently:
- Versions are tracked, but not *what* changed or *who* changed it
- No UI to see edit history
- AI may work with stale content if it retrieves an old version
- No way for agent to summarize recent document activity

---

## Requirements

1. Track every change per document (user + AI changes)
2. Show changelog in document pane UI
3. Ensure AI always gets the latest document version
4. Agent tool to query logs and provide summaries

---

## Why This Approach

| Decision | Rationale |
|----------|-----------|
| **CHANGELOG# DynamoDB entity** | EAGLE uses single-table design with entity prefixes (DOCUMENT#, AUDIT#, SESSION#). Adding CHANGELOG# requires zero schema changes. |
| **Follow `audit_store.py` pattern** | Proven write-only pattern already in codebase. Copy it, don't reinvent. |
| **Hook at `document_service.py`** | This is the canonical entry point for ALL document creation (AI + user). One hook catches everything vs. duplicating across endpoints. |
| **Add tab to ActivityPanel** | Panel already has 3 tabs. Adding a 4th is minimal UI change vs. new component. |
| **Fix existing read path** | Instead of a new "get latest" tool, fix `s3_document_ops` to auto-resolve latest version for package docs. Simpler. |
| **One new tool** | `document_changelog_search` for agent to query history. That's all that's needed. |

---

## Implementation

### Phase 1: Changelog Store (Backend)

**Create** `server/app/changelog_store.py`:

```
PK:  CHANGELOG#{tenant_id}
SK:  CHANGELOG#{package_id}#{doc_type}#{ISO_timestamp}
```

| Attribute | Purpose |
|-----------|---------|
| `changelog_id` | UUID |
| `package_id`, `doc_type`, `version` | Document reference |
| `change_type` | `create`, `update`, `finalize` |
| `change_source` | `agent_tool`, `user_edit` |
| `change_summary` | Human-readable description |
| `actor_user_id` | Who made the change |
| `session_id` | Optional chat session link |
| `created_at`, `ttl` | Timestamp + 7-year TTL |

Functions:
- `write_changelog_entry(...)` — write single entry
- `list_changelog_entries(tenant_id, package_id, doc_type, limit=50)` — newest first

---

### Phase 2: Hook Document Flows (Backend)

**Edit** `server/app/document_service.py` line ~225 (after `_update_package_checklist`):

```python
from .changelog_store import write_changelog_entry

write_changelog_entry(
    tenant_id=tenant_id,
    package_id=package_id,
    doc_type=doc_type,
    version=next_version,
    change_type="create",
    change_source=change_source,
    change_summary=f"Created {doc_type} v{next_version}: {title}",
    actor_user_id=created_by_user_id or "system",
    session_id=session_id,
)
```

Also hook `finalize_document()` (~line 286) for finalize events.

---

### Phase 3: API Endpoint (Backend)

**Add** to `server/app/main.py`:

```python
@app.get("/api/packages/{package_id}/documents/{doc_type}/changelog")
async def get_document_changelog(package_id, doc_type, limit=50, user=Depends(...)):
    return list_changelog_entries(user.tenant_id, package_id, doc_type, limit)
```

---

### Phase 4: Agent Tool + Latest Doc Fix (Backend)

**4a. Add tool** `document_changelog_search` to `server/app/agentic_service.py`:
- Input: `package_id` (required), `doc_type` (optional), `limit` (default 20)
- Output: List of changelog entries with summaries
- Register in `TOOL_DISPATCH` and `_SERVICE_TOOL_DEFS`

**4b. Fix existing read path** in `_exec_s3_document_ops` (line ~753):
- When reading a package document, auto-resolve to latest version via `get_document(tenant_id, package_id, doc_type)` (no version = latest)
- Include `version` and `is_latest: true` in response

This ensures AI always works with current content without needing a separate tool.

---

### Phase 5: Changelog Tab (Frontend)

**Edit** `client/components/chat-simple/activity-panel.tsx` line 31:

```typescript
import { History } from 'lucide-react';

const TABS: TabDef[] = [
  { id: 'documents',     label: 'Documents',     icon: FileText },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'logs',          label: 'Agent Logs',    icon: Terminal },
  { id: 'changelog',     label: 'Changelog',     icon: History },
];
```

Add `ChangelogTab` component:
- Fetch from `/api/packages/{packageId}/documents/{docType}/changelog`
- Show: timestamp, actor icon (robot/user), doc type, version, summary

---

## Files to Modify

| File | Change |
|------|--------|
| `server/app/changelog_store.py` | **New** — DynamoDB CRUD |
| `server/app/document_service.py:225` | Hook changelog write |
| `server/app/main.py` | Add changelog endpoint |
| `server/app/agentic_service.py` | Add 1 tool + fix read path |
| `client/components/chat-simple/activity-panel.tsx` | Add Changelog tab |

---

## Verification

```bash
# Level 1 — Lint
ruff check app/
npx tsc --noEmit

# Level 2 — Unit tests
python -m pytest tests/test_changelog_store.py -v

# Level 3 — E2E
npx playwright test tests/changelog.spec.ts
```

| Test | Validates |
|------|-----------|
| Create doc via API, check changelog entry | Phase 1-2 |
| AI creates doc, changelog shows "agent_tool" | Phase 2 |
| Call `document_changelog_search` tool | Phase 4a |
| Read package doc, verify `is_latest: true` | Phase 4b |
| Open ActivityPanel, see Changelog tab | Phase 5 |
