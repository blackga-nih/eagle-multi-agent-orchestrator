/**
 * KB Review Approve Route
 *
 * POST /api/admin/kb-review/{id}/approve
 *   - Approves a pending KB review: applies diff to matrix.json and moves doc to approved/
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const authHeader = request.headers.get('authorization');
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const response = await fetch(
      `${FASTAPI_URL}/api/admin/kb-review/${encodeURIComponent(id)}/approve`,
      { method: 'POST', headers }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: `Backend error: ${response.status}`, detail: errorText }, { status: response.status });
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    console.error('KB review approve error:', error);
    return NextResponse.json({ error: 'Internal server error', details: String(error) }, { status: 500 });
  }
}
