/**
 * Document Store — optimistic localStorage cache for generated documents.
 *
 * Demoted (Phase C of the unify-document-tracking plan): no longer holds
 * any checklist or completion state. The DOCUMENT# DynamoDB table is the
 * single source of truth; the `usePackageChecklist` hook reads from SSE
 * pushes and `GET /api/packages/{id}/checklist`.
 *
 * What lives here now:
 *   eagle_generated_docs  → Record<docId, StoredDocument>
 *     ↳ Used solely so the new-tab `/documents/[id]` viewer page can paint
 *       on first frame without a backend round-trip. Cache-only — never
 *       authoritative.
 *
 * The `eagle_packages` key was retired with the checklist mutation block.
 */

import { DocumentInfo } from '@/types/chat';
import { DocumentType, DocumentStatus } from '@/types/schema';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StoredDocument {
  id: string;
  document_id?: string;
  package_id?: string;
  title: string;
  document_type: DocumentType;
  content?: string;
  file_type?: string;
  content_type?: string;
  is_binary?: boolean;
  download_url?: string | null;
  mode?: 'package' | 'workspace';
  status: DocumentStatus;
  version: number;
  word_count?: number;
  s3_key?: string;
  preview_mode?: DocumentInfo['preview_mode'];
  preview_blocks?: DocumentInfo['preview_blocks'];
  preview_sheets?: DocumentInfo['preview_sheets'];
  session_id: string;
  origin_context_available?: boolean;
  document_capabilities?: DocumentInfo['document_capabilities'];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DOCS_KEY = 'eagle_generated_docs';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function readMap<T>(key: string): Record<string, T> {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeMap<T>(key: string, map: Record<string, T>): void {
  try {
    localStorage.setItem(key, JSON.stringify(map));
  } catch {
    // localStorage full or unavailable
  }
}

function getDocId(doc: DocumentInfo): string {
  const raw = doc.s3_key || doc.document_id || doc.title;
  return encodeURIComponent(raw);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Persist a generated document to the optimistic viewer cache.
 *
 * Phase C of the unify-document-tracking plan: this no longer touches any
 * package or checklist state. The DOCUMENT# DynamoDB table — surfaced via
 * SSE checklist_update frames and `GET /api/packages/{id}/checklist` — is
 * the single source of truth for what's been generated. This function only
 * keeps doc bodies hot for the new-tab `/documents/[id]` viewer page so
 * the first paint doesn't need a backend round-trip.
 */
export function saveGeneratedDocument(doc: DocumentInfo, sessionId: string): void {
  const docId = getDocId(doc);
  const now = new Date().toISOString();

  const docs = readMap<StoredDocument>(DOCS_KEY);
  const existing = docs[docId];

  docs[docId] = {
    id: docId,
    document_id: doc.document_id,
    package_id: doc.package_id,
    title: doc.title,
    document_type: doc.document_type as DocumentType,
    content: doc.content,
    file_type: doc.file_type,
    content_type: doc.content_type,
    is_binary: doc.is_binary,
    download_url: doc.download_url ?? null,
    mode: doc.mode,
    status: (doc.status as DocumentStatus | undefined) || 'draft',
    version: doc.version ?? (existing ? existing.version + 1 : 1),
    word_count: doc.word_count,
    s3_key: doc.s3_key,
    preview_mode: doc.preview_mode,
    preview_blocks: doc.preview_blocks,
    preview_sheets: doc.preview_sheets,
    session_id: sessionId,
    origin_context_available: doc.origin_context_available,
    document_capabilities: doc.document_capabilities,
    created_at: existing?.created_at || now,
    updated_at: now,
  };
  writeMap(DOCS_KEY, docs);
}

// ---------------------------------------------------------------------------
// Readers
// ---------------------------------------------------------------------------

export function getGeneratedDocuments(): StoredDocument[] {
  const map = readMap<StoredDocument>(DOCS_KEY);
  return Object.values(map).sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

export function getGeneratedDocument(id: string): StoredDocument | null {
  const map = readMap<StoredDocument>(DOCS_KEY);
  if (map[id]) return map[id];

  const decoded = decodeURIComponent(id);
  const normalizedId = encodeURIComponent(decoded);
  if (map[normalizedId]) return map[normalizedId];

  const match = Object.values(map).find((doc) => {
    if (doc.id === id || doc.id === normalizedId) return true;
    return doc.s3_key === decoded || doc.title === decoded;
  });
  return match ?? null;
}
