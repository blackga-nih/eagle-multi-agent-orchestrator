import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ packageId: string; docType: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { packageId, docType } = await params;
  const format = request.nextUrl.searchParams.get('format') || 'original';
  const version = request.nextUrl.searchParams.get('version');
  const authHeader = request.headers.get('authorization');

  const headers: Record<string, string> = {};
  if (authHeader) headers.Authorization = authHeader;

  const query = new URLSearchParams({ format });
  if (version) query.set('version', version);

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/documents/${encodeURIComponent(docType)}/download?${query.toString()}`,
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

    const blob = await response.blob();
    const disposition =
      response.headers.get('content-disposition') ||
      `attachment; filename="${docType}.${format}"`;
    const contentType = response.headers.get('content-type') || 'application/octet-stream';

    return new NextResponse(blob, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': disposition,
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to download package document', details: String(error) },
      { status: 500 },
    );
  }
}
