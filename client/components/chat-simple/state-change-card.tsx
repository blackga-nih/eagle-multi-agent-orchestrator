'use client';

import { useState } from 'react';
import { StateChangeEntry } from '@/contexts/chat-runtime-context';
import Modal from '@/components/ui/modal';

// ── Human-friendly labels ────────────────────────────────────────────

const STATE_TYPE_META: Record<string, { icon: string; label: string }> = {
  checklist_update: { icon: '📋', label: 'Package Updated' },
  phase_change: { icon: '🔄', label: 'Phase Changed' },
  document_ready: { icon: '📄', label: 'Document Ready' },
  compliance_alert: { icon: '⚠️', label: 'Compliance Alert' },
  sources_read: { icon: '📖', label: 'Document Read' },
  sources_summary: { icon: '📚', label: 'Sources Summary' },
};

const SOURCE_DOC_TYPE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  template: { bg: 'bg-blue-100', text: 'text-blue-800', label: 'Template' },
  checklist: { bg: 'bg-amber-100', text: 'text-amber-800', label: 'Checklist' },
  regulation: { bg: 'bg-purple-100', text: 'text-purple-800', label: 'FAR/DFARS' },
  guidance: { bg: 'bg-green-100', text: 'text-green-800', label: 'Guidance' },
  policy: { bg: 'bg-teal-100', text: 'text-teal-800', label: 'Policy' },
  document: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Document' },
  memo: { bg: 'bg-indigo-100', text: 'text-indigo-800', label: 'Memo' },
  reference: { bg: 'bg-slate-100', text: 'text-slate-800', label: 'Reference' },
};

const SOURCE_TOOL_LABELS: Record<string, string> = {
  knowledge_fetch: 'Knowledge Base',
  search_far: 'FAR/DFARS Search',
  research: 'Research Tool',
  web_fetch: 'Web Fetch',
};

