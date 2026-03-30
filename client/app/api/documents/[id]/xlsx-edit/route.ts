import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

interface RouteParams {
  params: Promise<{ id: string }>;
}

async function resolveDocKey(id: string, headers: Record<string, string>): Promise<string | null> {
  if (id.startsWith('eagle/')) return id;

  try {
    const listResponse = await fetch(`${FASTAPI_URL}/api/documents`, {
      method: 'GET',
      headers,
    });
    if (!listResponse.ok) return null;

    const data = await listResponse.json();
    const docs: Array<{ key?: string; name?: string }> = data.documents || [];
    const match = docs.find((doc) => {
      const key = doc.key || '';
      const name = doc.name || '';
      return name === id || key === id || key.endsWith(`/${id}`);
    });
    return match?.key || null;
  } catch {
    return null;
  }
}

export async function POST(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const authHeader = request.headers.get('authorization');

  let body: { cell_edits: unknown[]; change_source?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  if (!Array.isArray(body.cell_edits)) {
    return NextResponse.json({ error: 'Missing required field: cell_edits' }, { status: 400 });
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) headers.Authorization = authHeader;

  const docKey = await resolveDocKey(decodeURIComponent(id), headers);
  if (!docKey) {
    return NextResponse.json({ error: 'Document not found' }, { status: 404 });
  }

  try {
    const response = await fetch(
      `${FASTAPI_URL}/api/documents/xlsx-edit/${encodeURIComponent(docKey)}`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({
          cell_edits: body.cell_edits,
          change_source: body.change_source || 'user_edit',
        }),
      },
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: errorText }, { status: response.status });
    }

    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to save XLSX preview edits', details: String(error) },
      { status: 500 },
    );
  }
}
