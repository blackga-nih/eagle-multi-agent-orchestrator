/**
 * Document Upload API Route
 *
 * POST /api/documents/upload
 *   - Proxies multipart file upload to FastAPI backend
 *   - Requires Authorization header (forwarded to backend)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    const queryString = request.nextUrl.searchParams.toString();

    // Forward multipart body directly — don't parse, just pipe
    const formData = await request.formData();

    const headers: Record<string, string> = {};
    if (authHeader) headers['Authorization'] = authHeader;
    // Do NOT set Content-Type — let fetch set the multipart boundary automatically

    const url = queryString
      ? `${FASTAPI_URL}/api/documents/upload?${queryString}`
      : `${FASTAPI_URL}/api/documents/upload`;

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`FastAPI /api/documents/upload error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: errorText },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Document upload error:', error);

    if (error instanceof TypeError && error.message.includes('fetch')) {
      return NextResponse.json(
        {
          error: 'Cannot connect to backend',
          detail: `Ensure FastAPI is running at ${FASTAPI_URL}`,
          details: String(error),
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      {
        error: 'Internal server error',
        detail: error instanceof Error ? error.message : 'Unexpected upload proxy error',
        details: String(error),
      },
      { status: 500 }
    );
  }
}
