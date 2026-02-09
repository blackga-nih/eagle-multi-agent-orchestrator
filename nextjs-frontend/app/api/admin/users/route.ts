/**
 * Admin Users API Route
 *
 * GET /api/admin/users?days=30&limit=50
 *   - Proxies to FastAPI admin users endpoint
 *   - Returns user activity data (session counts, last active, costs per user)
 *   - Query params forwarded: days (period filter), limit (max results)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    // Forward all query parameters to FastAPI
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/admin/users${queryString ? `?${queryString}` : ''}`;

    // Forward Authorization header from client
    const authHeader = request.headers.get('authorization');

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (authHeader) {
      headers['Authorization'] = authHeader;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers,
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Admin users error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Admin users API error:', error);

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
