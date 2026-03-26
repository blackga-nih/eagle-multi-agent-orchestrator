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
    key: string;
    upload_id: string;
    filename: string;
    size_bytes: number;
    content_type: string;
    classification: ClassificationResult;
    package_context: PackageContext;
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
        const error = await response.json().catch(() => ({ detail: 'Upload failed' })) as {
            detail?: string;
            details?: string;
            error?: string;
            message?: string;
        };
        throw new Error(
            error.detail || error.details || error.error || error.message || `Upload failed: ${response.status}`
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
        const error = await response.json().catch(() => ({ detail: 'Assignment failed' })) as {
            detail?: string;
            details?: string;
            error?: string;
            message?: string;
        };
        throw new Error(
            error.detail || error.details || error.error || error.message || `Assignment failed: ${response.status}`
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

export interface PackageChecklist {
    package_id: string;
    required: string[];
    completed: string[];
    missing: string[];
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

// ── Tag API ────────────────────────────────────────────────────────

export async function addDocumentTags(docId: string, tags: string[], token?: string | null): Promise<void> {
    await fetch(`/api/documents/${docId}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ tags }),
    });
}

export async function removeDocumentTags(docId: string, tags: string[], token?: string | null): Promise<void> {
    await fetch(`/api/documents/${docId}/tags`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ tags }),
    });
}

export async function addPackageTags(packageId: string, tags: string[], token?: string | null): Promise<void> {
    await fetch(`/api/packages/${packageId}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ tags }),
    });
}

export async function removePackageTags(packageId: string, tags: string[], token?: string | null): Promise<void> {
    await fetch(`/api/packages/${packageId}/tags`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
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

export async function searchByTag(tagValue: string, entityType?: string, token?: string | null): Promise<TagSearchResult[]> {
    const params = new URLSearchParams({ q: tagValue });
    if (entityType) params.append('type', entityType);

    const response = await fetch(`/api/tags/search?${params}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) return [];
    const data = await response.json();
    return data.results || [];
}
