# Fix Document Viewer: Load Failure, Same-Tab Nav, Card Persistence

## Context

Three bugs prevent the document viewer from working end-to-end:

1. **Document can't load** — sessionStorage key mismatch between what `document-card.tsx` stores (`%2E` encoded dots) and what `documents/[id]/page.tsx` looks up (decoded dots). Template fallback also too narrow (only matches `-template.md` suffix, not S3 filenames like `sow_20260212_145613.md`).

2. **Opens in same tab** — `router.push()` replaces the chat tab instead of opening a new one.

3. **Cards vanish on back-nav** — `documents` state is ephemeral React state. `saveSession(messages, {})` only persists messages, not the document-to-message mapping. On session reload, `documents` resets to `{}`.

## Files to Modify

| File | Bugs |
|------|------|
| `client/components/chat-simple/document-card.tsx` | 1, 2 |
| `client/app/documents/[id]/page.tsx` | 1 |
| `client/hooks/use-session-persistence.ts` | 3 |
| `client/contexts/session-context.tsx` | 3 |
| `client/components/chat-simple/simple-chat-interface.tsx` | 3 |

## Implementation

### Bug 2: Open document in new tab (document-card.tsx)

- Remove `import { useRouter } from 'next/navigation'` and `const router = useRouter()`
- Change `handleOpen` from `router.push(url)` to `window.open(url, '_blank')`
- sessionStorage is shared within the same origin, so the new tab can read it

### Bug 1a: Fix sessionStorage key mismatch (document-card.tsx)

- In `getDocId()`, remove the `.replace(/\./g, '%2E')` — just use `encodeURIComponent(raw)`
- Dots in Next.js dynamic `[id]` segments are safe; the original encoding caused the mismatch

### Bug 1b: Fix sessionStorage lookup + template fallback (documents/[id]/page.tsx)

- Add a double-lookup in sessionStorage for backward compat with old `%2E` keys:
  ```
  sessionStorage.getItem(`doc-content-${id}`)
    || sessionStorage.getItem(`doc-content-${encodeURIComponent(id).replace(/\./g, '%2E')}`)
  ```

- Replace the narrow `-template.md` suffix check with prefix-based template mapping:
  ```typescript
  const TEMPLATE_MAP: Record<string, string> = {
      sow: 'sow-template.md',
      igce: 'igce-template.md',
      market_research: 'market-research-template.md',
      acquisition_plan: 'acquisition-plan-template.md',
      justification: 'justification-template.md',
  };
  // Match algorithm: iterate TEMPLATE_MAP keys sorted by length descending,
  // check decodedId.startsWith(key + '_') || decodedId === key.
  // Longest-first ensures 'acquisition_plan' matches before a hypothetical
  // shorter prefix like 'acquisition'.
  ```
  This way `sow_20260212_145613.md` matches prefix `sow` and loads `sow-template.md` as fallback content.
  And `acquisition_plan_20260212.md` correctly matches `acquisition_plan`, not a shorter prefix.

### Bug 3: Persist documents across navigation

**use-session-persistence.ts:**
- Add `import { DocumentInfo } from '@/types/chat'`
- Add optional `documents?: Record<string, DocumentInfo[]>` to `SessionData`
- Extend `saveSession` signature: add third param `documents?: Record<string, DocumentInfo[]>`
- Include `documents` in the serialized `sessionData` object
- `loadSession` already returns full `SessionData` — no change needed

**session-context.tsx:**
- Add `import { DocumentInfo } from '@/types/chat'`
- Update `saveSession` type in `SessionContextValue` to include optional `documents` param
- Add `documents?: Record<string, DocumentInfo[]>` to `loadSession` return type

**simple-chat-interface.tsx:**
- In session load effect: restore `setDocuments(sessionData.documents || {})`
- In `saveSessionDebounced`: pass `documents` as third arg — `saveSession(messages, {}, documents)`
- Add `documents` to `saveSessionDebounced` dependency array

**localStorage bloat prevention:** When serializing documents for session persistence,
strip the `content` field from each `DocumentInfo`. Card rendering only needs metadata
(`title`, `document_type`, `word_count`, `document_id`, `s3_key`). The full content is
already stored separately in sessionStorage (`doc-content-${docId}`) for the viewer page.

**Backward compat:** The `documents` field is optional. Old sessions without it default to `{}`. The advanced chat's `saveSession(messages, acquisitionData)` call (2 args) still works since the third param is optional.

## Verification

1. `npx tsc --noEmit` — zero TypeScript errors
2. Generate a document in chat (e.g., "Generate a SOW for IT services at NCI")
3. Verify document card appears below the assistant message
4. Click "Open Document" — should open in a **new tab**
5. New tab should show document content (from sessionStorage or template fallback), not "Unable to load"
6. Go back to the chat tab — document card should **still be visible**
7. Switch to a different session and back — document card should **persist**
8. Test with a fresh browser (no prior sessionStorage) — template fallback should load the correct template
