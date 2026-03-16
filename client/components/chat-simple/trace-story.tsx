'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  GitBranch, RefreshCw, ChevronDown, ChevronRight,
  Cpu, BarChart2, AlertCircle, Wrench, ArrowRight, ExternalLink,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface InternalTool {
  name: string;
  input: Record<string, unknown>;
  output_preview: string | Record<string, unknown>;
}

interface ToolDetail {
  name: string;
  input: Record<string, unknown>;
  output_preview?: string | Record<string, unknown>;
}

interface SubagentStory {
  name: string;
  observation_id?: string;
  input_query: string;
  input_tokens: number;
  output_tokens: number;
  response_preview: string;
  response_full?: string;
  internal_tools: InternalTool[];
}

interface TurnStory {
  turn: number;
  observation_id?: string;
  input_tokens: number;
  output_tokens: number;
  tool_calls: string[];
  tool_details?: ToolDetail[];
  has_reasoning: boolean;
  response_preview: string;
  response_full?: string;
  subagents: SubagentStory[];
}

interface TraceStory {
  trace_id: string;
  session_id: string;
  timestamp: string;
  langfuse_url?: string;
  total_observations: number;
  supervisor_turns: number;
  total_tokens: {
    supervisor: { input: number; output: number };
    subagents: { input: number; output: number };
    combined: { input: number; output: number };
  };
  story: TurnStory[];
}

interface TraceStoryProps {
  sessionId?: string;
}

// ---------------------------------------------------------------------------
// SubagentCard — expandable subagent with input query + internal tool calls
// ---------------------------------------------------------------------------

