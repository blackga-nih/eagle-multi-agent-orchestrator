/**
 * Admin Costs API Route
 *
 * GET /api/admin/costs?days=30&group_by=model
 *   - Proxies to FastAPI admin cost-report endpoint
 *   - Returns cost breakdown data (by model, by user, daily trends)
 *   - Query params forwarded: all cost-report filters
 *
 * Note: The Next.js route path is /api/admin/costs but it proxies
 * to FastAPI's /api/admin/cost-report endpoint.
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    // Forward all query parameters to FastAPI
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/admin/cost-report${queryString ? `?${queryString}` : ''}`;

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
      console.error(`Admin costs error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Admin costs API error:', error);

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
