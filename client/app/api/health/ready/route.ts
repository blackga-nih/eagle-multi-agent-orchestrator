/**
 * Readiness Probe API Route (proxy to FastAPI)
 *
 * GET /api/health/ready
 *   - Checks DynamoDB + Bedrock reachability (no auth required)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(_request: NextRequest) {
  try {
    const response = await fetch(`${FASTAPI_URL}/api/health/ready`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error('Health ready GET error:', error);
    return NextResponse.json(
      { status: 'degraded', checks: { proxy: 'error: backend unreachable' } },
      { status: 503 }
    );
  }
}
