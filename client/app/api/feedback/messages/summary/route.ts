import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(`${FASTAPI_URL}/api/feedback/messages/summary`, { headers });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: 'Failed to fetch summary' }, { status: 500 });
  }
}
