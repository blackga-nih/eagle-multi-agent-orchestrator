/**
 * Session Messages API Route (proxy to FastAPI)
 *
 * GET /api/sessions/[sessionId]/messages?limit=N&offset=0
 *   - Get messages for a specific session
 *   - Forwards query params (e.g. limit, offset) to FastAPI
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

interface RouteParams {
  params: Promise<{ sessionId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { sessionId } = await params;
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/sessions/${sessionId}/messages${queryString ? `?${queryString}` : ''}`;

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const authorization = request.headers.get('Authorization');
    if (authorization) {
      headers['Authorization'] = authorization;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers,
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Session messages GET error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch session messages' },
      { status: 502 }
    );
  }
}
