import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

export async function GET() {
  try {
    const response = await fetch(`${FASTAPI_URL}/api/tools`, {
      signal: AbortSignal.timeout(5000),
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend returned ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: 'Cannot connect to backend' },
      { status: 503 }
    );
  }
}
