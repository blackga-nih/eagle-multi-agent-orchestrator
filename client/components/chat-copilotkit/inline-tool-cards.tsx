'use client';

import { useState, useMemo } from 'react';
import { marked } from 'marked';
import { getToolMeta, SUBAGENT_TOOLS } from './tool-meta';
import type { AGUILogEntry } from './agui-activity-log';

// ---------------------------------------------------------------------------
// Tracked tool call — built from AG-UI events
// ---------------------------------------------------------------------------

interface TrackedToolCall {
  toolCallId: string;
  toolName: string;
  args: string;
  result: string | null;
  status: 'running' | 'done';
}

/** Build tracked tool calls from raw AG-UI events. */
function buildToolCalls(events: AGUILogEntry[]): TrackedToolCall[] {
  const map = new Map<string, TrackedToolCall>();
  const order: string[] = [];

  for (const entry of events) {
    const e = entry.event;

    if (e.type === 'TOOL_CALL_START' && e.toolCallId) {
      const id = e.toolCallId as string;
      if (!map.has(id)) order.push(id);
      map.set(id, {
        toolCallId: id,
        toolName: (e.toolCallName as string) ?? 'unknown',
        args: '',
        result: null,
        status: 'running',
      });
    }

    if (e.type === 'TOOL_CALL_ARGS' && e.toolCallId) {
      const tc = map.get(e.toolCallId as string);
      if (tc) tc.args += (e.delta as string) ?? '';
    }

    if (e.type === 'TOOL_CALL_RESULT' && e.toolCallId) {
      const tc = map.get(e.toolCallId as string);
      if (tc) tc.result = (e.result as string) ?? '';
    }

    if (e.type === 'TOOL_CALL_END' && e.toolCallId) {
      const tc = map.get(e.toolCallId as string);
      if (tc) tc.status = 'done';
    }
  }

  return order.map((id) => map.get(id)!).filter(Boolean);
}

// ---------------------------------------------------------------------------
// Tracked steps (subagent delegations)
// ---------------------------------------------------------------------------

interface TrackedStep {
  name: string;
  status: 'running' | 'done';
}

function buildSteps(events: AGUILogEntry[]): TrackedStep[] {
  const map = new Map<string, TrackedStep>();
  const order: string[] = [];

  for (const entry of events) {
    const e = entry.event;
    if (e.type === 'STEP_STARTED' && e.stepName) {
      const name = e.stepName as string;
      if (!map.has(name)) order.push(name);
      map.set(name, { name, status: 'running' });
    }
    if (e.type === 'STEP_FINISHED' && e.stepName) {
      const step = map.get(e.stepName as string);
      if (step) step.status = 'done';
    }
  }

  return order.map((n) => map.get(n)!).filter(Boolean);
}

// ---------------------------------------------------------------------------
// File references — extracted from tool results
// ---------------------------------------------------------------------------

interface FileRef {
  path: string;
  filename: string;
  charCount: number;
  content: string;
}

function extractFileRefs(toolCalls: TrackedToolCall[]): FileRef[] {
  const refs: FileRef[] = [];

  for (const tc of toolCalls) {
    if (tc.status !== 'done' || !tc.result) continue;

    // s3_document_ops read results
    if (tc.toolName === 's3_document_ops') {
      let parsedArgs: Record<string, unknown> = {};
      try {
        parsedArgs = JSON.parse(tc.args);
      } catch {
        /* skip */
      }
      const op = String(parsedArgs.operation ?? '');
      const key = String(parsedArgs.key ?? '');
      if ((op === 'read' || op === 'get') && key && tc.result.length > 0) {
        refs.push({
          path: key,
          filename: key.split('/').pop() || key,
          charCount: tc.result.length,
          content: tc.result,
        });
      }
      continue;
    }

    // Subagent results that mention file paths (e.g. "legal-counselor/...")
    if (SUBAGENT_TOOLS.has(tc.toolName) && tc.result) {
      const filePathRegex = /([a-zA-Z_-]+\/[a-zA-Z_/-]+\.\w{2,4})\n(\d+)\s*chars?/g;
      let match;
      while ((match = filePathRegex.exec(tc.result)) !== null) {
        refs.push({
          path: match[1],
          filename: match[1].split('/').pop() || match[1],
          charCount: parseInt(match[2], 10),
          content: '', // Content is inline in the subagent result, not separate
        });
      }
    }
  }

  return refs;
}

// ---------------------------------------------------------------------------
// Summarize tool args
// ---------------------------------------------------------------------------

function summarizeArgs(toolName: string, argsJson: string): string {
  if (!argsJson) return '';
  try {
    const input = JSON.parse(argsJson);
    const query = input.query ?? input.prompt ?? input.message ?? input.action ?? '';
    if (query) {
      const q = String(query);
      return q.length > 100 ? q.slice(0, 100) + '\u2026' : q;
    }
    if (toolName === 's3_document_ops') {
      const op = String(input.operation ?? 'list');
      const key = String(input.key ?? '');
      return key ? `${op}: ${key.split('/').pop()}` : op;
    }
    if (toolName === 'create_document') {
      return String(input.title ?? input.doc_type ?? '');
    }
    return '';
  } catch {
    return argsJson.length > 80 ? argsJson.slice(0, 80) + '\u2026' : argsJson;
  }
}

// ---------------------------------------------------------------------------
// Strip metadata tags from HTML
// ---------------------------------------------------------------------------

