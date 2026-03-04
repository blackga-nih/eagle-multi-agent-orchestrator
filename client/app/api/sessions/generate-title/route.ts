/**
 * Generate Title API Route (proxy to FastAPI)
 *
 * POST /api/sessions/generate-title
 *   - Generates an AI-powered session title from the user's first message
 *   - Gracefully falls back to "New Session" on any backend error
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

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

    const response = await fetch(`${FASTAPI_URL}/api/generate-title`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      return NextResponse.json({ title: 'New Session' });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    // Backend unavailable or timeout — return graceful fallback
    return NextResponse.json({ title: 'New Session' });
  }
}
