/**
 * Documents API Route
 *
 * Proxies document requests to the FastAPI backend.
 *
 * GET /api/documents
 *   - List documents for the authenticated user
 *   - Requires Authorization header (forwarded to backend)
 *
 * POST /api/documents
 *   - Export a document via FastAPI (proxies to /api/documents/export)
 *   - Returns a streaming response with proper content-type
 *     and content-disposition headers from the backend
 *   - Requires Authorization header (forwarded to backend)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');

    if (!authHeader) {
      return NextResponse.json(
        { error: 'Missing Authorization header' },
        { status: 401 }
      );
    }

    // Forward all query parameters to the backend
    const { searchParams } = new URL(request.url);
    const queryString = searchParams.toString();
    const url = queryString
      ? `${FASTAPI_URL}/api/documents?${queryString}`
      : `${FASTAPI_URL}/api/documents`;

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authHeader,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`FastAPI /api/documents error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Documents GET error:', error);

    if (error instanceof TypeError && error.message.includes('fetch')) {
      return NextResponse.json(
        {
          error: 'Cannot connect to backend',
          details: `Ensure FastAPI is running at ${FASTAPI_URL}`,
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get('authorization');

    if (!authHeader) {
      return NextResponse.json(
        { error: 'Missing Authorization header' },
        { status: 401 }
      );
    }

    const body = await request.json();

    const response = await fetch(`${FASTAPI_URL}/api/documents/export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': authHeader,
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`FastAPI /api/documents/export error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    // Build response headers from the backend response
    const responseHeaders = new Headers();

    const contentType = response.headers.get('content-type');
    if (contentType) {
      responseHeaders.set('Content-Type', contentType);
    }

    const contentDisposition = response.headers.get('content-disposition');
    if (contentDisposition) {
      responseHeaders.set('Content-Disposition', contentDisposition);
    }

    const contentLength = response.headers.get('content-length');
    if (contentLength) {
      responseHeaders.set('Content-Length', contentLength);
    }

    // Stream the response body back to the client
    return new Response(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error('Documents POST (export) error:', error);

    if (error instanceof TypeError && error.message.includes('fetch')) {
      return NextResponse.json(
        {
          error: 'Cannot connect to backend',
          details: `Ensure FastAPI is running at ${FASTAPI_URL}`,
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 }
    );
  }
}
