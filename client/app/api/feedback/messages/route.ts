import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const authHeader = request.headers.get('authorization');
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(
      `${FASTAPI_URL}/api/feedback/messages${queryString ? `?${queryString}` : ''}`,
      { headers, signal: AbortSignal.timeout(8_000) },
    );
    if (!response.ok) {
      const errorText = await response.text().catch(() => 'Unknown error');
      console.error(`[feedback/messages proxy] Backend returned ${response.status}: ${errorText}`);
      return NextResponse.json({ error: 'Failed to fetch feedback' }, { status: response.status });
    }
    const data = await response.json();
    return NextResponse.json(data);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    console.error('[feedback/messages proxy] Error:', msg);
    return NextResponse.json({ error: 'Failed to fetch feedback' }, { status: 500 });
  }
}
