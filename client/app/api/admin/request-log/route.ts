/**
 * Admin Request Log API Route (proxy to FastAPI)
 *
 * GET /api/admin/request-log?limit=200&path_filter=
 *   - Recent HTTP request history from in-memory ring buffer
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = `${FASTAPI_URL}/api/admin/request-log${queryString ? `?${queryString}` : ''}`;

    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    const authorization = request.headers.get('Authorization');
    if (authorization) headers['Authorization'] = authorization;

    const response = await fetch(url, { method: 'GET', headers });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Admin request-log GET error:', error);
    return NextResponse.json({ error: 'Failed to fetch request log' }, { status: 502 });
  }
}