function docLabel(slug: string): string {
  const map: Record<string, string> = {
    sow: 'Statement of Work',
    igce: 'IGCE',
    market_research: 'Market Research Report',
    acquisition_plan: 'Acquisition Plan',
    justification: 'Justification & Approval',
    source_selection_plan: 'Source Selection Plan',
    eval_criteria: 'Evaluation Criteria',
    determination_findings: 'Determination & Findings',
    security_checklist: 'Security Checklist',
    section_508: 'Section 508 Compliance',
    cor_certification: 'COR Certification',
    contract_type_justification: 'Contract Type Justification',
    subcontracting_plan: 'Subcontracting Plan',
  };
  return map[slug] || slug.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Summary line ─────────────────────────────────────────────────────

function getSummary(entry: StateChangeEntry): string {
  switch (entry.stateType) {
    case 'checklist_update': {
      const req = entry.checklist?.required?.length ?? 0;
      const done = entry.checklist?.completed?.length ?? 0;
      if (req > 0) return `${done}/${req} docs complete`;
      if (entry.title) return entry.title;
      return 'Package updated';
    }
    case 'phase_change':
      return entry.phase ? `→ ${entry.phase}` : 'Phase changed';
    case 'document_ready':
      return 'New document available';
    case 'compliance_alert':
      return 'Review required';
    case 'sources_read':
      return entry.sourceTitle || 'Reading document...';
    case 'sources_summary': {
      const n = entry.fetchCount ?? 0;
      const chars = entry.totalCharsRead ?? 0;
      return `${n} doc${n !== 1 ? 's' : ''} read (${chars.toLocaleString()} chars)`;
    }
    default:
      return entry.stateType.replace(/_/g, ' ');
  }
}

// ── Main component ───────────────────────────────────────────────────

interface StateChangeCardProps {
  entry: StateChangeEntry;
}

export default function StateChangeCard({ entry }: StateChangeCardProps) {
  const [showDetail, setShowDetail] = useState(false);
  const meta = STATE_TYPE_META[entry.stateType] ?? { icon: '📦', label: entry.stateType };
  const summary = getSummary(entry);
  const progressPct = entry.progressPct ?? 0;
  const hasProgress =
    entry.stateType === 'checklist_update' && (entry.checklist?.required?.length ?? 0) > 0;
  const isSourceEvent = entry.stateType === 'sources_read';
  const isSourceSummary = entry.stateType === 'sources_summary';
  const docTypeStyle = SOURCE_DOC_TYPE_STYLES[entry.sourceDocType ?? ''] ?? SOURCE_DOC_TYPE_STYLES.document;

  return (
    <>
      {/* Compact inline chip */}
      <button
        data-testid="state-change-card"
        onClick={() => setShowDetail(true)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-[#D8DEE6] bg-white hover:bg-gray-50 transition-colors cursor-pointer text-left max-w-xs"
      >
        <span className="text-sm flex-shrink-0">{meta.icon}</span>
        <span className="text-[11px] font-medium text-[#003366] truncate">{meta.label}</span>
        <span className="text-[10px] text-gray-500 truncate">{summary}</span>
        {hasProgress && (
          <span className="ml-1 flex-shrink-0 w-12 h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <span
              className="block h-full bg-[#2196F3] rounded-full transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </span>
        )}
      </button>

      {/* Detail modal */}
      {showDetail && (
        <Modal
          isOpen={showDetail}
          onClose={() => setShowDetail(false)}
          title={isSourceEvent ? 'Source Document' : isSourceSummary ? 'Sources Summary' : 'Package State Update'}
        >
          <div data-testid="state-change-detail" className="space-y-3 text-sm">
            {/* Header row */}
            <div className="flex items-center gap-2">
              <span className="text-lg">{meta.icon}</span>
              <span className="font-semibold text-[#003366]">{meta.label}</span>
            </div>

            {/* ── Sources Read detail ─────────────────────── */}
            {isSourceEvent && (
              <div className="space-y-3">
                <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
                  {entry.sourceTitle && (
                    <>
                      <span className="text-gray-500">Title</span>
                      <span className="text-gray-700 font-medium">{entry.sourceTitle}</span>
                    </>
                  )}
                  {entry.sourceDocType && (
                    <>
                      <span className="text-gray-500">Type</span>
                      <span>
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${docTypeStyle.bg} ${docTypeStyle.text}`}>
                          {docTypeStyle.label}
                        </span>
                      </span>
                    </>
                  )}
                  {entry.sourceS3Key && (
                    <>
                      <span className="text-gray-500">File</span>
                      <span className="font-mono text-gray-600 text-[11px] break-all">
                        {entry.sourceS3Key.includes('/') ? entry.sourceS3Key.split('/').pop() : entry.sourceS3Key}
                      </span>
                    </>
                  )}
                  {entry.sourceCharsRead != null && entry.sourceCharsRead > 0 && (
                    <>
                      <span className="text-gray-500">Characters Read</span>
                      <span className="text-gray-700">{entry.sourceCharsRead.toLocaleString()}</span>
                    </>
                  )}
                  {entry.sourceTool && (
                    <>
                      <span className="text-gray-500">Source</span>
                      <span className="text-gray-700">{SOURCE_TOOL_LABELS[entry.sourceTool] || entry.sourceTool}</span>
                    </>
                  )}
                </div>
              </div>
            )}

            {/* ── Sources Summary detail ──────────────────── */}
            {isSourceSummary && (
              <div className="space-y-3">
                <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
                  <span className="text-gray-500">Documents Read</span>
                  <span className="text-gray-700 font-medium">{entry.fetchCount ?? 0}</span>
                  <span className="text-gray-500">Searches Performed</span>
                  <span className="text-gray-700">{entry.searchCount ?? 0}</span>
                  <span className="text-gray-500">Total Characters</span>
                  <span className="text-gray-700">{(entry.totalCharsRead ?? 0).toLocaleString()}</span>
                </div>
                {entry.fetchedKeys && entry.fetchedKeys.length > 0 && (
                  <div>
                    <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">
                      Documents Fetched
                    </p>
                    <ul className="space-y-1">
                      {entry.fetchedKeys.map((key) => (
                        <li key={key} className="flex items-center gap-2 text-xs">
                          <span className="text-gray-400">📖</span>
                          <span className="font-mono text-gray-600 text-[11px] truncate">
                            {key.includes('/') ? key.split('/').pop() : key}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* ── Package state detail (existing) ─────────── */}
            {!isSourceEvent && !isSourceSummary && (
              <>
                {/* Package info */}
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  {entry.packageId && (
                    <>
                      <span className="text-gray-500">Package ID</span>
                      <span className="font-mono text-gray-700">{entry.packageId}</span>
                    </>
                  )}
                  {entry.title && (
                    <>
                      <span className="text-gray-500">Title</span>
                      <span className="text-gray-700">{entry.title}</span>
                    </>
                  )}
                  {entry.phase && (
                    <>
                      <span className="text-gray-500">Phase</span>
                      <span className="text-gray-700 capitalize">{entry.phase}</span>
                    </>
                  )}
                  {entry.acquisitionMethod && (
                    <>
                      <span className="text-gray-500">Acquisition Method</span>
                      <span className="text-gray-700 capitalize">
                        {entry.acquisitionMethod.replace(/_/g, ' ')}
                      </span>
                    </>
                  )}
                  {entry.contractType && (
                    <>
                      <span className="text-gray-500">Contract Type</span>
                      <span className="text-gray-700 uppercase">{entry.contractType}</span>
                    </>
                  )}
                  {entry.contractVehicle && (
                    <>
                      <span className="text-gray-500">Vehicle</span>
                      <span className="text-gray-700">{entry.contractVehicle}</span>
                    </>
                  )}
                </div>

                {/* Progress bar */}
                {hasProgress && (
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-500">Document Progress</span>
                      <span className="text-xs font-medium text-[#003366]">
                        {entry.checklist?.completed?.length ?? 0}/
                        {entry.checklist?.required?.length ?? 0}
                      </span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2">
                      <div
                        className="bg-[#2196F3] h-2 rounded-full transition-all"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Document checklist */}
                {entry.checklist && entry.checklist.required.length > 0 && (
                  <div>
                    <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1.5">
                      Required Documents
                    </p>
                    <ul className="space-y-1">
                      {entry.checklist.required.map((docType) => {
                        const isDone = entry.checklist?.completed?.includes(docType);
                        return (
                          <li key={docType} className="flex items-center gap-2 text-xs">
                            <span
                              className={`w-3.5 h-3.5 rounded border flex items-center justify-center ${
                                isDone
                                  ? 'bg-green-100 border-green-500 text-green-700'
                                  : 'border-gray-300'
                              }`}
                            >
                              {isDone && (
                                <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                                  <path
                                    fillRule="evenodd"
                                    d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                                    clipRule="evenodd"
                                  />
                                </svg>
                              )}
                            </span>
                            <span className={isDone ? 'text-gray-400 line-through' : 'text-gray-700'}>
                              {docLabel(docType)}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
