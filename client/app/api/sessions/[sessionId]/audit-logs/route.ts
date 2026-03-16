/**
 * Session Audit Logs API Route (proxy to FastAPI)
 *
 * GET /api/sessions/[sessionId]/audit-logs
 *   - Get persisted SSE audit events for a session (all turns combined)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

interface RouteParams {
  params: Promise<{ sessionId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { sessionId } = await params;
    const url = `${FASTAPI_URL}/api/sessions/${sessionId}/audit-logs`;

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
    console.error('Audit logs GET error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch audit logs' },
      { status: 502 }
    );
  }
}
