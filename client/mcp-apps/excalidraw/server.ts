/**
 * Excalidraw MCP App Server
 *
 * Exposes two MCP tools:
 *  - create_diagram  (model + app) — opens Excalidraw with optional pre-loaded elements
 *  - reset_diagram   (app only)    — clears the canvas
 *
 * The bundled Excalidraw UI is served as a ui:// resource so any MCP Apps-
 * compatible host (Claude.ai, EAGLE admin chat) can render it inline.
 *
 * Usage:
 *   npm run build   # bundle the React UI → dist/mcp-app.html
 *   npm run serve   # start this HTTP server on PORT (default 3002)
 */

import {
  registerAppTool,
  registerAppResource,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import cors from "cors";
import express from "express";
import fs from "node:fs/promises";
import path from "node:path";

// ── constants ────────────────────────────────────────────────────────────────

const PORT = Number(process.env.PORT ?? 3002);

// Works from both `tsx server.ts` (source) and `node dist/server.js` (compiled)
const DIST_DIR = import.meta.filename?.endsWith(".ts")
  ? path.join(import.meta.dirname, "dist")
  : import.meta.dirname;

const RESOURCE_URI = "ui://excalidraw/mcp-app.html";

// ── MCP server ────────────────────────────────────────────────────────────────

const mcpServer = new McpServer({
  name: "EAGLE Excalidraw MCP App",
  version: "1.0.0",
});

/**
 * create_diagram — opens an interactive Excalidraw canvas.
 *
 * Claude can call this with an array of Excalidraw elements to pre-populate
 * the canvas, or omit `elements` to open a blank canvas the admin can draw on.
 */
registerAppTool(
  mcpServer,
  "create_diagram",
  {
    title: "Create Diagram",
    description:
      "Opens an interactive Excalidraw diagram canvas inside the chat. " +
      "Provide a title and optional Excalidraw elements JSON array to pre-populate the canvas. " +
      "The admin can then edit the diagram live.",
    inputSchema: {
      type: "object" as const,
      properties: {
        title: {
          type: "string",
          description: "Diagram title shown in the canvas header",
        },
        elements: {
          type: "array",
          description:
            "Excalidraw elements array. Each element should have: id, type (rectangle|ellipse|arrow|text|diamond|line), x, y, width, height, strokeColor, backgroundColor, text (for text elements), fontSize.",
          items: { type: "object" },
        },
        appState: {
          type: "object",
          description: "Optional Excalidraw appState overrides (viewBackgroundColor, zoom, etc.)",
        },
      },
      required: ["title"],
    },
    _meta: { ui: { resourceUri: RESOURCE_URI } },
  },
  async (args) => {
    const payload = {
      title: (args.title as string) ?? "New Diagram",
      elements: (args.elements as unknown[]) ?? [],
      appState: (args.appState as Record<string, unknown>) ?? {},
    };
    return {
      content: [{ type: "text" as const, text: JSON.stringify(payload) }],
    };
  },
);

/**
 * reset_diagram — clears the canvas. App-only visibility so the
 * "Clear" button in the UI can call it without the model seeing the tool.
 */
registerAppTool(
  mcpServer,
  "reset_diagram",
  {
    title: "Reset Canvas",
    description: "Clears all elements from the Excalidraw canvas.",
    inputSchema: { type: "object" as const, properties: {} },
    _meta: { ui: { resourceUri: RESOURCE_URI, visibility: ["app"] } },
  },
  async () => ({
    content: [
      {
        type: "text" as const,
        text: JSON.stringify({ title: "New Diagram", elements: [], appState: {} }),
      },
    ],
  }),
);

/**
 * Resource handler — serves the bundled Excalidraw HTML to the host.
 */
registerAppResource(
  mcpServer,
  RESOURCE_URI,
  RESOURCE_URI,
  { mimeType: RESOURCE_MIME_TYPE },
  async () => {
    const htmlPath = path.join(DIST_DIR, "mcp-app.html");
    let html: string;
    try {
      html = await fs.readFile(htmlPath, "utf-8");
    } catch {
      throw new Error(
        `UI bundle not found at ${htmlPath}. Run "npm run build" first.`,
      );
    }
    return {
      contents: [{ uri: RESOURCE_URI, mimeType: RESOURCE_MIME_TYPE, text: html }],
    };
  },
);

// ── HTTP server ───────────────────────────────────────────────────────────────

const app = express();
app.use(cors());
app.use(express.json({ limit: "10mb" }));

// Health check
app.get("/health", (_req, res) => {
  res.json({ status: "ok", server: "eagle-excalidraw-mcp-app" });
});

// MCP endpoint — each request creates a fresh stateless transport
app.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  res.on("close", () => transport.close());
  await mcpServer.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

app.listen(PORT, () => {
  console.log(`\n🎨 Excalidraw MCP App server`);
  console.log(`   MCP endpoint : http://localhost:${PORT}/mcp`);
  console.log(`   Health check : http://localhost:${PORT}/health`);
  console.log(`   UI bundle    : ${DIST_DIR}/mcp-app.html\n`);
});
