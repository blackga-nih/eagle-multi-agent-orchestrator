/**
 * Individual Document API Route
 *
 * GET /api/documents/[id]?user_id=xxx&version=1
 *   - Get document metadata and content
 *
 * PUT /api/documents/[id]
 *   - Update document content (creates new version)
 *
 * DELETE /api/documents/[id]?user_id=xxx
 *   - Delete document and all versions
 */

import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.AGENTCORE_URL || 'http://localhost:8081';

interface RouteParams {
  params: Promise<{ id: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get('user_id') || 'default-user';
  const version = searchParams.get('version');
  const includeContent = searchParams.get('content') !== 'false';
  const includeVersions = searchParams.get('versions') === 'true';

  try {
    const queryParams = new URLSearchParams({ user_id: userId });
    if (version) queryParams.set('version', version);
    if (includeContent) queryParams.set('content', 'true');
    if (includeVersions) queryParams.set('versions', 'true');

    const response = await fetch(`${BACKEND_URL}/documents/${id}?${queryParams}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    if (response.ok) {
      const data = await response.json();
      return NextResponse.json(data);
    }
  } catch {
    // Backend unavailable
  }

  // Mock response for development
  const mockDoc = getMockDocument(id, userId);
  if (!mockDoc) {
    return NextResponse.json(
      { error: 'Document not found' },
      { status: 404 }
    );
  }

  const response: Record<string, unknown> = { ...mockDoc };

  if (includeContent) {
    response.content = getMockContent(mockDoc.document_type);
  }

  if (includeVersions) {
    response.versions = getMockVersions(id);
  }

  return NextResponse.json(response);
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;

  try {
    const body = await request.json();

    // Validate
    if (!body.user_id) {
      return NextResponse.json(
        { error: 'Missing required field: user_id' },
        { status: 400 }
      );
    }

    try {
      const response = await fetch(`${BACKEND_URL}/documents/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        const data = await response.json();
        return NextResponse.json(data);
      }
    } catch {
      // Backend unavailable
    }

    // Mock response - simulate version increment
    const mockDoc = getMockDocument(id, body.user_id);
    if (!mockDoc) {
      return NextResponse.json(
        { error: 'Document not found' },
        { status: 404 }
      );
    }

    return NextResponse.json({
      ...mockDoc,
      current_version: mockDoc.current_version + 1,
      updated_at: new Date().toISOString(),
      ...(body.title && { title: body.title }),
      ...(body.status && { status: body.status }),
      ...(body.description && { description: body.description }),
    });

  } catch (error) {
    console.error('Update document error:', error);
    return NextResponse.json(
      { error: 'Failed to update document' },
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get('user_id') || 'default-user';

  try {
    const response = await fetch(`${BACKEND_URL}/documents/${id}?user_id=${userId}`, {
      method: 'DELETE',
    });

    if (response.ok) {
      return NextResponse.json({ success: true, document_id: id });
    }
  } catch {
    // Backend unavailable
  }

  // Mock success response
  return NextResponse.json({
    success: true,
    document_id: id,
    message: 'Document deleted (mock)',
  });
}

/**
 * Mock document data for development
 */
function getMockDocument(documentId: string, userId: string) {
  const docs: Record<string, {
    document_id: string;
    user_id: string;
    document_type: string;
    title: string;
    description: string;
    current_version: number;
    status: string;
    tags: string[];
    created_at: string;
    updated_at: string;
  }> = {
    'doc-001': {
      document_id: 'doc-001',
      user_id: userId,
      document_type: 'sow',
      title: 'IT Consulting Services SOW',
      description: 'Statement of Work for IT consulting engagement',
      current_version: 2,
      status: 'draft',
      tags: ['IT', 'services'],
      created_at: '2026-01-28T10:00:00Z',
      updated_at: '2026-01-29T14:30:00Z',
    },
    'doc-002': {
      document_id: 'doc-002',
      user_id: userId,
      document_type: 'igce',
      title: 'CT Scanner IGCE',
      description: 'Independent Government Cost Estimate for medical imaging equipment',
      current_version: 1,
      status: 'in_review',
      tags: ['medical', 'equipment'],
      created_at: '2026-01-27T09:00:00Z',
      updated_at: '2026-01-27T09:00:00Z',
    },
    'doc-003': {
      document_id: 'doc-003',
      user_id: userId,
      document_type: 'justification',
      title: 'Sole Source Justification - Lab Equipment',
      description: 'J&A for specialized research equipment',
      current_version: 3,
      status: 'final',
      tags: ['research', 'sole-source'],
      created_at: '2026-01-20T11:00:00Z',
      updated_at: '2026-01-25T16:45:00Z',
    },
  };

  return docs[documentId] || null;
}

function getMockContent(documentType: string): string {
  const contents: Record<string, string> = {
    sow: `# Statement of Work

## 1. Background
The National Cancer Institute requires IT consulting services to support ongoing research initiatives.

## 2. Scope of Work
The contractor shall provide the following services:
- Technical architecture review and recommendations
- Cloud infrastructure optimization
- Security assessment and remediation

## 3. Period of Performance
Base period: 12 months
Option periods: Two 12-month options

## 4. Deliverables
- Monthly status reports
- Technical documentation
- Final recommendations report
`,
    igce: `# Independent Government Cost Estimate (IGCE)

## Equipment: CT Scanner

### Base Unit Cost
| Item | Quantity | Unit Price | Total |
|------|----------|------------|-------|
| CT Scanner (64-slice) | 1 | $450,000 | $450,000 |
| Installation | 1 | $25,000 | $25,000 |
| Training | 1 | $15,000 | $15,000 |

### Annual Maintenance
- Year 1: $35,000
- Year 2: $37,000
- Year 3: $39,000

### Total Estimated Cost: $601,000
`,
    justification: `# Justification and Approval (J&A)
## Sole Source Justification

### 1. Contracting Activity
National Cancer Institute, Office of Acquisitions

### 2. Description of Action
Procurement of specialized laboratory equipment for cancer research.

### 3. Statutory Authority
FAR 6.302-1: Only one responsible source

### 4. Rationale
The required equipment has proprietary specifications that can only be met by a single manufacturer...
`,
  };

  return contents[documentType] || '# Document\n\nContent not available.';
}

function getMockVersions(documentId: string) {
  return [
    {
      version: 2,
      s3_key: `users/default/documents/${documentId}/versions/v2.md`,
      change_summary: 'Updated scope section',
      changed_by: 'user-001',
      change_source: 'user_edit',
      created_at: '2026-01-29T14:30:00Z',
      size_bytes: 2048,
    },
    {
      version: 1,
      s3_key: `users/default/documents/${documentId}/versions/v1.md`,
      change_summary: 'Initial version',
      changed_by: 'user-001',
      change_source: 'user_edit',
      created_at: '2026-01-28T10:00:00Z',
      size_bytes: 1536,
    },
  ];
}
