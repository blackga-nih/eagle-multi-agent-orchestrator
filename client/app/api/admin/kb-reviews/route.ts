/**
 * KB Reviews Admin API Route
 *
 * GET /api/admin/kb-reviews?status=pending
 *   - Lists KB review records from DynamoDB via FastAPI backend
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status') ?? 'pending';

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(
      `${FASTAPI_URL}/api/admin/kb-reviews?status=${encodeURIComponent(status)}`,
      { method: 'GET', headers }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: `Backend error: ${response.status}`, detail: errorText }, { status: response.status });
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('KB reviews GET error:', error);
    return NextResponse.json({ error: 'Internal server error', details: String(error) }, { status: 500 });
  }
}
