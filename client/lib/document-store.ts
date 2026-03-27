/**
 * Document Store — localStorage persistence for generated documents & acquisition packages.
 *
 * Keys:
 *   eagle_packages        → Record<sessionId, PackageData>
 *   eagle_generated_docs  → Record<docId, StoredDocument>
 */

import { DocumentInfo } from '@/types/chat';
import { DocumentType, DocumentStatus, WorkflowStatus, DOCUMENT_TYPE_LABELS } from '@/types/schema';

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
  created_at: string;
  updated_at: string;
}

export interface PackageChecklist {
  document_type: DocumentType;
  label: string;
  status: 'pending' | 'completed';
  document_id?: string;
}

export interface PackageData {
  id: string;
  package_id?: string;
  title: string;
  status: WorkflowStatus;
  created_at: string;
  updated_at: string;
  documents: string[];
  checklist: PackageChecklist[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PACKAGES_KEY = 'eagle_packages';
const DOCS_KEY = 'eagle_generated_docs';

/** Slug-to-DocumentType mapping for backend required_documents slugs. */
const SLUG_TO_DOC_TYPE: Record<string, DocumentType> = {
  sow: 'sow',
  igce: 'igce',
  'market-research': 'market_research',
  'acquisition-plan': 'acquisition_plan',
  justification: 'justification',
  'd-f': 'd_f',
  qasp: 'qasp',
  'source-selection-plan': 'source_selection_plan',
  'subcontracting-plan': 'subcontracting_plan',
  'sb-review': 'sb_review',
  'purchase-request': 'purchase_request',
  'security-checklist': 'security_checklist',
  'section-508': 'section_508',
  'human-subjects': 'human_subjects',
  'funding-doc': 'funding_doc',
};

/** Build a checklist from backend required_documents slugs. */
function buildChecklist(requiredDocs: string[]): PackageChecklist[] {
  return requiredDocs.map((slug) => {
    const docType = SLUG_TO_DOC_TYPE[slug] || (slug.replace(/-/g, '_') as DocumentType);
    const label =
      DOCUMENT_TYPE_LABELS[docType] ||
      slug.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    return { document_type: docType, label, status: 'pending' as const };
  });
}

const DEFAULT_CHECKLIST: PackageChecklist[] = [
  { document_type: 'purchase_request', label: 'Purchase Request', status: 'pending' },
  { document_type: 'sow', label: 'Statement of Work', status: 'pending' },
  { document_type: 'igce', label: 'Cost Estimate (IGCE)', status: 'pending' },
  { document_type: 'market_research', label: 'Market Research', status: 'pending' },
  { document_type: 'acquisition_plan', label: 'Acquisition Plan', status: 'pending' },
  { document_type: 'justification', label: 'Justification & Approval (J&A)', status: 'pending' },
  { document_type: 'source_selection_plan', label: 'Source Selection Plan', status: 'pending' },
  { document_type: 'qasp', label: 'Quality Assurance Surveillance Plan (QASP)', status: 'pending' },
  { document_type: 'funding_doc', label: 'Funding Document', status: 'pending' },
  { document_type: 'sb_review', label: 'Small Business Review (HHS-653)', status: 'pending' },
];

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
 * Persist a generated document and upsert its acquisition package.
 */
export function saveGeneratedDocument(
  doc: DocumentInfo,
  sessionId: string,
  sessionTitle: string,
  requiredDocuments?: string[],
): void {
  const docId = getDocId(doc);
  const packageKey = doc.package_id || sessionId;
  const now = new Date().toISOString();

  // --- Save document ---
  const docs = readMap<StoredDocument>(DOCS_KEY);
  const existing = docs[docId];

  const stored: StoredDocument = {
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
    created_at: existing?.created_at || now,
    updated_at: now,
  };
  docs[docId] = stored;
  writeMap(DOCS_KEY, docs);

  // --- Upsert package ---
  const packages = readMap<PackageData>(PACKAGES_KEY);
  let pkg = packages[packageKey];

  if (!pkg) {
    const checklist =
      requiredDocuments && requiredDocuments.length > 0
        ? buildChecklist(requiredDocuments)
        : DEFAULT_CHECKLIST.map((c) => ({ ...c }));
    pkg = {
      id: packageKey,
      package_id: doc.package_id,
      title: sessionTitle || 'Untitled Package',
      status: 'in_progress',
      created_at: now,
      updated_at: now,
      documents: [],
      checklist,
    };
  }

  // Link document to package
  if (!pkg.documents.includes(docId)) {
    pkg.documents.push(docId);
  }

  // Update checklist item
  const checkItem = pkg.checklist.find((c) => c.document_type === doc.document_type);
  if (checkItem) {
    checkItem.status = 'completed';
    checkItem.document_id = docId;
  }

  pkg.updated_at = now;
  packages[packageKey] = pkg;
  writeMap(PACKAGES_KEY, packages);
}

// ---------------------------------------------------------------------------
// Readers
// ---------------------------------------------------------------------------

export function getPackages(): PackageData[] {
  const map = readMap<PackageData>(PACKAGES_KEY);
  return Object.values(map).sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

export function getPackage(id: string): PackageData | null {
  const map = readMap<PackageData>(PACKAGES_KEY);
  return map[id] ?? null;
}

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
