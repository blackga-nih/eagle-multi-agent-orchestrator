'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { ClientToolResult } from '@/lib/client-tools';
import { DocumentInfo } from '@/types/chat';
import { resolveResultPanel } from './tool-result-panels';
import Modal from '@/components/ui/modal';
import ReactMarkdown from 'react-markdown';

export type ToolStatus = 'pending' | 'running' | 'done' | 'error' | 'interrupted';

interface ToolUseDisplayProps {
  toolName: string;
  input: Record<string, unknown>;
  status: ToolStatus;
  result?: ClientToolResult | null;
  isClientSide?: boolean;
  sessionId?: string;
  streamingInput?: string;
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
  manage_package:             { icon: '📦', label: 'Package Update' },
  document_changelog_search:  { icon: '📜', label: 'Changelog Search' },
  // Admin tools
  manage_skills:              { icon: '⚙️', label: 'Managing Skills' },
  manage_prompts:             { icon: '💬', label: 'Managing Prompts' },
  manage_templates:           { icon: '📋', label: 'Managing Templates' },
  cloudwatch_logs:            { icon: '🔎', label: 'CloudWatch Logs' },
  generate_html_playground:   { icon: '🌐', label: 'Generating HTML' },
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
    case 'generate_html_playground': {
      const htmlTitle = String(input.title ?? '');
      const htmlDocType = String(input.doc_type ?? 'document').replace(/_/g, ' ');
      return htmlTitle ? `${htmlDocType}: ${htmlTitle}` : htmlDocType;
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

// ── Status helpers ───────────────────────────────────────────────────

function StatusDot({ status }: { status: ToolStatus }) {
  if (status === 'pending' || status === 'running') {
    return <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse shrink-0" />;
  }
  if (status === 'error') {
    return <span className="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />;
  }
  if (status === 'interrupted') {
    return <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />;
  }
  return <span className="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" />;
}

const STATUS_TEXT: Record<ToolStatus, string> = {
  pending: 'Pending',
  running: 'Running…',
  done: 'Completed',
  error: 'Error',
  interrupted: 'Interrupted',
};

// ── Chip border/bg by status ─────────────────────────────────────────

function chipClasses(status: ToolStatus): string {
  switch (status) {
    case 'pending':
    case 'running':
      return 'border-blue-300 bg-blue-50 hover:bg-blue-100';
    case 'error':
      return 'border-red-300 bg-red-50 hover:bg-red-100';
    case 'interrupted':
      return 'border-amber-300 bg-amber-50 hover:bg-amber-100';
    case 'done':
      return 'border-[#D1D9E0] bg-[#F8FAFC] hover:bg-gray-100';
  }
}

// ── Document result card (shown inside modal) ────────────────────────

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
  const source = data.source as string | undefined;
  const templatePath = data.template_path as string | undefined;
  const templateProvenance = data.template_provenance as { template_id?: string; template_source?: string } | undefined;

  // Derive template display info
  const templateDisplay = templateProvenance?.template_id || templatePath || source || 'Built-in';
  const templateLabel = templateDisplay.includes('/')
    ? templateDisplay.split('/').pop()
    : templateDisplay.replace(/_/g, ' ');

  const handleOpen = () => {
    const docId = encodeURIComponent(s3Key || (data.document_id as string) || title);
    const params = new URLSearchParams();
    if (sessionId) params.set('session', sessionId);

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
      source,
      template_path: templatePath,
    };
    try {
      sessionStorage.setItem(`doc-content-${docId}`, JSON.stringify(docInfo));
    } catch {
      // sessionStorage may be unavailable
    }

    window.open(`/documents/${docId}?${params.toString()}`, '_blank');
  };