function SubagentCard({ sub }: { sub: SubagentStory }) {
  const [open, setOpen] = useState(false);
  const hasDetail = !!sub.input_query || !!sub.response_preview || sub.internal_tools.length > 0;

  return (
    <div className="rounded-md border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => hasDetail && setOpen(v => !v)}
        disabled={!hasDetail}
        className="w-full flex items-center gap-2 px-2.5 py-2 text-left hover:bg-gray-50 transition disabled:cursor-default"
      >
        {hasDetail ? (
          open
            ? <ChevronDown className="w-3 h-3 text-gray-400 shrink-0" />
            : <ChevronRight className="w-3 h-3 text-gray-400 shrink-0" />
        ) : (
          <span className="w-3 h-3 shrink-0" />
        )}
        <Cpu className="w-3 h-3 text-violet-500 shrink-0" />
        <span className="text-[10px] font-semibold text-gray-700 flex-1">{sub.name}</span>
        {sub.internal_tools.length > 0 && (
          <span className="text-[8px] text-gray-400 shrink-0">
            {sub.internal_tools.length} tool{sub.internal_tools.length !== 1 ? 's' : ''}
          </span>
        )}
        <span className="text-[9px] text-gray-400 font-mono shrink-0 tabular-nums">
          {sub.input_tokens.toLocaleString()}↑ {sub.output_tokens.toLocaleString()}↓
        </span>
      </button>

      {open && hasDetail && (
        <div className="border-t border-gray-100 bg-gray-50/40 px-2.5 py-2 space-y-2">
          {/* Input query */}
          {sub.input_query && (
            <div>
              <span className="text-[8px] font-bold text-blue-500 uppercase tracking-wider block mb-0.5">
                Input
              </span>
              <p className="text-[10px] text-gray-700 bg-blue-50 border border-blue-100 rounded px-2 py-1.5 leading-relaxed">
                {sub.input_query}
              </p>
            </div>
          )}

          {/* Internal tool calls */}
          {sub.internal_tools.length > 0 && (
            <div>
              <span className="text-[8px] font-bold text-amber-600 uppercase tracking-wider block mb-1">
                Tool calls ({sub.internal_tools.length})
              </span>
              <div className="space-y-1">
                {sub.internal_tools.map((tool, i) => (
                  <InternalToolRow key={i} tool={tool} />
                ))}
              </div>
            </div>
          )}

          {/* Response preview */}
          {sub.response_preview && (
            <div>
              <span className="text-[8px] font-bold text-green-600 uppercase tracking-wider block mb-0.5">
                Response
              </span>
              <p className="text-[10px] text-gray-600 leading-relaxed italic line-clamp-4">
                {sub.response_preview}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InternalToolRow — a single tool call inside a subagent
// ---------------------------------------------------------------------------

function InternalToolRow({ tool }: { tool: InternalTool }) {
  const [open, setOpen] = useState(false);

  const inputSummary = (() => {
    if (!tool.input || typeof tool.input !== 'object') return '';
    const val = tool.input.query ?? tool.input.key ?? tool.input.s3_key ?? Object.values(tool.input)[0];
    const s = String(val ?? '');
    return s.length > 60 ? s.slice(0, 59) + '…' : s;
  })();

  return (
    <div className="rounded border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-left hover:bg-gray-50 transition"
      >
        {open
          ? <ChevronDown className="w-2.5 h-2.5 text-gray-400 shrink-0" />
          : <ChevronRight className="w-2.5 h-2.5 text-gray-400 shrink-0" />
        }
        <Wrench className="w-2.5 h-2.5 text-amber-500 shrink-0" />
        <span className="text-[9px] font-bold text-gray-600 shrink-0">{tool.name}</span>
        {inputSummary && (
          <span className="text-[9px] text-gray-400 truncate flex-1 min-w-0">{inputSummary}</span>
        )}
      </button>
      {open && (
        <div className="border-t border-gray-100 px-2 py-1.5 space-y-1.5 bg-gray-50/50">
          {tool.input && Object.keys(tool.input).length > 0 && (
            <div>
              <span className="text-[8px] font-bold text-blue-500 uppercase block mb-0.5">Input</span>
              <pre className="text-[9px] font-mono text-gray-600 whitespace-pre-wrap break-all bg-blue-50 border border-blue-100 rounded px-1.5 py-1">
                {JSON.stringify(tool.input, null, 2).slice(0, 600)}
              </pre>
            </div>
          )}
          {tool.output_preview && (
            <div>
              <span className="text-[8px] font-bold text-green-600 uppercase block mb-0.5">Output</span>
              <pre className="text-[9px] font-mono text-gray-600 whitespace-pre-wrap break-all bg-green-50 border border-green-100 rounded px-1.5 py-1">
                {typeof tool.output_preview === 'string'
                  ? tool.output_preview.slice(0, 400)
                  : JSON.stringify(tool.output_preview, null, 2).slice(0, 400)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TurnCard — expandable supervisor turn with subagent breakdown
// ---------------------------------------------------------------------------

function ToolDetailCard({ tool }: { tool: ToolDetail }) {
  const [open, setOpen] = useState(false);

  const inputSummary = (() => {
    if (!tool.input || typeof tool.input !== 'object') return '';
    const val = tool.input.query ?? tool.input.keyword ?? tool.input.key ?? Object.values(tool.input)[0];
    const s = String(val ?? '');
    return s.length > 80 ? s.slice(0, 79) + '…' : s;
  })();

  return (
    <div className="rounded border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-1.5 px-2 py-1.5 text-left hover:bg-gray-50 transition"
      >
        {open
          ? <ChevronDown className="w-2.5 h-2.5 text-gray-400 shrink-0" />
          : <ChevronRight className="w-2.5 h-2.5 text-gray-400 shrink-0" />
        }
        <Wrench className="w-2.5 h-2.5 text-violet-500 shrink-0" />
        <span className="text-[9px] font-bold text-gray-600 shrink-0">{tool.name}</span>
        {inputSummary && (
          <span className="text-[9px] text-gray-400 truncate flex-1 min-w-0">{inputSummary}</span>
        )}
      </button>
      {open && (
        <div className="border-t border-gray-100 px-2 py-1.5 space-y-1.5 bg-gray-50/50">
          {tool.input && Object.keys(tool.input).length > 0 && (
            <div>
              <span className="text-[8px] font-bold text-blue-500 uppercase block mb-0.5">Input</span>
              <pre className="text-[9px] font-mono text-gray-600 whitespace-pre-wrap break-all bg-blue-50 border border-blue-100 rounded px-1.5 py-1 max-h-40 overflow-auto">
                {JSON.stringify(tool.input, null, 2).slice(0, 800)}
              </pre>
            </div>
          )}
          {tool.output_preview && (
            <div>
              <span className="text-[8px] font-bold text-green-600 uppercase block mb-0.5">Output</span>
              <pre className="text-[9px] font-mono text-gray-600 whitespace-pre-wrap break-all bg-green-50 border border-green-100 rounded px-1.5 py-1 max-h-40 overflow-auto">
                {typeof tool.output_preview === 'string'
                  ? tool.output_preview.slice(0, 600)
                  : JSON.stringify(tool.output_preview, null, 2).slice(0, 600)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function TurnCard({ turn, traceId, langfuseUrl }: { turn: TurnStory; traceId?: string; langfuseUrl?: string }) {
  const [open, setOpen] = useState(false);
  const hasSubagents = turn.subagents.length > 0;
  const hasToolDetails = (turn.tool_details?.length ?? 0) > 0;
  const hasDetail = hasSubagents || hasToolDetails || !!turn.response_preview;

  // Deep link: Langfuse supports ?observation=<id> to highlight a specific span
  const turnLangfuseUrl = langfuseUrl && turn.observation_id
    ? `${langfuseUrl}?observation=${turn.observation_id}`
    : undefined;

  return (
    <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
      <button
        onClick={() => hasDetail && setOpen(v => !v)}
        disabled={!hasDetail}
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-gray-50 transition disabled:cursor-default"
      >
        {hasDetail ? (
          open
            ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            : <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        ) : (
          <span className="w-3.5 h-3.5 shrink-0" />
        )}

        <span className="text-[10px] font-bold text-gray-500 uppercase shrink-0">
          Turn {turn.turn}
        </span>

        {turn.tool_calls.length > 0 ? (
          <div className="flex gap-1 flex-wrap flex-1 min-w-0">
            {turn.tool_calls.map((name, i) => (
              <span
                key={i}
                className="px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 text-[8px] font-bold uppercase"
              >
                {name}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-[10px] text-gray-400 flex-1 truncate min-w-0">
            {turn.response_preview.slice(0, 60)}
          </span>
        )}

        {turn.has_reasoning && (
          <span className="text-[8px] px-1 py-0.5 rounded bg-purple-100 text-purple-700 shrink-0 font-bold">
            reasoning
          </span>
        )}

        <span className="text-[9px] text-gray-400 shrink-0 font-mono tabular-nums">
          {turn.input_tokens.toLocaleString()}↑ {turn.output_tokens.toLocaleString()}↓
        </span>
      </button>

      {open && hasDetail && (
        <div className="border-t border-gray-100 px-3 py-2.5 space-y-2.5 bg-gray-50/30">
          {/* Tool call details */}
          {hasToolDetails && (
            <div className="space-y-1.5">
              <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider block">
                Tool calls ({turn.tool_details!.length})
              </span>
              {turn.tool_details!.map((td, i) => (
                <ToolDetailCard key={i} tool={td} />
              ))}
            </div>
          )}

          {/* Subagents */}
          {hasSubagents && (
            <div className="space-y-1.5">
              <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider block">
                Subagents ({turn.subagents.length})
              </span>
              {turn.subagents.map((sub, i) => (
                <SubagentCard key={i} sub={sub} />
              ))}
            </div>
          )}

          {/* Response */}
          {(turn.response_full || turn.response_preview) && (
            <div>
              <span className="text-[8px] font-bold text-green-600 uppercase tracking-wider block mb-0.5">
                {hasSubagents ? 'Synthesis' : 'Response'}
              </span>
              <p className="text-[10px] text-gray-600 leading-relaxed italic max-h-48 overflow-auto">
                &ldquo;{turn.response_full || turn.response_preview}&rdquo;
              </p>
            </div>
          )}

          {/* Deep link to Langfuse */}
          {turnLangfuseUrl && (
            <a
              href={turnLangfuseUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[9px] text-blue-500 hover:text-blue-700 transition"
            >
              <ExternalLink className="w-2.5 h-2.5" />
              View full trace in Langfuse
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function TraceStory({ sessionId }: TraceStoryProps) {
  const [story, setStory] = useState<TraceStory | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastFetched, setLastFetched] = useState<Date | null>(null);

  const fetchStory = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setErrorCode(null);
    setErrorMsg(null);
    try {
      const res = await fetch(
        `/api/traces/story?session_id=${encodeURIComponent(sessionId)}`,
      );
      if (res.status === 503) { setErrorCode('not_configured'); return; }
      if (res.status === 404) { setErrorCode('no_traces'); return; }
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        setErrorMsg(`${res.status}: ${text.slice(0, 200)}`);
        return;
      }
      const data: TraceStory = await res.json();
      setStory(data);
      setLastFetched(new Date());
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to fetch trace');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { fetchStory(); }, [fetchStory]);

  // ── No session ──────────────────────────────────────────────────────────
  if (!sessionId) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <GitBranch className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No session selected.</p>
        <p className="text-xs text-gray-400 mt-1">Start a conversation to see traces.</p>
      </div>
    );
  }

  // ── Langfuse not configured ─────────────────────────────────────────────
  if (errorCode === 'not_configured') {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center mb-3">
          <GitBranch className="w-5 h-5 text-amber-500" />
        </div>
        <p className="text-sm font-medium text-gray-700">Langfuse not configured</p>
        <p className="text-xs text-gray-400 mt-1 max-w-xs">
          Set <code className="bg-gray-100 px-1 rounded text-[10px]">LANGFUSE_PUBLIC_KEY</code> and{' '}
          <code className="bg-gray-100 px-1 rounded text-[10px]">LANGFUSE_SECRET_KEY</code> in the server environment.
        </p>
      </div>
    );
  }

  // ── No traces yet ───────────────────────────────────────────────────────
  if (errorCode === 'no_traces') {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <GitBranch className="w-5 h-5 text-gray-300 mb-2" />
        <p className="text-sm text-gray-500">No traces yet for this session.</p>
        <p className="text-xs text-gray-400 mt-1">
          Traces appear after the first agent response.
        </p>
        <button
          onClick={fetchStory}
          className="mt-3 text-[10px] text-blue-600 hover:text-blue-800 font-medium"
        >
          Refresh
        </button>
      </div>
    );
  }

  return (
    <>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] text-gray-500 flex items-center gap-2">
          {story && (
            <>
              <span>{story.supervisor_turns} turn{story.supervisor_turns !== 1 ? 's' : ''}</span>
              <span className="text-gray-300">·</span>
              <span className="font-mono">
                {story.total_tokens.combined.input.toLocaleString()}↑{' '}
                {story.total_tokens.combined.output.toLocaleString()}↓
              </span>
            </>
          )}
          {lastFetched && (
            <>
              <span className="text-gray-300">·</span>
              <span>
                {lastFetched.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          {story?.langfuse_url && (
            <a
              href={story.langfuse_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-800 transition"
            >
              <ExternalLink className="w-3 h-3" />
              Langfuse
            </a>
          )}
          <button
            onClick={fetchStory}
            disabled={loading}
            className="flex items-center gap-1 text-[10px] text-blue-600 hover:text-blue-800 disabled:opacity-40 transition"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Generic error */}
      {errorMsg && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs mb-3">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {errorMsg}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !story && (
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-10 rounded-lg bg-gray-100 animate-pulse" />
          ))}
        </div>
      )}

      {/* Story */}
      {story && (
        <div className="space-y-1.5">
          {/* Token summary */}
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 mb-2">
            <BarChart2 className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            <div className="flex gap-4 text-[9px] font-mono text-gray-500">
              <span>
                supervisor:{' '}
                {story.total_tokens.supervisor.input.toLocaleString()}↑{' '}
                {story.total_tokens.supervisor.output.toLocaleString()}↓
              </span>
              <span>
                subagents:{' '}
                {story.total_tokens.subagents.input.toLocaleString()}↑{' '}
                {story.total_tokens.subagents.output.toLocaleString()}↓
              </span>
            </div>
          </div>

          {story.story.map(turn => (
            <TurnCard
              key={turn.turn}
              turn={turn}
              traceId={story.trace_id}
              langfuseUrl={story.langfuse_url}
            />
          ))}
        </div>
      )}
    </>
  );
}
