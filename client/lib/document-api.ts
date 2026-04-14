/**
 * Document API Client
 *
 * Functions for uploading documents and assigning them to packages.
 */

export interface ClassificationResult {
  doc_type: string;
  confidence: number;
  method: 'filename' | 'content' | 'unknown';
  suggested_title: string | null;
}

export interface PackageContext {
  mode: 'package' | 'workspace';
  package_id: string | null;
}

export interface UploadResult {
  document_id?: string;
  key: string;
  upload_id: string;
  filename: string;
  size_bytes: number;
  content_type: string;
  classification: ClassificationResult;
  package_id?: string | null;
  package_context?: PackageContext;
}

export interface ComplianceReadiness {
  score: number;
  missing_documents: string[];
  draft_documents: string[];
  finalized_count?: number;
  total_required?: number;
  last_computed?: string;
}

export interface PackageInfo {
  package_id: string;
  title: string;
  status?: string;
  requirement_type?: string;
  estimated_value?: string;
  created_at?: string;
  system_tags?: string[];
  user_tags?: string[];
  far_tags?: string[];
  compliance_readiness?: ComplianceReadiness;
  threshold_tier?: string;
  approval_level?: string;
}

export interface AssignResult {
  success: boolean;
  document_id?: string;
  package_id?: string;
  doc_type?: string;
  version?: number;
  status?: string;
  s3_key?: string;
  title?: string;
  error?: string;
}

export interface PackageAttachment {
  attachment_id: string;
  package_id: string;
  attachment_type: 'document' | 'image' | 'screenshot';
  doc_type?: string | null;
  linked_doc_type?: string | null;
  category: string;
  usage: 'reference' | 'checklist_support' | 'official_candidate' | 'official_document';
  include_in_zip: boolean;
  title: string;
  display_name?: string;
  filename: string;
  original_filename: string;
  file_type: string;
  content_type: string;
  size_bytes: number;
  s3_key: string;
  classification?: ClassificationResult;
  classification_confidence?: number;
  classification_source?: string;
  extracted_text?: string;
  extracted_text_available?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface UploadPackageAttachmentOptions {
  title?: string;
  docType?: string;
  linkedDocType?: string;
  category?: string;
  usage?: 'reference' | 'checklist_support' | 'official_candidate' | 'official_document';
  includeInZip?: boolean;
  sessionId?: string;
}

/**
 * Upload a document to the user's S3 workspace.
 */
export async function uploadDocument(
  file: File,
  sessionId?: string,
  packageId?: string,
  token?: string | null,
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);

  const params = new URLSearchParams();
  if (sessionId) params.append('session_id', sessionId);
  if (packageId) params.append('package_id', packageId);

  const url = `/api/documents/upload${params.toString() ? `?${params}` : ''}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const rawBody = await response.text().catch(() => '');
    let error: {
      detail?: string;
      details?: string;
      error?: string;
      message?: string;
    } = {};

    if (rawBody) {
      try {
        error = JSON.parse(rawBody) as {
          detail?: string;
          details?: string;
          error?: string;
          message?: string;
        };
      } catch {
        error = { detail: rawBody.trim() || 'Upload failed' };
      }
    } else {
      error = { detail: 'Upload failed' };
    }

    throw new Error(
      error.detail ||
        error.details ||
        error.error ||
        error.message ||
        `Upload failed: ${response.status}`,
    );
  }

  return response.json();
}

export async function uploadPackageAttachment(
  packageId: string,
  file: File,
  options: UploadPackageAttachmentOptions = {},
  token?: string | null,
): Promise<PackageAttachment> {
  const formData = new FormData();
  formData.append('file', file);
  if (options.title) formData.append('title', options.title);
  if (options.docType) formData.append('doc_type', options.docType);
  if (options.linkedDocType) formData.append('linked_doc_type', options.linkedDocType);
  if (options.category) formData.append('category', options.category);
  if (options.usage) formData.append('usage', options.usage);
  if (typeof options.includeInZip === 'boolean') {
    formData.append('include_in_zip', String(options.includeInZip));
  }
  if (options.sessionId) formData.append('session_id', options.sessionId);

  const response = await fetch(`/api/packages/${encodeURIComponent(packageId)}/attachments`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    const rawBody = await response.text().catch(() => '');
    let error: {
      detail?: string;
      details?: string;
      error?: string;
      message?: string;
    } = {};

    if (rawBody) {
      try {
        error = JSON.parse(rawBody) as {
          detail?: string;
          details?: string;
          error?: string;
          message?: string;
        };
      } catch {
        error = { detail: rawBody.trim() || 'Attachment upload failed' };
      }
    } else {
      error = { detail: 'Attachment upload failed' };
    }

    throw new Error(
      error.detail ||
        error.details ||
        error.error ||
        error.message ||
        `Attachment upload failed: ${response.status}`,
    );
  }

  return response.json();
}

export async function listPackageAttachments(
  packageId: string,
  token?: string | null,
): Promise<PackageAttachment[]> {
  const response = await fetch(`/api/packages/${encodeURIComponent(packageId)}/attachments`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch package attachments: ${response.status}`);
  }

  const data = (await response.json()) as { attachments?: PackageAttachment[] };
  return data.attachments || [];
}

