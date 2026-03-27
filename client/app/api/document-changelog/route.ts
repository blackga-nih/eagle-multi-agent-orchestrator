/**
 * Document Changelog API Route
 *
 * GET /api/document-changelog?key=...&limit=50
 *   - Proxies to FastAPI /api/document-changelog
 *   - Returns changelog entries for a document by S3 key
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const key = searchParams.get('key');
  const limit = searchParams.get('limit') || '50';

  if (!key) {
    return NextResponse.json({ error: 'Missing key parameter' }, { status: 400 });
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  const authHeader = request.headers.get('authorization');
  if (authHeader) {
    headers.Authorization = authHeader;
  }

  const url = `${FASTAPI_URL}/api/document-changelog?key=${encodeURIComponent(key)}&limit=${limit}`;

  try {
    const response = await fetch(url, { headers });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: errorText },
        { status: response.status },
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to fetch changelog', details: String(error) },
      { status: 500 },
    );
  }
}
