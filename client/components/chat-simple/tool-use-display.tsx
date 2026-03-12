'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ClientToolResult } from '@/lib/client-tools';
import { DocumentInfo } from '@/types/chat';

// ---------------------------------------------------------------------------
// Knowledge Source types (exported for Sources tab)
// ---------------------------------------------------------------------------

export interface KnowledgeSource {
  document_id: string;
  title: string;
  summary?: string;
  document_type?: string;
  primary_topic?: string;
  primary_agent?: string;
  authority_level?: string;
  s3_key?: string;
  confidence_score?: number;
  keywords?: string[];
  /** Which tool found/read this document */
  source_tool: 'knowledge_search' | 'knowledge_fetch' | 'search_far';
  /** Content (for knowledge_fetch results) */
  content?: string;
  truncated?: boolean;
  content_length?: number;
}

export type ToolStatus = 'pending' | 'running' | 'done' | 'error';

interface ToolUseDisplayProps {
  toolName: string;
  input: Record<string, unknown>;
  status: ToolStatus;
  result?: ClientToolResult | null;
  isClientSide?: boolean;
  sessionId?: string;
}

// ── Tool metadata: icon + human-friendly label ──────────────────────

const TOOL_META: Record<string, { icon: string; label: string }> = {
  // Specialist subagents
  oa_intake:            { icon: '📋', label: 'Intake Assessment' },
  legal_counsel:        { icon: '⚖️', label: 'Legal Analysis' },
  market_intelligence:  { icon: '📊', label: 'Market Research' },
  tech_translator:      { icon: '🔧', label: 'Technical Review' },
  tech_review:          { icon: '🔧', label: 'Technical Review' },
  public_interest:      { icon: '🏛️', label: 'Public Interest Review' },
  document_generator:   { icon: '📄', label: 'Generating Document' },
  compliance:           { icon: '✅', label: 'Compliance Check' },
  policy_analyst:       { icon: '📜', label: 'Policy Analysis' },
  policy_librarian:     { icon: '📚', label: 'Policy Lookup' },
  policy_supervisor:    { icon: '👤', label: 'Policy Review' },
  ingest_document:      { icon: '📥', label: 'Document Ingestion' },
  knowledge_retrieval:  { icon: '🔍', label: 'Knowledge Search' },
  // Knowledge base tools
  knowledge_search:     { icon: '🔎', label: 'Searching Knowledge Base' },
  knowledge_fetch:      { icon: '📖', label: 'Reading Document' },
  // Service tools
  s3_document_ops:      { icon: '📁', label: 'Document Storage' },
  dynamodb_intake:      { icon: '🗃️', label: 'Intake Records' },
  create_document:      { icon: '📝', label: 'Creating Document' },
  get_intake_status:    { icon: '📊', label: 'Intake Status' },
  intake_workflow:      { icon: '🔄', label: 'Intake Workflow' },
  search_far:           { icon: '📖', label: 'Searching FAR/DFARS' },
  query_compliance_matrix: { icon: '✅', label: 'Compliance Matrix' },
  // Client-side tools
  think:                { icon: '💭', label: 'Reasoning' },
  code:                 { icon: '💻', label: 'Running Code' },
  editor:               { icon: '✏️', label: 'Editing' },
};

function getToolMeta(toolName: string) {
  return TOOL_META[toolName] ?? { icon: '⚙️', label: toolName.replace(/_/g, ' ') };
}

// ── Input summary ───────────────────────────────────────────────────

