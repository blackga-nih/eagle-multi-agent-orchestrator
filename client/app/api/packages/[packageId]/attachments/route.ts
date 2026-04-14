import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ packageId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { packageId } = await params;
  const authHeader = request.headers.get('authorization');
  const queryString = request.nextUrl.searchParams.toString();

  const headers: Record<string, string> = {};
  if (authHeader) headers.Authorization = authHeader;

  const url = queryString
    ? `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/attachments?${queryString}`
    : `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/attachments`;

  try {
    const response = await fetch(url, { method: 'GET', headers });
    const text = await response.text();
    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: text },
        { status: response.status },
      );
    }
    return new NextResponse(text, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to fetch package attachments', details: String(error) },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  const { packageId } = await params;
  const authHeader = request.headers.get('authorization');
  const contentType = request.headers.get('content-type');

  const headers: Record<string, string> = {};
  if (authHeader) headers.Authorization = authHeader;
  if (contentType) headers['Content-Type'] = contentType;

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/attachments`,
      {
        method: 'POST',
        headers,
        body: request.body,
        duplex: 'half',
      },
    );

    const text = await response.text();
    if (!response.ok) {
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: text },
        { status: response.status },
      );
    }

    return new NextResponse(text, {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to upload package attachment', details: String(error) },
      { status: 500 },
    );
  }
}
