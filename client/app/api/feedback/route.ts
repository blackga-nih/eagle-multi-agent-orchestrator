import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

// Screenshots are base64-encoded PNGs that can exceed the default 1MB limit.
// Without this, Next.js returns 403 for oversized payloads.
export const maxDuration = 30;

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

// Max payload size we'll accept (5MB) — matches backend S3 screenshot cap
const MAX_BODY_BYTES = 5 * 1024 * 1024;

export async function POST(request: NextRequest) {
  try {
    // Guard against oversized payloads before parsing
    const contentLength = request.headers.get('content-length');
    if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
      return NextResponse.json(
        { error: 'Payload too large. Try removing the screenshot.' },
        { status: 413 },
      );
    }

    const body = await request.json();
    const authHeader = request.headers.get('authorization');

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(`${FASTAPI_URL}/api/feedback`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(8_000),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
      return NextResponse.json(
        { error: errorData.detail || 'Failed to submit feedback' },
        { status: response.status },
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error('[feedback proxy] Failed to forward feedback to backend:', msg);
    return NextResponse.json({ error: `Failed to submit feedback: ${msg}` }, { status: 500 });
  }
}