function summarizeInput(toolName: string, input: Record<string, unknown>): string {
  if (!input || Object.keys(input).length === 0) return '';

  switch (toolName) {
    case 'think': {
      const thought = String(input.thought ?? '');
      return thought.length > 60 ? thought.slice(0, 60) + '…' : thought;
    }
    case 'code': {
      const lang = String(input.language ?? '');
      const lines = String(input.source ?? '').split('\n').length;
      return `${lang} · ${lines} line${lines !== 1 ? 's' : ''}`;
    }
    case 'create_document': {
      const docType = String(input.doc_type ?? '').replace(/_/g, ' ');
      const title = String(input.title ?? '');
      return title ? `${docType}: ${title}` : docType;
    }
    case 's3_document_ops': {
      const op = String(input.operation ?? 'list');
      const key = String(input.key ?? '');
      return key ? `${op} · ${key.split('/').pop()}` : op;
    }
    case 'search_far': {
      return String(input.query ?? '');
    }
    case 'knowledge_search': {
      const parts = [];
      if (input.query) parts.push(String(input.query));
      if (input.topic) parts.push(`topic: ${input.topic}`);
      if (input.document_type) parts.push(`type: ${input.document_type}`);
      return parts.join(' · ') || 'searching...';
    }
    case 'knowledge_fetch': {
      const key = String(input.s3_key ?? input.document_id ?? '');
      return key.split('/').pop() || 'fetching document...';
    }
    case 'query_compliance_matrix': {
      const params = typeof input.params === 'string' ? input.params : JSON.stringify(input);
      try {
        const p = JSON.parse(params);
        const parts = [];
        if (p.acquisition_method) parts.push(p.acquisition_method.toUpperCase());
        if (p.contract_value) parts.push(`$${Number(p.contract_value).toLocaleString()}`);
        return parts.join(' · ') || String(p.operation ?? '');
      } catch {
        return params.slice(0, 60);
      }
    }
    case 'dynamodb_intake': {
      return String(input.operation ?? '');
    }
    case 'intake_workflow': {
      return String(input.action ?? '');
    }
    default: {
      // Subagent delegation — show the query
      const query = input.query ?? input.prompt ?? input.message;
      if (query) {
        const q = String(query);
        return q.length > 80 ? q.slice(0, 80) + '…' : q;
      }
      const first = Object.entries(input)[0];
      if (!first) return '';
      const val = typeof first[1] === 'string' ? first[1] : JSON.stringify(first[1]);
      return val.length > 60 ? val.slice(0, 60) + '…' : val;
    }
  }
}

// ── Status indicator ────────────────────────────────────────────────

function StatusDot({ status }: { status: ToolStatus }) {
  if (status === 'pending' || status === 'running') {
    return <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse shrink-0" />;
  }
  if (status === 'error') {
    return <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />;
  }
  return <span className="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" />;
}

// ── Document result card (inline in tool card) ──────────────────────

const DOC_LABEL: Record<string, string> = {
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification & Approval',
  eval_criteria: 'Evaluation Criteria',
  security_checklist: 'Security Checklist',
  section_508: 'Section 508 Compliance',
  cor_certification: 'COR Certification',
  contract_type_justification: 'Contract Type Justification',
};