export async function updatePackageAttachment(
  packageId: string,
  attachmentId: string,
  updates: Partial<
    Pick<
      PackageAttachment,
      'title' | 'doc_type' | 'linked_doc_type' | 'category' | 'usage' | 'include_in_zip'
    >
  >,
  token?: string | null,
): Promise<PackageAttachment> {
  const response = await fetch(
    `/api/packages/${encodeURIComponent(packageId)}/attachments/${encodeURIComponent(attachmentId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(updates),
    },
  );

  if (!response.ok) {
    const error = (await response.json().catch(() => ({ detail: 'Attachment update failed' }))) as {
      detail?: string;
      details?: string;
      error?: string;
      message?: string;
    };
    throw new Error(
      error.detail ||
        error.details ||
        error.error ||
        error.message ||
        `Attachment update failed: ${response.status}`,
    );
  }

  return response.json();
}

export async function deletePackageAttachment(
  packageId: string,
  attachmentId: string,
  token?: string | null,
): Promise<void> {
  const response = await fetch(
    `/api/packages/${encodeURIComponent(packageId)}/attachments/${encodeURIComponent(attachmentId)}`,
    {
      method: 'DELETE',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    },
  );

  if (!response.ok) {
    const error = (await response.json().catch(() => ({ detail: 'Attachment delete failed' }))) as {
      detail?: string;
      details?: string;
      error?: string;
      message?: string;
    };
    throw new Error(
      error.detail ||
        error.details ||
        error.error ||
        error.message ||
        `Attachment delete failed: ${response.status}`,
    );
  }
}

export async function promotePackageAttachment(
  packageId: string,
  attachmentId: string,
  payload: {
    doc_type: string;
    title?: string;
    set_as_official?: boolean;
  },
  token?: string | null,
): Promise<PackageDocument> {
  const response = await fetch(
    `/api/packages/${encodeURIComponent(packageId)}/attachments/${encodeURIComponent(attachmentId)}/promote`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    },
  );

  if (!response.ok) {
    const error = (await response.json().catch(() => ({ detail: 'Attachment promotion failed' }))) as {
      detail?: string;
      details?: string;
      error?: string;
      message?: string;
    };
    throw new Error(
      error.detail ||
        error.details ||
        error.error ||
        error.message ||
        `Attachment promotion failed: ${response.status}`,
    );
  }

  return response.json();
}

/**
 * Assign an uploaded document to an acquisition package.
 */
export async function assignToPackage(
  uploadId: string,
  packageId: string,
  docType: string,
  title?: string,
  token?: string | null,
): Promise<AssignResult> {
  const response = await fetch(`/api/documents/${uploadId}/assign-to-package`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      package_id: packageId,
      doc_type: docType,
      title,
    }),
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => ({ detail: 'Assignment failed' }))) as {
      detail?: string;
      details?: string;
      error?: string;
      message?: string;
    };
    throw new Error(
      error.detail ||
        error.details ||
        error.error ||
        error.message ||
        `Assignment failed: ${response.status}`,
    );
  }

  return response.json();
}

/**
 * List all packages for the current user.
 */
export async function listPackages(token?: string | null): Promise<PackageInfo[]> {
  const response = await fetch('/api/packages', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch packages: ${response.status}`);
  }

  return response.json();
}

/**
 * Delete a package (only intake/drafting status allowed).
 */
