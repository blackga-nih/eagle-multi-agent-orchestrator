/**
 * Knowledge Base Document Fetch API Route
 *
 * GET /api/knowledge-base/document/{s3Key}
 *   - Fetch full document content from S3 via the backend
 *   - Uses catch-all route since S3 keys contain slashes
 */

import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ s3Key: string[] }> },
) {
  try {
    const { s3Key } = await params;
    const s3KeyPath = s3Key.join('/');
    const authHeader = request.headers.get('authorization');
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(
      `${FASTAPI_URL}/api/knowledge-base/document/${encodeURI(s3KeyPath)}`,
      { method: 'GET', headers },
    );

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: text },
        { status: response.status },
      );
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    if (error instanceof TypeError && error.message.includes('fetch')) {
      return NextResponse.json(
        {
          error: 'Cannot connect to backend',
          details: `Ensure FastAPI is running at ${FASTAPI_URL}`,
        },
        { status: 503 },
      );
    }
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
