/**
 * /api/diagrams — Diagram Generation Endpoint
 *
 * Proxies to the FastAPI backend with an Excalidraw-specific system prompt
 * injected into the user message. Claude is instructed to output Excalidraw
 * element JSON in a ```json code block alongside its explanation.
 *
 * The frontend (admin/diagrams page) parses the JSON block when streaming
 * completes and loads the elements directly into the Excalidraw canvas.
 */

import { NextRequest, NextResponse } from 'next/server';

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

const DIAGRAM_SYSTEM_PROMPT = `You are an expert diagram assistant integrated with an Excalidraw canvas.

When the user asks you to create, draw, or design a diagram, you MUST:
1. Briefly describe what you're drawing (1-2 sentences)
2. Output a JSON code block containing Excalidraw elements

The JSON must be an array of Excalidraw elements. Each element requires:
- id: unique string (e.g. "el-1", "el-2")
- type: "rectangle" | "ellipse" | "diamond" | "arrow" | "text" | "line"
- x, y: position (numbers, spread elements across a 800x600 canvas)
- width, height: size (rectangles/ellipses/diamonds typically 120-200 wide, 50-80 tall)
- angle: 0
- strokeColor: "#1e1e1e"
- backgroundColor: "transparent" (or light hex like "#e3f2fd" for fills)
- fillStyle: "solid"
- strokeWidth: 2
- roughness: 1
- opacity: 100
- roundness: { type: 3 } for rectangles with rounded corners, null for sharp
- For text elements: add "text", "fontSize": 16, "fontFamily": 1, "textAlign": "center", "verticalAlign": "middle"
- For arrow elements: add "startArrowhead": null, "endArrowhead": "arrow", "points": [[0,0],[dx,dy]] where dx/dy is the delta

Example JSON structure:
\`\`\`json
[
  {"id":"el-1","type":"rectangle","x":100,"y":100,"width":160,"height":60,"angle":0,"strokeColor":"#1e1e1e","backgroundColor":"#e3f2fd","fillStyle":"solid","strokeWidth":2,"roughness":1,"opacity":100,"roundness":{"type":3}},
  {"id":"el-2","type":"text","x":140,"y":120,"width":80,"height":20,"angle":0,"strokeColor":"#1e1e1e","backgroundColor":"transparent","fillStyle":"solid","strokeWidth":1,"roughness":1,"opacity":100,"text":"Service A","fontSize":14,"fontFamily":1,"textAlign":"center","verticalAlign":"middle"}
]
\`\`\`

Always provide the JSON block so the canvas can render your diagram. Keep diagrams clear with 5-15 elements.
Do NOT wrap shapes with extra text elements unless the type is "text". For labeled shapes, use the shape element with text property if supported, or add a separate text element at the same position.`;

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const userMessage: string = body.message || body.prompt || body.query || '';

    if (!userMessage.trim()) {
      return NextResponse.json({ error: 'Missing message' }, { status: 400 });
    }

    const authHeader = request.headers.get('authorization');
    const sessionId = body.session_id || crypto.randomUUID();

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authHeader) headers['Authorization'] = authHeader;

    // Inject diagram instructions before the user message
    const fullMessage = `${DIAGRAM_SYSTEM_PROMPT}\n\n---\nUser request: ${userMessage}`;

    const fastApiBody = { message: fullMessage, session_id: sessionId };

    // Try SSE streaming first
    const response = await fetch(`${FASTAPI_URL}/api/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(fastApiBody),
    });

    if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
      return new Response(response.body, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
        },
      });
    }

    // Fallback to REST
    const restResp = await fetch(`${FASTAPI_URL}/api/chat`, {
      method: 'POST',
      headers,
      body: JSON.stringify(fastApiBody),
    });

    if (!restResp.ok) {
      return NextResponse.json(
        { error: `Backend error: ${restResp.status}` },
        { status: restResp.status },
      );
    }

    const data = await restResp.json();
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        const textEvent = {
          type: 'text',
          agent_id: 'diagram-assistant',
          agent_name: 'Diagram Assistant',
          content: data.response || '',
          timestamp: new Date().toISOString(),
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(textEvent)}\n\n`));

        const completeEvent = {
          type: 'complete',
          agent_id: 'diagram-assistant',
          agent_name: 'Diagram Assistant',
          timestamp: new Date().toISOString(),
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(completeEvent)}\n\n`));
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
    console.error('Diagrams API route error:', error);
    return NextResponse.json(
      { error: 'Internal server error', details: String(error) },
      { status: 500 },
    );
  }
}
