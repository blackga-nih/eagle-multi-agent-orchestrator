'use client';

/**
 * Admin Diagrams — AI-powered Excalidraw canvas in the EAGLE admin interface.
 *
 * Split layout:
 *   Left  — AI chat panel (calls /api/diagrams which injects Excalidraw system prompt)
 *   Right — Live Excalidraw canvas populated from Claude's JSON output
 *
 * How diagram rendering works:
 *   1. Admin asks Claude to draw something.
 *   2. The /api/diagrams route injects an Excalidraw-specific system prompt.
 *   3. Claude responds with explanation text + a ```json code block.
 *   4. When streaming completes the frontend parses the JSON block and
 *      loads the Excalidraw elements into the live canvas.
 *
 * Additionally, if the backend returns a tool_result for "create_diagram"
 * (future: once the EAGLE FastAPI tool is wired), that is also handled.
 */

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useCallback, useRef, useState } from 'react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';
import type { ExcalidrawCanvasRef, DiagramElement } from '@/components/diagrams/ExcalidrawCanvas';
import { ChevronLeft, Trash2, Download, Send, Loader2, PenTool } from 'lucide-react';

// Excalidraw is browser-only — disable SSR
const ExcalidrawCanvas = dynamic(
  () => import('@/components/diagrams/ExcalidrawCanvas'),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm bg-gray-50">
        Loading canvas…
      </div>
    ),
  },
);

// ── types ─────────────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

// ── diagram JSON parser ───────────────────────────────────────────────────────

/**
 * Extract Excalidraw elements from a ```json code block in the assistant text.
 * Returns null if no valid array is found.
 */
function extractDiagramElements(text: string): DiagramElement[] | null {
  const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[1].trim());
    if (Array.isArray(parsed) && parsed.length > 0 && parsed[0].type) {
      return parsed as DiagramElement[];
    }
  } catch {
    // not valid JSON
  }
  return null;
}

/**
 * Derive a diagram title from the assistant text or the user prompt.
 */