export async function deletePackage(packageId: string, token?: string | null): Promise<void> {
  const response = await fetch(`/api/packages/${encodeURIComponent(packageId)}`, {
    method: 'DELETE',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => ({ detail: 'Delete failed' }))) as {
      detail?: string;
      error?: string;
    };
    throw new Error(error.detail || error.error || `Delete failed: ${response.status}`);
  }
}

// ── Package Document & Checklist API ─────────────────────────────

export interface PackageDocument {
  document_id: string;
  doc_type: string;
  title: string;
  version: number;
  status: string;
  file_type: string;
  content?: string;
  s3_key?: string;
  created_at?: string;
  word_count?: number;
}

export interface ChecklistItem {
  slug: string;
  label: string;
  status: 'pending' | 'completed';
  document_id?: string;
  version?: number;
  updated_at?: string;
  doc_status?: string;
}

export interface PackageChecklist {
  package_id?: string;
  required: string[];
  completed: string[];
  missing: string[];
  complete?: boolean;
  items?: ChecklistItem[];
  extra?: ChecklistItem[];
  pathway?: string | null;
  title?: string | null;
  custom?: boolean;
  warnings?: string[];
}

export interface DocTypeManifestEntry {
  slug: string;
  label: string;
}

/**
 * List all documents for a package (latest version per doc type).
 */
export async function getPackageDocuments(
  packageId: string,
  token?: string | null,
): Promise<PackageDocument[]> {
  const response = await fetch(`/api/packages/${encodeURIComponent(packageId)}/documents`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch package documents: ${response.status}`);
  }

  return response.json();
}

/**
 * Get the document checklist for a package.
 */
export async function getPackageChecklist(
  packageId: string,
  token?: string | null,
): Promise<PackageChecklist> {
  const response = await fetch(`/api/packages/${encodeURIComponent(packageId)}/checklist`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch package checklist: ${response.status}`);
  }

  return response.json();
}

/**
 * Mutate a package's required-doc list (Phase B' Option D).
 *
 * `add` and `remove` can be combined in one call. `reset: true` discards
 * the user's curated list and recomputes from the pathway baseline; it
 * takes priority over add/remove. Returns the freshly-derived rich
 * checklist so callers can mutate() without a refetch.
 */
export async function patchPackageRequiredDocs(
  packageId: string,
  body: { add?: string[]; remove?: string[]; reset?: boolean },
  token?: string | null,
): Promise<PackageChecklist> {
  const response = await fetch(
    `/api/packages/${encodeURIComponent(packageId)}/required-docs`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    },
  );

  if (!response.ok) {
    const err = (await response.json().catch(() => ({ detail: 'Patch failed' }))) as {
      detail?: string;
    };
    throw new Error(err.detail || `Patch failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Fetch the allowed doc-type manifest used by the "+ Add Required" picker.
 */
export async function getDocTypesManifest(
  token?: string | null,
): Promise<DocTypeManifestEntry[]> {
  const response = await fetch('/api/packages/doc-types', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch doc-types manifest: ${response.status}`);
  }

  const data = (await response.json()) as { doc_types?: DocTypeManifestEntry[] };
  return data.doc_types || [];
}

// ── Tag API ────────────────────────────────────────────────────────

export async function addDocumentTags(
  docId: string,
  tags: string[],
  token?: string | null,
): Promise<void> {
  await fetch(`/api/documents/${docId}/tags`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ tags }),
  });
}

export async function removeDocumentTags(
  docId: string,
  tags: string[],
  token?: string | null,
): Promise<void> {
  await fetch(`/api/documents/${docId}/tags`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ tags }),
  });
}

export async function addPackageTags(
  packageId: string,
  tags: string[],
  token?: string | null,
): Promise<void> {
  await fetch(`/api/packages/${packageId}/tags`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ tags }),
  });
}

export async function removePackageTags(
  packageId: string,
  tags: string[],
  token?: string | null,
): Promise<void> {
  await fetch(`/api/packages/${packageId}/tags`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ tags }),
  });
}

export interface TagSearchResult {
  entity_type: string;
  entity_id: string;
  tag_type: string;
  tag_value: string;
  created_at: string;
}

export async function searchByTag(
  tagValue: string,
  entityType?: string,
  token?: string | null,
): Promise<TagSearchResult[]> {
  const params = new URLSearchParams({ q: tagValue });
  if (entityType) params.append('type', entityType);

  const response = await fetch(`/api/tags/search?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) return [];
  const data = await response.json();
  return data.results || [];
}
