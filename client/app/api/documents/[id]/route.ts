/**
 * Individual Document API Route
 *
 * GET /api/documents/[id]?content=true
 *   - Proxies to FastAPI /api/documents/{doc_key:path}
 *   - Supports ids passed as full S3 keys or legacy filename-only ids
 *
 * PUT/DELETE are currently unsupported in the FastAPI document API.
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';
const DEV_MODE = process.env.DEV_MODE === 'true' || process.env.NODE_ENV === 'development';

interface RouteParams {
  params: Promise<{ id: string }>;
}

const DOC_TYPE_BY_PREFIX: Array<{ prefix: string; type: string; title: string }> = [
  { prefix: 'acquisition_plan', type: 'acquisition_plan', title: 'Acquisition Plan' },
  { prefix: 'market_research', type: 'market_research', title: 'Market Research' },
  { prefix: 'security_checklist', type: 'security_checklist', title: 'Security Checklist' },
  { prefix: 'contract_type_justification', type: 'contract_type_justification', title: 'Contract Type Justification' },
  { prefix: 'cor_certification', type: 'cor_certification', title: 'COR Certification' },
  { prefix: 'eval_criteria', type: 'eval_criteria', title: 'Evaluation Criteria' },
  { prefix: 'section_508', type: 'section_508', title: 'Section 508 Compliance' },
  { prefix: 'justification', type: 'justification', title: 'Justification & Approval' },
  { prefix: 'igce', type: 'igce', title: 'Cost Estimate (IGCE)' },
  { prefix: 'sow', type: 'sow', title: 'Statement of Work' },
];

function inferDocTypeAndTitle(fileName: string): { document_type: string; title: string } {
  const base = fileName.toLowerCase();
  for (const entry of DOC_TYPE_BY_PREFIX) {
    if (base.startsWith(`${entry.prefix}_`) || base === entry.prefix || base.includes(`${entry.prefix}.`)) {
      return { document_type: entry.type, title: entry.title };
    }
  }

  if (base.endsWith('.docx')) {
    return { document_type: 'docx', title: 'Word Document' };
  }
  if (base.endsWith('.pdf')) {
    return { document_type: 'pdf', title: 'PDF Document' };
  }
  if (base.endsWith('.md')) {
    return { document_type: 'markdown', title: 'Markdown Document' };
  }

  return { document_type: 'document', title: 'Document' };
}

async function resolveDocKey(id: string, headers: Record<string, string>): Promise<string | null> {
  if (id.startsWith('eagle/')) return id;

  // Legacy ids may only contain a filename. Resolve by listing user docs.
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

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const decodedId = decodeURIComponent(id);
  const includeContent = request.nextUrl.searchParams.get('content') !== 'false';

  const authHeader = request.headers.get('authorization');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (authHeader) {
    headers.Authorization = authHeader;
  }

  const docKey = await resolveDocKey(decodedId, headers);
  if (!docKey) {
    return NextResponse.json(
      {
        error: 'Document not found',
        detail: 'Could not resolve document key from id',
      },
      { status: 404 },
    );
  }

  try {
    const query = includeContent ? '?content=true' : '';
    const response = await fetch(`${FASTAPI_URL}/api/documents/${encodeURIComponent(docKey)}${query}`, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: `Backend error: ${response.status}`, detail: errorText },
        { status: response.status },
      );
    }

    const data = await response.json();
    const key = data.key || docKey;
    const fileName = key.split('/').pop() || decodedId;
    const inferred = inferDocTypeAndTitle(fileName);

    return NextResponse.json({
      ...data,
      key,
      s3_key: key,
      document_id: key,
      document_type: inferred.document_type,
      title: data.title || inferred.title,
    });
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to fetch document', details: String(error) },
      { status: 500 },
    );
  }
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const { id } = await params;
  const authHeader = request.headers.get('authorization');

  let body: { content: string; change_source?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  if (!body.content || typeof body.content !== 'string') {
    return NextResponse.json({ error: 'Missing required field: content' }, { status: 400 });
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (authHeader) headers.Authorization = authHeader;

  const docKey = await resolveDocKey(decodeURIComponent(id), headers);
  if (!docKey) {
    return NextResponse.json({ error: 'Document not found' }, { status: 404 });
  }

  try {
    const response = await fetch(`${FASTAPI_URL}/api/documents/${encodeURIComponent(docKey)}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        content: body.content,
        change_source: body.change_source || 'user_edit',
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json({ error: errorText }, { status: response.status });
    }
    return NextResponse.json(await response.json());
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to update document', details: String(error) },
      { status: 500 },
    );
  }
}

export async function DELETE(_request: NextRequest, { params }: RouteParams) {
  if (DEV_MODE) {
    const { id } = await params;
    return NextResponse.json({
      success: true,
      status: 'not_implemented_dev',
      message: 'Document delete is not yet implemented in FastAPI route',
      document_id: decodeURIComponent(id),
    });
  }
  return NextResponse.json(
    { error: 'Document delete endpoint is not implemented for this route' },
    { status: 501 },
  );
}
