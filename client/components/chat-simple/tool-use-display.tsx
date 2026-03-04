'use client';

import { useState } from 'react';
import { ClientToolResult } from '@/lib/client-tools';
import { DocumentInfo } from '@/types/chat';

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
  const s3Key = String(data.s3_key ?? '');

  const handleOpen = () => {
    const docId = encodeURIComponent(data.document_id as string || s3Key || title);
    const params = new URLSearchParams();
    if (sessionId) params.set('session', sessionId);

    // Store content in sessionStorage for instant load in document viewer
    const docInfo: DocumentInfo = {
      document_id: (data.document_id as string) || s3Key,
      document_type: docType,
      title,
      content: data.content as string | undefined,
      status: data.status as string | undefined,
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
        {wordCount && (
          <p className="text-[10px] text-gray-400">{wordCount.toLocaleString()} words</p>
        )}
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

  const resultText =
    hasResult && !docData && result.result !== null && result.result !== undefined
      ? JSON.stringify(result.result, null, 2)
      : null;

  const canExpand = (status === 'done' || status === 'error') && (resultText || errorText);
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

      {/* Collapsible result panel (non-document tools) */}
      {expanded && (
        <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white">
          {errorText ? (
            <p className="text-red-600 font-mono text-[11px] whitespace-pre-wrap break-all">
              {errorText}
            </p>
          ) : resultText ? (
            <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
              {resultText}
            </pre>
          ) : null}
        </div>
      )}
    </div>
  );
}
