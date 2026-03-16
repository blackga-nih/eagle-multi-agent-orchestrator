import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ packageId: string; docType: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { packageId, docType } = await params;
  const version = request.nextUrl.searchParams.get('version');
  const authHeader = request.headers.get('authorization');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (authHeader) {
    headers.Authorization = authHeader;
  }

  const query = version ? `?version=${encodeURIComponent(version)}` : '';

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/documents/${encodeURIComponent(docType)}${query}`,
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
      { error: 'Failed to fetch package document', details: String(error) },
      { status: 500 },
    );
  }
}
