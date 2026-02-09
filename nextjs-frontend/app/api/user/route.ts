/**
 * User API Route
 *
 * Proxies user profile requests to the FastAPI backend.
 *
 * GET /api/user
 *   - Returns the authenticated user's profile from FastAPI
 *   - Requires Authorization header (forwarded to backend)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');

    if (!authHeader) {
      return NextResponse.json(
        { error: 'Missing Authorization header' },
        { status: 401 }
      );
    }

    const response = await fetch(`${FASTAPI_URL}/api/user/me`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authHeader,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`FastAPI /api/user/me error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('User API error:', error);

    if (error instanceof TypeError && error.message.includes('fetch')) {
      return NextResponse.json(
        {
          error: 'Cannot connect to backend',
          details: `Ensure FastAPI is running at ${FASTAPI_URL}`,
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 }
    );
  }
}
