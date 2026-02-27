/**
 * FastAPI Chat Streaming API Route
 *
 * Proxies requests to the FastAPI backend and streams
 * multi-agent SSE events back to the frontend.
 *
 * Backend: FastAPI POST /api/chat/stream (SSE)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    if (!body.prompt && !body.query) {
      return NextResponse.json(
        { error: 'Missing required field: prompt or query' },
        { status: 400 }
      );
    }

    const sessionId = body.session_id || crypto.randomUUID();
    const message = body.prompt || body.query;

    // Forward Authorization header from client
    const authHeader = request.headers.get('authorization');

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (authHeader) {
      headers['Authorization'] = authHeader;
    }

    // Transform to FastAPI chat request format
    const fastApiBody = {
      message,
      session_id: sessionId,
    };

    // Try SSE streaming endpoint first
    const response = await fetch(`${FASTAPI_URL}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(fastApiBody),
    });

    if (!response.ok) {
      // Fall back to REST chat endpoint
      const restResponse = await fetch(`${FASTAPI_URL}/api/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify(fastApiBody),
      });

      if (!restResponse.ok) {
        const errorText = await restResponse.text();
        console.error(`FastAPI error: ${restResponse.status} - ${errorText}`);
        return NextResponse.json(
          { error: `Backend error: ${restResponse.status}` },
          { status: restResponse.status }
        );
      }

      // Convert REST response to SSE format for consistent frontend handling
      const data = await restResponse.json();
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          const event = {
            type: 'text',
            agent_id: 'eagle-assistant',
            agent_name: 'EAGLE Assistant',
            content: data.response,
            timestamp: new Date().toISOString(),
          };
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));

          const complete = {
            type: 'complete',
            agent_id: 'eagle-assistant',
            agent_name: 'EAGLE Assistant',
            metadata: {
              session_id: data.session_id,
              usage: data.usage,
              model: data.model,
              tools_called: data.tools_called,
              cost_usd: data.cost_usd,
            },
            timestamp: new Date().toISOString(),
          };
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(complete)}\n\n`));
          controller.close();
        },
      });

      return new Response(stream, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    const contentType = response.headers.get('content-type');

    if (contentType?.includes('text/event-stream')) {
      // Pass through SSE stream directly — formats are compatible
      return new Response(response.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    // Handle JSON response (batch of events)
    const data = await response.json();

    if (data.stream_events && Array.isArray(data.stream_events)) {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          for (const event of data.stream_events) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
          }
          controller.close();
        },
      });

      return new Response(stream, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error('API route error:', error);

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

/**
 * Health check — pings FastAPI backend
 */
export async function GET() {
  try {
    const response = await fetch(`${FASTAPI_URL}/api/tools`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000),
    });

    if (response.ok) {
      return NextResponse.json({
        status: 'healthy',
        backend: FASTAPI_URL,
        timestamp: new Date().toISOString(),
      });
    }

    return NextResponse.json(
      {
        status: 'unhealthy',
        backend: FASTAPI_URL,
        error: `Backend returned ${response.status}`,
      },
      { status: 503 }
    );
  } catch {
    return NextResponse.json(
      {
        status: 'unhealthy',
        backend: FASTAPI_URL,
        error: 'Cannot connect to backend',
      },
      { status: 503 }
    );
  }
}