function deriveDiagramTitle(text: string, userPrompt: string): string {
  const headingMatch = text.match(/^#+\s+(.+)/m) || text.match(/^([A-Z][^.!?\n]{5,60})[.!?]?/m);
  if (headingMatch) return headingMatch[1].trim().slice(0, 50);
  const words = userPrompt.split(/\s+/).slice(0, 6).join(' ');
  return words.length > 3 ? words : 'Diagram';
}

// ── sub-components ─────────────────────────────────────────────────────────────

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  // Strip JSON code blocks from display text (they're shown in the canvas instead)
  const displayContent = msg.role === 'assistant'
    ? msg.content.replace(/```(?:json)?[\s\S]*?```/g, '*(Excalidraw diagram rendered in canvas ↗)*')
    : msg.content;

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[90%] rounded-xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
          isUser
            ? 'bg-[#E3F2FD] border border-[#BBDEFB] text-[#1A1A2E] rounded-br-sm'
            : 'bg-white border border-[#E8ECF1] text-[#1A1A2E] rounded-bl-sm'
        }`}
      >
        <div
          className={`text-[11px] font-semibold uppercase tracking-wide mb-1 ${
            isUser ? 'text-[#8896A6] text-right' : 'text-[#003366]'
          }`}
        >
          {isUser ? 'You' : '🦅 EAGLE'}
        </div>
        <p className="whitespace-pre-wrap text-sm">{displayContent}</p>
        {msg.isStreaming && (
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 mt-1">
            <Loader2 className="w-3 h-3 animate-spin" /> Drawing…
          </span>
        )}
      </div>
    </div>
  );
}

// ── suggestion prompts ────────────────────────────────────────────────────────

const SUGGESTIONS = [
  'Draw a system architecture for a microservices app',
  'Create a SOW approval workflow with 6 steps',
  'Diagram the EAGLE multi-agent hierarchy',
  'Show a procurement lifecycle flowchart',
];

// ── main page ──────────────────────────────────────────────────────────────────

export default function DiagramsPage() {
  const { getToken } = useAuth();
  const { currentSessionId } = useSession();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [canvasTitle, setCanvasTitle] = useState<string | undefined>(undefined);
  const [elementCount, setElementCount] = useState(0);
  const [status, setStatus] = useState<{ text: string; type: 'ok' | 'err' } | null>(null);

  const canvasRef = useRef<ExcalidrawCanvasRef>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingIdRef = useRef<string | null>(null);
  const accumulatedRef = useRef<string>('');

  // ── show a status badge ───────────────────────────────────────────────────

  const showStatus = (text: string, type: 'ok' | 'err' = 'ok') => {
    setStatus({ text, type });
    setTimeout(() => setStatus(null), 3500);
  };

  // ── load elements into canvas ─────────────────────────────────────────────

  const loadDiagram = useCallback(
    (elements: DiagramElement[], title: string) => {
      setCanvasTitle(title);
      canvasRef.current?.loadElements(elements);
      showStatus(`✅ Loaded "${title}" — ${elements.length} elements`);
    },
    [],
  );

  // ── send ───────────────────────────────────────────────────────────────────

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    const lastUserPrompt = text;
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsStreaming(true);
    streamingIdRef.current = null;
    accumulatedRef.current = '';

    try {
      const token = await getToken?.();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const resp = await fetch('/api/diagrams', {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: text,
          session_id: currentSessionId ?? crypto.randomUUID(),
        }),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`API error ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let event: Record<string, unknown>;
          try {
            event = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          const type = event.type as string;

          if (type === 'text' && typeof event.content === 'string') {
            accumulatedRef.current += event.content;
            setMessages((prev) => {
              const sid = streamingIdRef.current;
              if (sid) {
                return prev.map((m) =>
                  m.id === sid
                    ? { ...m, content: (m.content ?? '') + (event.content as string) }
                    : m,
                );
              }
              const newId = crypto.randomUUID();
              streamingIdRef.current = newId;
              return [
                ...prev,
                {
                  id: newId,
                  role: 'assistant',
                  content: event.content as string,
                  isStreaming: true,
                },
              ];
            });
          }

          if (type === 'complete') {
            // Mark streaming done
            setMessages((prev) =>
              prev.map((m) =>
                m.id === streamingIdRef.current ? { ...m, isStreaming: false } : m,
              ),
            );
            streamingIdRef.current = null;
            setIsStreaming(false);

            // Parse diagram JSON from accumulated text
            const elements = extractDiagramElements(accumulatedRef.current);
            if (elements) {
              const title = deriveDiagramTitle(accumulatedRef.current, lastUserPrompt);
              loadDiagram(elements, title);
            }
          }

          // Also handle explicit tool_result for create_diagram (future)
          if (
            type === 'tool_result' &&
            (event.tool_result as { name?: string })?.name === 'create_diagram'
          ) {
            try {
              const raw = (event.tool_result as { result: unknown }).result;
              const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
              if (data?.elements) {
                loadDiagram(data.elements as DiagramElement[], data.title ?? 'Diagram');
              }
            } catch {
              // ignore parse error
            }
          }
        }
      }
    } catch (err) {
      showStatus('⚠️ Error connecting to backend', 'err');
      console.error('Diagram request error:', err);
    } finally {
      setIsStreaming(false);
      setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, [input, isStreaming, getToken, currentSessionId, loadDiagram]);

  // ── export ─────────────────────────────────────────────────────────────────

  const handleExport = useCallback(async () => {
    const blob = await canvasRef.current?.exportPng();
    if (!blob) {
      showStatus('⚠️ Nothing to export yet', 'err');
      return;
    }
    const name = (canvasTitle ?? 'diagram').replace(/\s+/g, '-');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.png`;
    a.click();
    URL.revokeObjectURL(url);
    showStatus('✅ Exported!');
  }, [canvasTitle]);

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen overflow-hidden bg-[#F5F7FA]">
        <TopNav />

        {/* Page header */}
        <div className="flex items-center justify-between px-6 py-3 bg-white border-b border-[#E8ECF1] flex-shrink-0">
          <div className="flex items-center gap-3">
            <Link
              href="/admin"
              className="text-gray-400 hover:text-[#003366] transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-base font-bold text-[#003366] flex items-center gap-2">
                <PenTool className="w-4 h-4" /> AI Diagram Studio
              </h1>
              <p className="text-[11px] text-gray-400">
                Ask Claude to draw — edits render live in Excalidraw
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {status && (
              <span
                className={`text-xs rounded-full px-3 py-1 border ${
                  status.type === 'ok'
                    ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                    : 'text-red-700 bg-red-50 border-red-200'
                }`}
              >
                {status.text}
              </span>
            )}
            <button
              onClick={() => { canvasRef.current?.clearCanvas(); setCanvasTitle(undefined); setElementCount(0); }}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" /> Clear
            </button>
            <button
              onClick={handleExport}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-[#003366] text-[#003366] bg-white hover:bg-[#E3F2FD] transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> Export PNG
            </button>
          </div>
        </div>

        {/* Main split layout */}
        <div className="flex flex-1 min-h-0 overflow-hidden">

          {/* ── Left: AI Chat panel ────────────────────────────────── */}
          <div className="w-[360px] flex-shrink-0 flex flex-col border-r border-[#E8ECF1] bg-white">
            <div className="px-4 py-2.5 border-b border-[#E8ECF1] bg-[#F8FAFC] flex-shrink-0">
              <p className="text-[11px] font-semibold text-[#003366] uppercase tracking-wide">
                AI Chat
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                Describe a diagram — Claude draws it for you
              </p>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4">
              {messages.length === 0 ? (
                <div className="space-y-2">
                  <p className="text-[11px] text-gray-400 text-center mb-3">
                    Try one of these…
                  </p>
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => setInput(s)}
                      className="w-full text-left text-xs p-3 rounded-lg border border-[#E8ECF1] bg-[#F8FAFC] hover:bg-[#E3F2FD] hover:border-[#BBDEFB] transition-colors text-gray-600"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              ) : (
                messages.map((msg) => <ChatBubble key={msg.id} msg={msg} />)
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="p-3 border-t border-[#E8ECF1] flex-shrink-0">
              <div className="flex gap-2 items-end">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  placeholder="Describe a diagram…"
                  rows={2}
                  className="flex-1 resize-none rounded-lg border border-[#D0D7DE] bg-white px-3 py-2 text-sm text-[#1A1A2E] placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-[#003366]/20 focus:border-[#003366]"
                  disabled={isStreaming}
                />
                <button
                  onClick={handleSend}
                  disabled={isStreaming || !input.trim()}
                  className="p-2.5 rounded-lg bg-[#003366] text-white hover:bg-[#002244] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {isStreaming
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Send className="w-4 h-4" />
                  }
                </button>
              </div>
            </div>
          </div>

          {/* ── Right: Excalidraw Canvas ───────────────────────────── */}
          <div className="flex-1 flex flex-col min-w-0">
            <div className="px-4 py-2.5 border-b border-[#E8ECF1] bg-[#F8FAFC] flex items-center justify-between flex-shrink-0">
              <p className="text-[11px] font-semibold text-[#003366] uppercase tracking-wide">
                {canvasTitle ? `Canvas — ${canvasTitle}` : 'Canvas'}
              </p>
              <p className="text-[10px] text-gray-400">
                {elementCount > 0
                  ? `${elementCount} element${elementCount !== 1 ? 's' : ''} · draw & edit freely`
                  : 'Ask Claude to draw a diagram'}
              </p>
            </div>

            <div className="flex-1 min-h-0">
              <ExcalidrawCanvas
                ref={canvasRef}
                title={canvasTitle}
                onElementsChanged={setElementCount}
              />
            </div>
          </div>
        </div>
      </div>
    </AuthGuard>
  );
}
