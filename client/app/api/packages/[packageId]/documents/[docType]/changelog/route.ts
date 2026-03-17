import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ packageId: string; docType: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { packageId, docType } = await params;
  const limit = request.nextUrl.searchParams.get('limit') || '50';
  const authHeader = request.headers.get('authorization');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (authHeader) {
    headers.Authorization = authHeader;
  }

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/documents/${encodeURIComponent(docType)}/changelog?limit=${encodeURIComponent(limit)}`,
      {
        method: 'GET',
        headers,
      },
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: errorText },
        { status: response.status },
      );
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to fetch document changelog', details: String(error) },
      { status: 500 },
    );
  }
}
