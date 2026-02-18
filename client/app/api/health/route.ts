import { NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const response = await fetch(`${FASTAPI_URL}/api/health`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Health check error:', error);
    return NextResponse.json(
      { error: 'Backend unreachable' },
      { status: 502 }
    );
  }
}
