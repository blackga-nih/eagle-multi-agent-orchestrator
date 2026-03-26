/**
 * Knowledge Base API Route
 *
 * GET /api/knowledge-base
 *   - List/search knowledge base documents from the metadata table
 *   - Supports query, topic, document_type, agent filters
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = queryString
      ? `${FASTAPI_URL}/api/knowledge-base?${queryString}`
      : `${FASTAPI_URL}/api/knowledge-base`;

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(url, { method: 'GET', headers });

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
        { error: 'Cannot connect to backend', details: `Ensure FastAPI is running at ${FASTAPI_URL}` },
        { status: 503 },
      );
    }
    return NextResponse.json({ error: 'Internal server error', details: String(error) }, { status: 500 });
  }
}
