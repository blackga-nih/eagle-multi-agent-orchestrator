/**
 * Workspace Document Export Route (proxy to FastAPI)
 *
 * POST /api/documents/export?format=docx|pdf
 *   Body: { content: string, title: string, doc_type: string }
 *   Returns: rendered DOCX or PDF with Content-Disposition: attachment
 *   No package_id required — works for workspace-mode documents.
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/documents/export${queryString ? `?${queryString}` : ''}`;

    const body = await request.text();
    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    const authorization = request.headers.get('Authorization');
    if (authorization) headers['Authorization'] = authorization;

    const response = await fetch(url, { method: 'POST', headers, body });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Export failed' }));
      return NextResponse.json(err, { status: response.status });
    }

    const blob = await response.arrayBuffer();
    const contentType = response.headers.get('content-type') ?? 'application/octet-stream';
    const disposition = response.headers.get('content-disposition') ?? 'attachment';

    return new NextResponse(blob, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': disposition,
      },
    });
  } catch (error) {
    console.error('Document export error:', error);
    return NextResponse.json({ error: 'Export failed' }, { status: 502 });
  }
}
