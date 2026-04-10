import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const authHeader = request.headers.get('authorization');

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(`${FASTAPI_URL}/api/feedback/message`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(8_000),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      console.error(`[feedback/message proxy] Backend returned ${response.status}: ${errorText}`);
      let detail = 'Failed to submit feedback';
      try { detail = JSON.parse(errorText).detail || detail; } catch {}
      return NextResponse.json({ error: detail }, { status: response.status });
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error('[feedback/message proxy] Failed to forward feedback to backend:', msg);
    return NextResponse.json({ error: `Failed to submit feedback: ${msg}` }, { status: 500 });
  }
}
