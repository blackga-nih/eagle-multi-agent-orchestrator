'use client';

import { useState } from 'react';
import { ClientToolResult } from '@/lib/client-tools';
import { DocumentInfo } from '@/types/chat';
import { resolveResultPanel } from './tool-result-panels';

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

export const TOOL_META: Record<string, { icon: string; label: string }> = {
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
  // Service tools
  s3_document_ops:      { icon: '📁', label: 'Document Storage' },
  dynamodb_intake:      { icon: '🗃️', label: 'Intake Records' },
  create_document:      { icon: '📝', label: 'Creating Document' },
  get_intake_status:    { icon: '📊', label: 'Intake Status' },
  intake_workflow:      { icon: '🔄', label: 'Intake Workflow' },
  search_far:           { icon: '📖', label: 'Searching FAR/DFARS' },
  web_search:           { icon: '🌐', label: 'Web Search' },
  web_fetch:            { icon: '📄', label: 'Reading Page' },
  query_compliance_matrix: { icon: '✅', label: 'Compliance Matrix' },
  // Knowledge & reference tools
  knowledge_search:           { icon: '🔍', label: 'Knowledge Search' },
  knowledge_fetch:            { icon: '📄', label: 'Reading Document' },
  load_skill:                 { icon: '📋', label: 'Loading Skill' },
  list_skills:                { icon: '📑', label: 'Listing Skills' },
  load_data:                  { icon: '📊', label: 'Loading Data' },
  // Document management tools
  edit_docx_document:         { icon: '✏️', label: 'Editing Document' },
  get_latest_document:        { icon: '📄', label: 'Checking Document' },
  finalize_package:           { icon: '📦', label: 'Finalizing Package' },
  document_changelog_search:  { icon: '📜', label: 'Changelog Search' },
  // Admin tools
  manage_skills:              { icon: '⚙️', label: 'Managing Skills' },
  manage_prompts:             { icon: '💬', label: 'Managing Prompts' },
  manage_templates:           { icon: '📋', label: 'Managing Templates' },
  cloudwatch_logs:            { icon: '🔎', label: 'CloudWatch Logs' },
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
    case 'web_search': {
      return String(input.query ?? '');
    }
    case 'web_fetch': {
      const fetchUrl = String(input.url ?? '');
      try {
        return new URL(fetchUrl).hostname;
      } catch {
        return fetchUrl.length > 60 ? fetchUrl.slice(0, 60) + '...' : fetchUrl;
      }
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
    case 'knowledge_search': {
      return String(input.query ?? input.topic ?? '');
    }
    case 'knowledge_fetch': {
      const key = String(input.s3_key ?? '');
      return key.split('/').pop() || key;
    }
    case 'load_skill': {
      return String(input.name ?? '');
    }
    case 'load_data': {
      const name = String(input.name ?? '');
      const section = input.section ? ` / ${input.section}` : '';
      return name + section;
    }
    case 'edit_docx_document': {
      const key = String(input.document_key ?? '');
      return key.split('/').pop() || key;
    }
    case 'get_latest_document': {
      return String(input.doc_type ?? '').replace(/_/g, ' ');
    }
    case 'finalize_package': {
      return String(input.package_id ?? '');
    }
    case 'document_changelog_search': {
      const pkg = String(input.package_id ?? '');
      const dt = input.doc_type ? ` / ${input.doc_type}` : '';
      return pkg + dt;
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

// ── Web search result card ───────────────────────────────────────────

function parseWebSearchResult(result: ClientToolResult | null | undefined): Record<string, unknown> | null {
  if (!result || !result.result) return null;

  let data = result.result as Record<string, unknown>;
  if (typeof data === 'string') {
    try {
      data = JSON.parse(data);
    } catch {
      return null;
    }
  }

  if (data && typeof data === 'object' && !data.error && data.sources) {
    return data;
  }
  return null;
}

function WebSearchResultCard({ data }: { data: Record<string, unknown> }) {
  const answer = String(data.answer ?? '');
  const sources = (data.sources as Array<Record<string, string>>) ?? [];
  const sourceCount = (data.source_count as number) ?? sources.length;
  const displaySources = sources.slice(0, 5);
  const truncatedAnswer = answer.length > 300 ? answer.slice(0, 300) + '...' : answer;

  return (
    <div className="border-t border-[#E5E9F0] px-3 py-2.5 bg-white space-y-2">
      {/* Answer preview */}
      {truncatedAnswer && (
        <p className="text-xs text-gray-700 leading-relaxed">{truncatedAnswer}</p>
      )}

      {/* Sources */}
      {displaySources.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">
              Sources
            </span>
            <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
              {sourceCount}
            </span>
          </div>
          <ol className="space-y-0.5">
            {displaySources.map((source, i) => (
              <li key={i} className="flex items-baseline gap-1.5 text-[11px]">
                <span className="text-gray-400 shrink-0">{i + 1}.</span>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:text-blue-800 hover:underline truncate min-w-0"
                  title={source.url}
                >
                  {source.domain || new URL(source.url).hostname}
                </a>
              </li>
            ))}
          </ol>
          {sourceCount > 5 && (
            <p className="text-[10px] text-gray-400">
              +{sourceCount - 5} more sources
            </p>
          )}
        </div>
      )}
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

  const hasExpandableResult = hasResult && !docData && (
    errorText || result.result !== null && result.result !== undefined
  );
  const canExpand = (status === 'done' || status === 'error') && hasExpandableResult;
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

        {/* Summary — shown as "Label — input params" */}
        {summary && (
          <span className="text-gray-400 truncate min-w-0 flex-1">
            — &ldquo;{summary}&rdquo;
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

      {/* Collapsible result panel — type-specific rendering */}
      {expanded && resolveResultPanel(toolName, input, result, errorText)}
    </div>
  );
}
