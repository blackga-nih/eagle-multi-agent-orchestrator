/**
 * Session Context API Route (proxy to FastAPI)
 *
 * GET /api/sessions/[sessionId]/context
 *   - Get preloaded context for a session (active package, checklist, preferences)
 */

import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

interface RouteParams {
  params: Promise<{ sessionId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { sessionId } = await params;
    const url = `${FASTAPI_URL}/api/sessions/${sessionId}/context`;

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
      signal: AbortSignal.timeout(15000),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Session context GET error:', error);
    return NextResponse.json({ error: 'Failed to fetch session context' }, { status: 502 });
  }
}
