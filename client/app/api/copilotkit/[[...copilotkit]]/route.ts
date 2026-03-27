/**
 * CopilotKit API Route — proxies AG-UI requests to the FastAPI backend.
 *
 * CopilotKit React components call this route, which forwards to
 * FastAPI's /copilotkit/* endpoint (mounted by agui_adapter.py).
 */

import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
export const fetchCache = 'force-no-store';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://127.0.0.1:8000';

async function handleRequest(req: NextRequest) {
  // Extract the CopilotKit sub-path from the URL
  const url = new URL(req.url);
  const fullPath = url.pathname; // e.g. /api/copilotkit/agent/eagle
  const copilotKitPath = fullPath.replace(/^\/api\/copilotkit/, '');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Forward auth header
  const authHeader = req.headers.get('authorization');
  if (authHeader) {
    headers['Authorization'] = authHeader;
  }

  // CopilotKit React SDK (REST mode) sends GET /info, but the Python SDK
  // only handles info at the root path (path == ''), not /info.
  // Convert GET /info to POST at the root copilotkit endpoint.
  const isInfoGet = req.method === 'GET' && copilotKitPath === '/info';
  const method = isInfoGet ? 'POST' : req.method;

  let body: string | undefined;
  if (isInfoGet) {
    body = '{}';
  } else if (req.method !== 'GET') {
    body = await req.text();
  }

  // CopilotKit v1.53 single-transport also sends POST /api/copilotkit with
  // {"method":"info"} (no /info path suffix).
  let isMethodInfoPost = false;
  if (body && (copilotKitPath === '' || copilotKitPath === '/')) {
    try {
      const parsed = JSON.parse(body);
      if (parsed.method === 'info') {
        isMethodInfoPost = true;
      }
    } catch {
      // Not JSON — ignore
    }
  }

  // Python CopilotKit SDK handles /info at root path (path == ''), not /info.
  // Route /info requests to the root copilotkit endpoint.
  const effectivePath = isInfoGet ? '/' : copilotKitPath || '/';
  const targetUrl = `${FASTAPI_URL}/copilotkit${effectivePath}`;

  const response = await fetch(targetUrl, {
    method,
    headers,
    body,
  });

  // /info response: the Python CopilotKit SDK (v0.1.78) returns agents as an
  // array [{name, description}] with key "sdkVersion", but the React SDK
  // v1.53 (@copilotkitnext) expects agents as a keyed object {name: {description}}
  // with key "version". Transform the response to bridge the gap.
  const isInfoRequest =
    copilotKitPath === '/info' || (copilotKitPath === '/' && isInfoGet) || isMethodInfoPost;
  if (isInfoRequest && response.ok) {
    try {
      const data = (await response.json()) as {
        agents?:
          | Array<{ name: string; description: string }>
          | Record<string, { description: string }>;
        sdkVersion?: string;
        version?: string;
        actions?: unknown[];
      };

      // Convert array format to keyed object if needed
      let agents: Record<string, { description: string }> = {};
      if (Array.isArray(data.agents)) {
        for (const a of data.agents) {
          agents[a.name] = { description: a.description };
        }
      } else if (data.agents && typeof data.agents === 'object') {
        agents = data.agents as Record<string, { description: string }>;
      }

      const transformed = {
        agents,
        actions: data.actions ?? [],
        version: data.version ?? data.sdkVersion ?? 'unknown',
      };

      return new Response(JSON.stringify(transformed), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    } catch {
      // Fall through to normal handling if JSON parse fails
    }
  }

  // Stream the response back — agent run/connect endpoints produce SSE.
  // The Python CopilotKit SDK incorrectly sets content-type: application/json
  // for SSE streams, so we detect agent endpoints and force text/event-stream
  // which @ag-ui/client requires to invoke its SSE parser.
  const isAgentEndpoint = copilotKitPath.includes('/agent/');
  const upstreamContentType = response.headers.get('content-type') || '';

  if (
    upstreamContentType.includes('text/event-stream') ||
    upstreamContentType.includes('application/json')
  ) {
    const { readable, writable } = new TransformStream();
    const upstream = response.body;
    if (upstream) {
      upstream.pipeTo(writable).catch(() => {});
    } else {
      writable.close();
    }

    // Force text/event-stream for agent endpoints so @ag-ui/client uses SSE parsing
    const contentType = isAgentEndpoint ? 'text/event-stream' : upstreamContentType;

    return new Response(readable, {
      status: response.status,
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      },
    });
  }

  // Non-streaming response
  const text = await response.text();
  return new Response(text, {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') || 'application/json',
    },
  });
}

export async function GET(req: NextRequest) {
  return handleRequest(req);
}

export async function POST(req: NextRequest) {
  return handleRequest(req);
}

export async function PUT(req: NextRequest) {
  return handleRequest(req);
}

export async function DELETE(req: NextRequest) {
  return handleRequest(req);
}
