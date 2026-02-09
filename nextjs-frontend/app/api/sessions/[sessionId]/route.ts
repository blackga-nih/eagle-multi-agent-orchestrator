/**
 * Individual Session API Route (proxy to FastAPI)
 *
 * GET /api/sessions/[sessionId]
 *   - Get a specific session by ID
 *
 * DELETE /api/sessions/[sessionId]
 *   - Delete a specific session by ID
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

interface RouteParams {
  params: Promise<{ sessionId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  try {
    const { sessionId } = await params;

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const authorization = request.headers.get('Authorization');
    if (authorization) {
      headers['Authorization'] = authorization;
    }

    const response = await fetch(`${FASTAPI_URL}/api/sessions/${sessionId}`, {
      method: 'GET',
      headers,
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Session GET error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch session' },
      { status: 502 }
    );
  }
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  try {
    const { sessionId } = await params;

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const authorization = request.headers.get('Authorization');
    if (authorization) {
      headers['Authorization'] = authorization;
    }

    const response = await fetch(`${FASTAPI_URL}/api/sessions/${sessionId}`, {
      method: 'DELETE',
      headers,
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Session DELETE error:', error);
    return NextResponse.json(
      { error: 'Failed to delete session' },
      { status: 502 }
    );
  }
}