  return (
    <div className="bg-gray-50 rounded-lg p-4 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <span className="text-[10px] font-bold uppercase text-blue-600 tracking-wider">
          {DOC_LABEL[docType] ?? docType.replace(/_/g, ' ')}
        </span>
        <p className="text-sm font-medium text-gray-900 truncate">{title}</p>
        <p className="text-xs text-gray-400 mt-0.5">
          {version ? `v${version}` : 'Draft'}
          {wordCount ? ` · ${wordCount.toLocaleString()} words` : ''}
        </p>
        {templateDisplay && (
          <p className="text-[10px] text-gray-400 mt-1 truncate" title={templateDisplay}>
            Template: {templateLabel}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={handleOpen}
        className="flex items-center gap-1 px-3 py-1.5 bg-[#003366] text-white text-xs font-medium rounded-md
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

// ── Parse helpers ────────────────────────────────────────────────────

function parseCreateDocumentResult(result: ClientToolResult | null | undefined): Record<string, unknown> | null {
  if (!result || !result.result) return null;

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

// ── Format input for modal display ───────────────────────────────────

function formatInputForDisplay(input: Record<string, unknown>): Array<[string, string]> {
  if (!input || Object.keys(input).length === 0) return [];
  return Object.entries(input)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => {
      const label = k.replace(/_/g, ' ');
      const value = typeof v === 'string'
        ? (v.length > 200 ? v.slice(0, 200) + '…' : v)
        : JSON.stringify(v, null, 2);
      return [label, value] as [string, string];
    })
    .slice(0, 8);
}

// ── Streaming preview helpers ────────────────────────────────────────

function extractContentFromJson(rawJson: string): string | null {
  const match = rawJson.match(/"content"\s*:\s*"/);
  if (!match || match.index === undefined) return null;
  const start = match.index + match[0].length;
  let content = rawJson.slice(start);
  // Remove trailing incomplete escape
  if (content.endsWith('\\')) content = content.slice(0, -1);
  // Unescape JSON string sequences
  return content
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, '\\');
}

function StreamingPreview({ rawJson, toolName }: { rawJson: string; toolName: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const content = useMemo(
    () => toolName === 'create_document' ? extractContentFromJson(rawJson) : null,
    [rawJson, toolName],
  );

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [rawJson.length]);

  if (content) {
    return (
      <div ref={scrollRef} className="max-h-64 overflow-y-auto rounded-lg border border-gray-100 p-3">
        <div className="prose prose-sm max-w-none">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
        <div className="flex items-center gap-2 text-blue-500 text-xs mt-2">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          <span>Writing... ({rawJson.length < 1024 ? `${rawJson.length}B` : `${Math.round(rawJson.length / 1024)}KB`})</span>
        </div>
      </div>
    );
  }

  return (
    <div className="text-sm text-gray-500 flex items-center gap-2 p-3 bg-gray-50 rounded-lg">
      <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
      <span>Composing input... ({rawJson.length} chars)</span>
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
  streamingInput,
}: ToolUseDisplayProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const meta = getToolMeta(toolName);
  const summary = summarizeInput(toolName, input);

  const hasResult = result !== undefined && result !== null;
  const errorText = hasResult ? result.error : null;
  const docData = toolName === 'create_document' ? parseCreateDocumentResult(result) : null;

  const chipLabel = status === 'done' && toolName === 'create_document' ? 'Document Created' : meta.label;

  return (
    <>
      {/* ── Compact chip ── */}
      <button
        type="button"
        data-testid="tool-chip"
        onClick={() => setModalOpen(true)}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs
                    cursor-pointer transition-colors select-none ${chipClasses(status)}`}
      >
        <span className="text-sm leading-none shrink-0" role="img" aria-label={chipLabel}>
          {meta.icon}
        </span>
        <span className="font-medium text-gray-700 whitespace-nowrap">{chipLabel}</span>
        {streamingInput && status !== 'done' ? (
          <span className="text-[10px] text-blue-500 truncate max-w-[120px]">
            Writing... ({streamingInput.length < 1024 ? `${streamingInput.length}B` : `${Math.round(streamingInput.length / 1024)}KB`})
          </span>
        ) : (
          <StatusDot status={status} />
        )}
      </button>

      {/* ── Detail modal ── */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={`${meta.icon} ${chipLabel}`}
        size="lg"
      >
        <div className="space-y-5">
          {/* Status + summary bar */}
          <div className="flex items-center gap-3 text-sm">
            <div className="flex items-center gap-1.5">
              <StatusDot status={status} />
              <span className={`font-medium ${
                status === 'error' ? 'text-red-600' :
                status === 'done' ? 'text-green-700' :
                'text-blue-600'
              }`}>
                {STATUS_TEXT[status]}
              </span>
            </div>
            {summary && (
              <span className="text-gray-500 truncate">{summary}</span>
            )}
          </div>

          {/* Input parameters */}
          {Object.keys(input).length > 0 && (
            <div>
              <h3 className="text-xs font-bold uppercase text-gray-400 tracking-wider mb-2">Input</h3>
              <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
                {formatInputForDisplay(input).map(([label, value]) => (
                  <div key={label} className="flex gap-2 text-xs">
                    <span className="font-medium text-gray-500 shrink-0 min-w-[80px]">{label}</span>
                    <span className="text-gray-800 break-words whitespace-pre-wrap min-w-0">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Streaming content preview */}
          {streamingInput && status !== 'done' && (
            <div>
              <h3 className="text-xs font-bold uppercase text-gray-400 tracking-wider mb-2">
                Live Preview
              </h3>
              <StreamingPreview rawJson={streamingInput} toolName={toolName} />
            </div>
          )}

          {/* Error */}
          {errorText && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <h3 className="text-xs font-bold uppercase text-red-600 tracking-wider mb-1">Error</h3>
              <p className="text-sm text-red-700 whitespace-pre-wrap">{errorText}</p>
            </div>
          )}

          {/* Document result card */}
          {status === 'done' && docData && (
            <DocumentResultCard data={docData} sessionId={sessionId} />
          )}

          {/* Tool-specific result panel */}
          {!errorText && !docData && hasResult && (status === 'done' || status === 'error') && (
            <div>
              <h3 className="text-xs font-bold uppercase text-gray-400 tracking-wider mb-2">Result</h3>
              <div className="border border-gray-100 rounded-lg overflow-hidden">
                {resolveResultPanel(toolName, input, result, null)}
              </div>
            </div>
          )}
        </div>
      </Modal>
    </>
  );
}
