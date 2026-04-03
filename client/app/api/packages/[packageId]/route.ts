import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ packageId: string }> },
) {
  try {
    const { packageId } = await params;
    const authHeader = request.headers.get('authorization');
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    const url = `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}`;

    const response = await fetch(url, {
      method: 'DELETE',
      headers,
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: errorText }, { status: response.status });
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 500 });
  }
}
