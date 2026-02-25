/**
 * FastAPI Chat API Route
 *
 * Proxies requests to the FastAPI backend and emits SSE-formatted
 * events back to the frontend for compatibility.
 *
 * Backend: FastAPI POST /api/chat (JSON)
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

function normalizeSlashCommand(input: string): string {
  const message = input.trim();
  if (!message.startsWith('/')) return message;

  const [rawCommand, ...restParts] = message.split(/\s+/);
  const command = rawCommand.toLowerCase();
  const rest = restParts.join(' ').trim();

  switch (command) {
    case '/document':
      return rest
        ? `Create the requested acquisition document(s): ${rest}`
        : 'Create the requested acquisition document(s).';
    case '/research':
      return rest
        ? `Research this acquisition/regulatory question and provide guidance: ${rest}`
        : 'Research acquisition/regulatory guidance for me.';
    case '/status':
      return 'Show the current acquisition package status, completed artifacts, and next steps.';
    case '/help':
      return 'List your capabilities and the best commands/prompts to generate acquisition artifacts.';
    case '/acquisition-package':
      return rest
        ? `Start a new acquisition package using this information: ${rest}`
        : 'Start a new acquisition package and ask me for the minimum required intake details.';
    default:
      // Unknown slash command: remove the leading command token and keep user intent text.
      return rest || message.replace(/^\//, '');
  }
}

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
    const rawMessage = body.prompt || body.query;
    const message = normalizeSlashCommand(rawMessage);

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

    const response = await fetch(`${FASTAPI_URL}/api/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify(fastApiBody),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`FastAPI error: ${response.status} - ${errorText}`);
      return NextResponse.json(
        { error: `Backend error: ${response.status}` },
        { status: response.status }
      );
    }

    // Convert REST response to SSE format for consistent frontend handling
    const data = await response.json();
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
 * Health check - pings FastAPI backend
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
