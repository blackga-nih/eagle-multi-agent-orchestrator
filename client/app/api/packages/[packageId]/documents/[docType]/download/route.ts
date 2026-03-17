/**
 * Package Document Download Route (proxy to FastAPI)
 *
 * GET /api/packages/[packageId]/documents/[docType]/download?format=docx&version=N
 *   - Returns rendered DOCX or PDF binary with Content-Disposition: attachment
 *   - format: "docx" (default) | "pdf"
 *   - version: optional version number (defaults to latest)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

interface RouteParams {
  params: Promise<{ packageId: string; docType: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { packageId, docType } = await params;
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/packages/${packageId}/documents/${docType}/download${queryString ? `?${queryString}` : ''}`;

    const headers: HeadersInit = {};
    const authorization = request.headers.get('Authorization');
    if (authorization) headers['Authorization'] = authorization;

    const response = await fetch(url, { method: 'GET', headers });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Download failed' }));
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
    console.error('Package document download error:', error);
    return NextResponse.json({ error: 'Download failed' }, { status: 502 });
  }
}
