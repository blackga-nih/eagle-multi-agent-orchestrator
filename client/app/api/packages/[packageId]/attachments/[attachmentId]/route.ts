import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ packageId: string; attachmentId: string }>;
}

export async function PATCH(request: NextRequest, { params }: RouteParams) {
  const { packageId, attachmentId } = await params;
  const authHeader = request.headers.get('authorization');
  const body = await request.text();

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (authHeader) headers.Authorization = authHeader;

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/attachments/${encodeURIComponent(attachmentId)}`,
      {
        method: 'PATCH',
        headers,
        body,
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
      { error: 'Failed to update package attachment', details: String(error) },
      { status: 500 },
    );
  }
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  const { packageId, attachmentId } = await params;
  const authHeader = request.headers.get('authorization');

  const headers: Record<string, string> = {};
  if (authHeader) headers.Authorization = authHeader;

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/packages/${encodeURIComponent(packageId)}/attachments/${encodeURIComponent(attachmentId)}`,
      {
        method: 'DELETE',
        headers,
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
      { error: 'Failed to delete package attachment', details: String(error) },
      { status: 500 },
    );
  }
}
