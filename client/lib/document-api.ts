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

export interface PackageInfo {
    package_id: string;
    title: string;
    status?: string;
    requirement_type?: string;
    estimated_value?: string;
    created_at?: string;
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
        const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(error.detail || `Upload failed: ${response.status}`);
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
        const error = await response.json().catch(() => ({ detail: 'Assignment failed' }));
        throw new Error(error.detail || `Assignment failed: ${response.status}`);
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