function DocumentResultCard({
  data,
  sessionId,
}: {
  data: Record<string, unknown>;
  sessionId?: string;
}) {
  const title = String(data.title ?? data.document_type ?? 'Document');
  const docType = String(data.document_type ?? data.doc_type ?? 'unknown');
  const wordCount = data.word_count as number | undefined;
  const version = data.version as number | undefined;
  const s3Key = String(data.s3_key ?? '');

  const handleOpen = () => {
    const docId = encodeURIComponent(s3Key || (data.document_id as string) || title);
    const params = new URLSearchParams();
    if (sessionId) params.set('session', sessionId);

    // Store content in sessionStorage for instant load in document viewer
    const docInfo: DocumentInfo = {
      document_id: s3Key || (data.document_id as string),
      package_id: data.package_id as string | undefined,
      document_type: docType,
      doc_type: docType,
      title,
      content: data.content as string | undefined,
      mode: data.mode as 'package' | 'workspace' | undefined,
      status: data.status as string | undefined,
      version,
      word_count: wordCount,
      generated_at: data.generated_at as string | undefined,
      s3_key: s3Key || undefined,
      s3_location: data.s3_location as string | undefined,
    };
    try {
      sessionStorage.setItem(`doc-content-${docId}`, JSON.stringify(docInfo));
    } catch {
      // sessionStorage may be unavailable
    }

    window.open(`/documents/${docId}?${params.toString()}`, '_blank');
  };

  return (
    <div className="border-t border-[#E5E9F0] px-3 py-2.5 bg-white flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">
          {DOC_LABEL[docType] ?? docType.replace(/_/g, ' ')}
        </span>
        <p className="text-xs font-medium text-gray-900 truncate">{title}</p>
        <p className="text-[10px] text-gray-400">
          {version ? `v${version}` : 'Draft'}
          {wordCount ? ` • ${wordCount.toLocaleString()} words` : ''}
        </p>
      </div>
      <button
        type="button"
        onClick={handleOpen}
        className="flex items-center gap-1 px-2.5 py-1 bg-[#003366] text-white text-[10px] font-medium rounded-md
                   hover:bg-[#004488] transition-colors shrink-0"
      >
        Open Document
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      </button>
    </div>
  );
}

// ── Parse create_document result from tool result data ───────────────

function parseCreateDocumentResult(result: ClientToolResult | null | undefined): Record<string, unknown> | null {
  if (!result || !result.result) return null;

  // result.result may be a parsed object or a JSON string
  let data = result.result as Record<string, unknown>;
  if (typeof data === 'string') {
    try {
      data = JSON.parse(data);
    } catch {
      return null;
    }
  }

  if (data && typeof data === 'object' && !data.error && (data.document_type || data.doc_type || data.s3_key)) {
    return data;
  }
  return null;
}

// ── Extract knowledge sources from tool results ─────────────────────

export function extractKnowledgeSources(
  toolName: string,
  result: ClientToolResult | null | undefined,
): KnowledgeSource[] {
  if (!result?.result) return [];
  let data = result.result as Record<string, unknown>;
  if (typeof data === 'string') {
    try { data = JSON.parse(data); } catch { return []; }
  }
  if (!data || typeof data !== 'object') return [];

  const sources: KnowledgeSource[] = [];

  if (toolName === 'knowledge_search' && Array.isArray(data.results)) {
    for (const r of data.results as Record<string, unknown>[]) {
      sources.push({
        document_id: String(r.document_id ?? ''),
        title: String(r.title ?? 'Untitled'),
        summary: String(r.summary ?? ''),
        document_type: String(r.document_type ?? ''),
        primary_topic: String(r.primary_topic ?? ''),
        primary_agent: String(r.primary_agent ?? ''),
        authority_level: String(r.authority_level ?? ''),
        s3_key: String(r.s3_key ?? ''),
        confidence_score: Number(r.confidence_score ?? 0),
        keywords: Array.isArray(r.keywords) ? r.keywords.map(String) : [],
        source_tool: 'knowledge_search',
      });
    }
  }

  if (toolName === 'knowledge_fetch') {
    sources.push({
      document_id: String(data.document_id ?? ''),
      title: String(data.title ?? data.document_id ?? 'Document'),
      s3_key: String(data.s3_key ?? ''),
      content: String(data.content ?? ''),
      truncated: Boolean(data.truncated),
      content_length: Number(data.content_length ?? 0),
      source_tool: 'knowledge_fetch',
    });
  }

  if (toolName === 'search_far' && Array.isArray(data.results)) {
    for (const r of data.results as Record<string, unknown>[]) {
      sources.push({
        document_id: String(r.part ?? r.section ?? ''),
        title: String(r.title ?? `FAR ${r.part ?? ''}`),
        summary: String(r.text ?? r.summary ?? ''),
        document_type: 'far_regulation',
        source_tool: 'search_far',
      });
    }
  }

  return sources;
}

// ── Authority level badge colors ────────────────────────────────────

const AUTHORITY_COLORS: Record<string, string> = {
  mandatory: 'bg-red-100 text-red-700',
  regulatory: 'bg-orange-100 text-orange-700',
  policy: 'bg-blue-100 text-blue-700',
  guidance: 'bg-green-100 text-green-700',
  reference: 'bg-gray-100 text-gray-600',
  template: 'bg-violet-100 text-violet-700',
};

// ── Knowledge Search Result Card ────────────────────────────────────

function KnowledgeSearchResultCard({
  result,
}: {
  result: ClientToolResult | null | undefined;
}) {
  const sources = extractKnowledgeSources('knowledge_search', result);
  if (sources.length === 0) return null;

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      <div className="px-3 py-1.5">
        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">
          {sources.length} document{sources.length !== 1 ? 's' : ''} found
        </span>
      </div>
      <div className="space-y-0.5 pb-1">
        {sources.map((src, i) => (
          <div
            key={src.document_id || i}
            className="px-3 py-2 hover:bg-blue-50/50 transition cursor-pointer group"
            onClick={() => {
              if (src.s3_key) {
                const docId = encodeURIComponent(src.s3_key);
                window.open(`/documents/${docId}`, '_blank');
              }
            }}
          >
            <div className="flex items-start gap-2">
              <span className="text-sm shrink-0 mt-0.5">📄</span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-[#003366] group-hover:underline truncate">
                  {src.title}
                </p>
                {src.summary && (
                  <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-2">{src.summary}</p>
                )}
                <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                  {src.authority_level && (
                    <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${
                      AUTHORITY_COLORS[src.authority_level] ?? AUTHORITY_COLORS.reference
                    }`}>
                      {src.authority_level}
                    </span>
                  )}
                  {src.document_type && (
                    <span className="text-[9px] text-gray-400 font-mono">
                      {src.document_type}
                    </span>
                  )}
                  {src.confidence_score ? (
                    <span className={`text-[9px] font-mono ${
                      src.confidence_score >= 0.8 ? 'text-green-600' :
                      src.confidence_score >= 0.5 ? 'text-amber-600' : 'text-gray-400'
                    }`}>
                      {(src.confidence_score * 100).toFixed(0)}% match
                    </span>
                  ) : null}
                  {src.primary_agent && (
                    <span className="text-[9px] text-violet-500">
                      agent: {src.primary_agent}
                    </span>
                  )}
                </div>
              </div>
              {src.s3_key && (
                <span className="text-[9px] text-blue-400 opacity-0 group-hover:opacity-100 transition shrink-0 mt-1">
                  View →
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Knowledge Fetch Result Card ─────────────────────────────────────

function KnowledgeFetchResultCard({
  result,
}: {
  result: ClientToolResult | null | undefined;
}) {
  const [showContent, setShowContent] = useState(false);
  const sources = extractKnowledgeSources('knowledge_fetch', result);
  if (sources.length === 0) return null;
  const src = sources[0];

  return (
    <div className="border-t border-[#E5E9F0] bg-white px-3 py-2.5">
      <div className="flex items-start gap-2">
        <span className="text-sm shrink-0">📖</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-[#003366] truncate">{src.title}</p>
            {src.truncated && (
              <span className="text-[8px] text-amber-600 bg-amber-50 px-1 rounded">truncated</span>
            )}
          </div>
          {src.content_length ? (
            <p className="text-[10px] text-gray-400 mt-0.5">
              {src.content_length.toLocaleString()} chars
            </p>
          ) : null}
          <div className="flex items-center gap-2 mt-1.5">
            {src.content && (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setShowContent(!showContent); }}
                className="text-[10px] text-blue-600 hover:text-blue-800 font-medium"
              >
                {showContent ? 'Hide content' : 'Preview content'}
              </button>
            )}
            {src.s3_key && (
              <button
                type="button"
                onClick={() => window.open(`/documents/${encodeURIComponent(src.s3_key!)}`, '_blank')}
                className="text-[10px] text-blue-600 hover:text-blue-800 font-medium"
              >
                Open full document →
              </button>
            )}
          </div>
          {showContent && src.content && (
            <pre className="mt-2 p-2 bg-gray-50 border border-gray-200 rounded text-[10px] font-mono text-gray-700 whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
              {src.content.slice(0, 3000)}
              {src.content.length > 3000 ? '\n\n... [content truncated for display]' : ''}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ── FAR Search Result Card ──────────────────────────────────────────

function FARSearchResultCard({
  result,
}: {
  result: ClientToolResult | null | undefined;
}) {
  if (!result?.result) return null;
  let data = result.result as Record<string, unknown>;
  if (typeof data === 'string') {
    try { data = JSON.parse(data); } catch { return null; }
  }
  const results = Array.isArray(data.results) ? data.results as Record<string, unknown>[] : [];
  if (results.length === 0) return null;

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      <div className="px-3 py-1.5">
        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">
          {results.length} FAR section{results.length !== 1 ? 's' : ''} found
        </span>
      </div>
      <div className="space-y-0.5 pb-1">
        {results.slice(0, 10).map((r, i) => (
          <div key={i} className="px-3 py-2">
            <div className="flex items-start gap-2">
              <span className="text-sm shrink-0 mt-0.5">📖</span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-[#003366]">
                  {r.part ? `FAR ${String(r.part)}` : ''}{r.section ? `.${String(r.section)}` : ''}
                  {r.title ? ` — ${String(r.title)}` : ''}
                </p>
                {(r.text || r.summary) ? (
                  <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-3">
                    {String(r.text ?? r.summary ?? '')}
                  </p>
                ) : null}
                {r.applicability ? (
                  <span className="text-[9px] text-blue-500 mt-0.5 inline-block">
                    Applies to: {String(r.applicability)}
                  </span>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ──────────────────────────────────────────────────

export default function ToolUseDisplay({
  toolName,
  input,
  status,
  result,
  isClientSide = false,
  sessionId,
}: ToolUseDisplayProps) {
  const [expanded, setExpanded] = useState(false);
  const meta = getToolMeta(toolName);
  const summary = summarizeInput(toolName, input);

  const hasResult = result !== undefined && result !== null;
  const errorText = hasResult ? result.error : null;

  // Special handling for create_document — show document card instead of raw JSON
  const docData = toolName === 'create_document' ? parseCreateDocumentResult(result) : null;

  // Knowledge/FAR tool specialized cards
  const isKnowledgeSearch = toolName === 'knowledge_search';
  const isKnowledgeFetch = toolName === 'knowledge_fetch';
  const isFARSearch = toolName === 'search_far';
  const hasSpecializedCard = isKnowledgeSearch || isKnowledgeFetch || isFARSearch;

  // Extract markdown report from subagent/tool results
  // Subagent results arrive as { report: "markdown..." }, service tools as { content: "...", ... }
  const reportText = hasResult && !docData && result.result && typeof result.result === 'object'
    ? (result.result as Record<string, unknown>).report as string | undefined
    : undefined;

  const resultText =
    hasResult && !docData && !reportText && result.result !== null && result.result !== undefined
      ? JSON.stringify(result.result, null, 2)
      : null;

  const canExpand = (status === 'done' || status === 'error') && !hasSpecializedCard && (resultText || reportText || errorText);
  const showDocCard = status === 'done' && docData !== null;

  return (
    <div
      className={`my-1 rounded-lg border text-xs overflow-hidden transition-colors ${
        status === 'running' || status === 'pending'
          ? 'border-blue-200 bg-blue-50/50'
          : status === 'error'
          ? 'border-red-200 bg-red-50/30'
          : 'border-[#E5E9F0] bg-[#F8FAFC]'
      }`}
    >
      {/* Header row */}
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2 text-left"
        onClick={() => canExpand && setExpanded((v) => !v)}
        disabled={!canExpand && !showDocCard}
      >
        {/* Icon */}
        <span className="text-sm shrink-0 leading-none" role="img" aria-label={meta.label}>
          {meta.icon}
        </span>

        {/* Label */}
        <span className="font-medium text-gray-800 shrink-0">
          {status === 'done' && toolName === 'create_document' ? 'Document Created' : meta.label}
        </span>

        {/* Summary */}
        {summary && (
          <span className="text-gray-400 truncate min-w-0 flex-1">
            {summary}
          </span>
        )}

        {/* Status dot */}
        <StatusDot status={status} />

        {/* Chevron */}
        {canExpand && (
          <span className={`text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}>
            ▾
          </span>
        )}
      </button>

      {/* Document result card — shown inline for create_document */}
      {showDocCard && (
        <DocumentResultCard data={docData} sessionId={sessionId} />
      )}

      {/* Knowledge search results — clickable document cards */}
      {status === 'done' && isKnowledgeSearch && (
        <KnowledgeSearchResultCard result={result} />
      )}

      {/* Knowledge fetch result — document preview with content toggle */}
      {status === 'done' && isKnowledgeFetch && (
        <KnowledgeFetchResultCard result={result} />
      )}

      {/* FAR search results — regulation sections */}
      {status === 'done' && isFARSearch && (
        <FARSearchResultCard result={result} />
      )}

      {/* Collapsible result panel (non-specialized tools) */}
      {expanded && (
        <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
          {errorText ? (
            <p className="text-red-600 font-mono text-[11px] whitespace-pre-wrap break-all">
              {errorText}
            </p>
          ) : reportText ? (
            <div className="prose prose-xs prose-gray max-w-none text-[11px] leading-relaxed
                            [&_h1]:text-xs [&_h1]:font-bold [&_h1]:mt-2 [&_h1]:mb-1
                            [&_h2]:text-[11px] [&_h2]:font-bold [&_h2]:mt-2 [&_h2]:mb-1
                            [&_h3]:text-[11px] [&_h3]:font-semibold [&_h3]:mt-1.5 [&_h3]:mb-0.5
                            [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0
                            [&_code]:text-[10px] [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded">
              <ReactMarkdown>{reportText}</ReactMarkdown>
            </div>
          ) : resultText ? (
            <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">
              {resultText}
            </pre>
          ) : null}
        </div>
      )}
    </div>
  );
}
