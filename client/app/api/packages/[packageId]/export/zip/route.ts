import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ packageId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { packageId } = await params;
  const format = request.nextUrl.searchParams.get('format') || 'docx';
  const authHeader = request.headers.get('authorization');

  const headers: Record<string, string> = {};
  if (authHeader) {
    headers.Authorization = authHeader;
  }

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/export/zip?format=${encodeURIComponent(format)}`,
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
    const disposition = response.headers.get('content-disposition') || `attachment; filename="${packageId}.zip"`;

    return new NextResponse(blob, {
      status: 200,
      headers: {
        'Content-Type': 'application/zip',
        'Content-Disposition': disposition,
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to export package ZIP', details: String(error) },
      { status: 500 },
    );
  }
}
