/**
 * Package Resolve-Context API Route (proxy to FastAPI)
 *
 * POST /api/packages/resolve-context
 *   - Detect, set, or clear active package context for a session
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const body = await request.json();
    const url = `${FASTAPI_URL}/api/packages/resolve-context`;

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: errorText }, { status: response.status });
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
