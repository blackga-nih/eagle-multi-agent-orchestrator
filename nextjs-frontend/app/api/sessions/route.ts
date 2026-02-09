/**
 * Sessions API Route (proxy to FastAPI)
 *
 * GET /api/sessions?limit=N
 *   - List sessions for the authenticated user
 *   - Forwards query params (e.g. limit) to FastAPI
 *
 * POST /api/sessions
 *   - Create a new session
 *   - Forwards request body to FastAPI
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/sessions${queryString ? `?${queryString}` : ''}`;

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
    console.error('Sessions GET error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch sessions' },
      { status: 502 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const authorization = request.headers.get('Authorization');
    if (authorization) {
      headers['Authorization'] = authorization;
    }

    const response = await fetch(`${FASTAPI_URL}/api/sessions`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Sessions POST error:', error);
    return NextResponse.json(
      { error: 'Failed to create session' },
      { status: 502 }
    );
  }
}