function stripMetadata(html: string): string {
  return html.replace(/<metadata[\s\S]*?<\/metadata>/gi, '');
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusIndicator({ status }: { status: 'running' | 'done' }) {
  if (status === 'running') {
    return <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse shrink-0" />;
  }
  return (
    <span className="w-4 h-4 rounded-full bg-green-100 text-green-600 flex items-center justify-center shrink-0 text-[10px]">
      &#10003;
    </span>
  );
}

function ToolCard({ tc }: { tc: TrackedToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const meta = getToolMeta(tc.toolName);
  const summary = summarizeArgs(tc.toolName, tc.args);
  const isSubagent = SUBAGENT_TOOLS.has(tc.toolName);
  const canExpand = tc.status === 'done' && tc.result !== null;

  return (
    <div
      className={`rounded-lg border text-xs overflow-hidden transition-colors ${
        tc.status === 'running' ? 'border-blue-200 bg-blue-50/50' : 'border-[#E5E9F0] bg-[#F8FAFC]'
      }`}
    >
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-black/[0.02] transition-colors"
        onClick={() => canExpand && setExpanded((v) => !v)}
        disabled={!canExpand}
      >
        <span className="text-sm shrink-0 leading-none" role="img" aria-label={meta.label}>
          {meta.icon}
        </span>
        <span className="font-medium text-gray-800 shrink-0">{meta.label}</span>
        {summary && <span className="text-gray-400 truncate min-w-0 flex-1">{summary}</span>}
        {isSubagent && (
          <span className="text-[9px] px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded-full font-bold shrink-0">
            specialist
          </span>
        )}
        <StatusIndicator status={tc.status} />
        {canExpand && (
          <span className={`text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}>
            &#9662;
          </span>
        )}
      </button>

      {expanded && tc.result && (
        <div className="border-t border-[#E5E9F0] bg-white">
          <div className="relative">
            <div className="overflow-y-auto max-h-96 px-4 py-3">
              {isSubagent ? (
                <div
                  className="text-xs text-gray-700 leading-relaxed prose prose-xs max-w-none"
                  dangerouslySetInnerHTML={{
                    __html: stripMetadata(marked.parse(tc.result) as string),
                  }}
                />
              ) : (
                <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap break-all">
                  {tc.result}
                </pre>
              )}
            </div>
            <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent" />
          </div>
        </div>
      )}
    </div>
  );
}

function FileCard({ file }: { file: FileRef }) {
  const [expanded, setExpanded] = useState(false);
  const hasContent = file.content.length > 0;
  const isMarkdown = file.filename.endsWith('.md');

  return (
    <div className="rounded-lg border border-[#E5E9F0] bg-[#F8FAFC] text-xs overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-black/[0.02] transition-colors"
        onClick={() => hasContent && setExpanded((v) => !v)}
        disabled={!hasContent}
      >
        <span className="text-sm shrink-0">{'\u{1F4C4}'}</span>
        <span className="font-mono font-medium text-gray-800 truncate min-w-0 flex-1">
          {file.filename}
        </span>
        <span className="text-[10px] text-gray-400 shrink-0">
          {file.charCount.toLocaleString()} chars
        </span>
        {hasContent && (
          <span className={`text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}>
            &#9662;
          </span>
        )}
      </button>

      {expanded && hasContent && (
        <div className="border-t border-[#E5E9F0] bg-white">
          <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
            <span className="text-[10px] font-mono text-gray-500 truncate">{file.path}</span>
            <span className="text-[10px] text-gray-400 ml-auto shrink-0">
              {file.content.length.toLocaleString()} chars
            </span>
          </div>
          <div className="relative">
            <div className="overflow-y-auto max-h-[600px] px-3 py-2">
              {isMarkdown ? (
                <div
                  className="text-xs text-gray-700 leading-relaxed prose prose-xs max-w-none"
                  dangerouslySetInnerHTML={{
                    __html: stripMetadata(marked.parse(file.content) as string),
                  }}
                />
              ) : (
                <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap break-all">
                  {file.content}
                </pre>
              )}
            </div>
            <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent" />
          </div>
        </div>
      )}
    </div>
  );
}

function StepBadge({ step }: { step: TrackedStep }) {
  const meta = getToolMeta(step.name);
  return (
    <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-50 border border-indigo-200 text-xs">
      <span className="text-sm leading-none">{meta.icon}</span>
      <span className="font-medium text-indigo-800">{meta.label}</span>
      <StatusIndicator status={step.status} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface InlineToolCardsProps {
  events: AGUILogEntry[];
}

export default function InlineToolCards({ events }: InlineToolCardsProps) {
  const toolCalls = useMemo(() => buildToolCalls(events), [events]);
  const steps = useMemo(() => buildSteps(events), [events]);
  const fileRefs = useMemo(() => extractFileRefs(toolCalls), [toolCalls]);

  if (toolCalls.length === 0 && steps.length === 0) return null;

  return (
    <div className="px-4 py-2 space-y-2 border-t border-[#E5E9F0] bg-[#FAFBFC]">
      {/* Subagent delegation badges */}
      {steps.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {steps.map((step) => (
            <StepBadge key={step.name} step={step} />
          ))}
        </div>
      )}

      {/* Tool call cards */}
      {toolCalls.map((tc) => (
        <ToolCard key={tc.toolCallId} tc={tc} />
      ))}

      {/* File reference cards */}
      {fileRefs.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
            Files Referenced
          </span>
          {fileRefs.map((file) => (
            <FileCard key={file.path} file={file} />
          ))}
        </div>
      )}
    </div>
  );
}
