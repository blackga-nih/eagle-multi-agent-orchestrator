/**
 * Excalidraw MCP App UI
 *
 * Receives diagram data from the host via MCP tool results,
 * renders an interactive Excalidraw canvas, and lets admins
 * edit diagrams live inside the EAGLE chat interface.
 */
import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Excalidraw, exportToBlob } from "@excalidraw/excalidraw";
import { useApp, useHostStyles } from "@modelcontextprotocol/ext-apps/react";
import type {
  ExcalidrawImperativeAPI,
  ExcalidrawInitialDataState,
} from "@excalidraw/excalidraw/types";
import type { McpUiHostContext } from "@modelcontextprotocol/ext-apps";

// ── types ─────────────────────────────────────────────────────────────────────

interface DiagramPayload {
  title: string;
  elements: ExcalidrawInitialDataState["elements"];
  appState?: Partial<ExcalidrawInitialDataState["appState"]>;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function parseDiagramPayload(text: string): DiagramPayload | null {
  try {
    const data = JSON.parse(text);
    if (typeof data === "object" && data !== null) {
      return {
        title: (data.title as string) ?? "Diagram",
        elements: (data.elements as ExcalidrawInitialDataState["elements"]) ?? [],
        appState: (data.appState as Partial<ExcalidrawInitialDataState["appState"]>) ?? {},
      };
    }
  } catch {
    // not JSON — ignore
  }
  return null;
}

// ── toolbar button ────────────────────────────────────────────────────────────

interface ToolbarButtonProps {
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}

function ToolbarButton({ onClick, title, children }: ToolbarButtonProps) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        padding: "4px 10px",
        borderRadius: 6,
        border: "1px solid #d0d7de",
        background: "#f6f8fa",
        cursor: "pointer",
        fontSize: 12,
        display: "flex",
        alignItems: "center",
        gap: 4,
        color: "#24292f",
      }}
    >
      {children}
    </button>
  );
}

// ── main component ────────────────────────────────────────────────────────────

function ExcalidrawMcpApp() {
  const [diagram, setDiagram] = useState<DiagramPayload>({
    title: "New Diagram",
    elements: [],
    appState: { viewBackgroundColor: "#ffffff" },
  });
  const [excalidrawApi, setExcalidrawApi] = useState<ExcalidrawImperativeAPI | null>(null);
  const [hostCtx, setHostCtx] = useState<McpUiHostContext | undefined>();
  const [exportStatus, setExportStatus] = useState<string | null>(null);

  // ── MCP App lifecycle ──────────────────────────────────────────────────────

  const { app, error } = useApp({
    appInfo: { name: "EAGLE Excalidraw", version: "1.0.0" },
    capabilities: {},
    onAppCreated: (a) => {
      // Receive diagram data from tool result (create_diagram or reset_diagram)
      a.ontoolresult = async (result) => {
        const textItem = result.content?.find((c) => c.type === "text");
        if (!textItem || textItem.type !== "text") return;
        const payload = parseDiagramPayload(textItem.text);
        if (payload) {
          setDiagram(payload);
        }
      };

      // Keep host context (theme, safe area, display mode)
      a.onhostcontextchanged = (ctx) => {
        setHostCtx((prev) => ({ ...prev, ...ctx }));
      };

      a.onteardown = async () => ({});
    },
  });

  // Apply host theme / fonts to the document
  useHostStyles(app);

  // Sync new diagram data into the live Excalidraw canvas
  useEffect(() => {
    if (!excalidrawApi || !diagram.elements) return;
    excalidrawApi.updateScene({
      elements: diagram.elements as Parameters<ExcalidrawImperativeAPI["updateScene"]>[0]["elements"],
      appState: {
        viewBackgroundColor: "#ffffff",
        ...(diagram.appState ?? {}),
      },
    });
    excalidrawApi.scrollToContent();
  }, [diagram, excalidrawApi]);

  // ── actions ────────────────────────────────────────────────────────────────

  const handleClear = useCallback(async () => {
    if (!app) return;
    await app.callServerTool({ name: "reset_diagram", arguments: {} });
  }, [app]);

  const handleExportPng = useCallback(async () => {
    if (!excalidrawApi) return;
    setExportStatus("Exporting…");
    try {
      const blob = await exportToBlob({
        elements: excalidrawApi.getSceneElements(),
        appState: excalidrawApi.getAppState(),
        files: excalidrawApi.getFiles(),
        mimeType: "image/png",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${diagram.title.replace(/\s+/g, "-")}.png`;
      a.click();
      URL.revokeObjectURL(url);
      setExportStatus("Exported!");
      setTimeout(() => setExportStatus(null), 2000);
    } catch (e) {
      setExportStatus("Export failed");
      console.error(e);
    }
  }, [excalidrawApi, diagram.title]);

  const handleSendToChat = useCallback(async () => {
    if (!app || !excalidrawApi) return;
    const elements = excalidrawApi.getSceneElements();
    const summary = `I've updated the diagram "${diagram.title}" with ${elements.length} element(s). The canvas now contains: ${elements.map((e) => e.type).join(", ")}.`;
    await app.sendMessage({
      role: "user",
      content: [{ type: "text", text: summary }],
    });
  }, [app, excalidrawApi, diagram.title]);

  // ── render ─────────────────────────────────────────────────────────────────

  if (error) {
    return (
      <div style={{ padding: 16, color: "red" }}>
        <strong>MCP App connection error:</strong> {error.message}
      </div>
    );
  }

  const safeArea = hostCtx?.safeAreaInsets ?? {};

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100%",
        height: "100%",
        paddingTop: (safeArea as { top?: number }).top ?? 0,
        paddingRight: (safeArea as { right?: number }).right ?? 0,
        paddingBottom: (safeArea as { bottom?: number }).bottom ?? 0,
        paddingLeft: (safeArea as { left?: number }).left ?? 0,
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "6px 12px",
          borderBottom: "1px solid #d0d7de",
          background: "#f6f8fa",
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13, color: "#003366", marginRight: 8 }}>
          🎨 {diagram.title}
        </span>

        <ToolbarButton onClick={handleClear} title="Clear canvas">
          🗑 Clear
        </ToolbarButton>

        <ToolbarButton onClick={handleExportPng} title="Export as PNG">
          ⬇ Export PNG
        </ToolbarButton>

        <ToolbarButton onClick={handleSendToChat} title="Send diagram summary to chat">
          💬 Send to Chat
        </ToolbarButton>

        {exportStatus && (
          <span style={{ fontSize: 12, color: "#57606a", marginLeft: 4 }}>
            {exportStatus}
          </span>
        )}
      </div>

      {/* Excalidraw canvas */}
      <div style={{ flex: 1, position: "relative" }}>
        <Excalidraw
          excalidrawAPI={(api) => setExcalidrawApi(api)}
          initialData={{
            elements: diagram.elements ?? [],
            appState: {
              viewBackgroundColor: "#ffffff",
              ...(diagram.appState ?? {}),
            },
          }}
          UIOptions={{
            canvasActions: {
              export: { saveFileToDisk: true },
            },
          }}
        />
      </div>
    </div>
  );
}

// ── bootstrap ─────────────────────────────────────────────────────────────────

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ExcalidrawMcpApp />
  </React.StrictMode>,
);
