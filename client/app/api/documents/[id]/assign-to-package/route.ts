import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ id: string }>;
}

async function parseBackendError(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) return `Backend error: ${response.status}`;

  try {
    const parsed = JSON.parse(text) as { detail?: string; error?: string; message?: string };
    return parsed.detail || parsed.error || parsed.message || text;
  } catch {
    return text;
  }
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const authHeader = request.headers.get('authorization');

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (authHeader) {
    headers.Authorization = authHeader;
  }

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/documents/${encodeURIComponent(decodeURIComponent(id))}/assign-to-package`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      },
    );

    if (!response.ok) {
      const errorText = await parseBackendError(response);
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: errorText },
        { status: response.status },
      );
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to assign uploaded document', details: String(error) },
      { status: 500 },
    );
  }
}
