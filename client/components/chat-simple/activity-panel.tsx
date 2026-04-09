'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import {
  FileText,
  Bell,
  Terminal,
  ClipboardCheck,
  PanelRightClose,
  PanelRightOpen,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Trash2,
  BookOpenText,
} from 'lucide-react';
import { AuditLogEntry } from '@/types/stream';
import { DocumentInfo } from '@/types/chat';
import type { StateChangeEntry } from '@/contexts/chat-runtime-context';
import AgentLogs, { buildDisplayEntries } from './agent-logs';
import { ChecklistTabContent, docLabel } from './checklist-panel';
import DocumentViewerModal from './document-viewer-modal';
import type { PackageState } from '@/hooks/use-package-state';
import { useAllPackages } from '@/hooks/use-all-packages';
import type { PackageInfo, PackageDocument } from '@/lib/document-api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ActivityPanelProps {
  logs: AuditLogEntry[];
  clearLogs: () => void;
  documents: Record<string, DocumentInfo[]>;
  sessionId?: string;
  isStreaming: boolean;
  isOpen: boolean;
  onToggle: () => void;
  packageState?: PackageState;
  getToken: () => Promise<string | null>;
  onRefreshPackage?: () => void;
  isRefreshingPackage?: boolean;
  stateChangesByMsg?: Record<string, StateChangeEntry[]>;
}

type TabId = 'package' | 'documents' | 'sources' | 'notifications' | 'logs';

interface TabDef {
  id: TabId;
  label: string;
  icon: typeof FileText;
}

const TABS: TabDef[] = [
  { id: 'package', label: 'Package', icon: ClipboardCheck },
  { id: 'documents', label: 'Documents', icon: FileText },
  { id: 'sources', label: 'Sources', icon: BookOpenText },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'logs', label: 'Agent Logs', icon: Terminal },
];

// ---------------------------------------------------------------------------
// Phase badge styles (shared with checklist-panel)
// ---------------------------------------------------------------------------

const PHASE_STYLES: Record<string, string> = {
  intake: 'bg-blue-100 text-blue-800',
  drafting: 'bg-amber-100 text-amber-800',
  finalizing: 'bg-purple-100 text-purple-800',
  review: 'bg-green-100 text-green-800',
  approved: 'bg-emerald-100 text-emerald-800',
};

// ---------------------------------------------------------------------------
// Document type icon helper
// ---------------------------------------------------------------------------

import { DOCUMENT_TYPE_ICONS, type DocumentType } from '@/types/schema';

function getDocIcon(type: string): string {
  return DOCUMENT_TYPE_ICONS[type as DocumentType] ?? '\u{1F4C4}';
}

/** Format-only types that should be replaced with a label inferred from title. */
const FORMAT_TYPES = new Set(['markdown', 'docx', 'xlsx', 'pdf', 'txt', 'document']);

function getDocTypeLabel(doc: DocumentInfo): string {
  const raw = doc.document_type;
  if (!FORMAT_TYPES.has(raw)) {
    return raw.replace(/_/g, ' ');
  }
  const t = (doc.title || '').toLowerCase();
  if (t.includes('sow') || (t.includes('statement') && t.includes('work')))
    return 'Statement of Work';
  if (t.includes('igce') || t.includes('ige') || t.includes('cost estimate'))
    return 'Cost Estimate';
  if (t.includes('market') || t.startsWith('mr-') || t.startsWith('mr_')) return 'Market Research';
  if (
    (t.includes('acquisition') && t.includes('plan')) ||
    t.startsWith('ap-') ||
    t.startsWith('ap_')
  )
    return 'Acquisition Plan';
  if (t.includes('justification') || t.includes('j&a')) return 'Justification & Approval';
  if (t.includes('son') || (t.includes('statement') && t.includes('need')))
    return 'Statement of Need';
  if (t.includes('cor')) return 'COR Appointment';
  if (t.includes('subk') || t.includes('subcontract')) return 'Subcontracting Plan';
  if (t.includes('conference')) return 'Conference Request';
  if (t.includes('buy') && t.includes('american')) return 'Buy American';
  if (t.includes('transmittal') || t.includes('cover memo')) return 'Transmittal Memo';
  return raw.replace(/_/g, ' ');
}

/** Relative time label (e.g. "2 days ago"). */
function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

/** Format dollar value. */
function formatValue(val?: string): string {
  if (!val) return '';
  const n = parseFloat(val);
  if (isNaN(n)) return val;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Single package card in the all-packages list. */
function PackageCard({
  pkg,
  isExpanded,
  onToggle,
  onDelete,
  documents,
  isLoadingDocs,
}: {
  pkg: PackageInfo;
  isExpanded: boolean;
  onToggle: () => void;
  onDelete?: () => void;
  documents: PackageDocument[];
  isLoadingDocs: boolean;
}) {
  const status = pkg.status ?? 'unknown';
  const cr = pkg.compliance_readiness;
  const progress = cr ? `${cr.finalized_count ?? 0}/${cr.total_required ?? 0}` : null;

  const openDoc = (doc: PackageDocument) => {
    const docId = encodeURIComponent(doc.s3_key || doc.document_id || doc.title);
    window.open(`/documents/${docId}`, '_blank');
  };

  return (
    <div className="rounded-lg border border-[#D8DEE6] bg-white overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left px-3 py-2.5 hover:bg-gray-50 transition flex items-start gap-2"
      >
        <span className="mt-0.5 shrink-0 text-gray-400">
          {isExpanded ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-[#003366] truncate">{pkg.title}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span
              className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${PHASE_STYLES[status] || 'bg-gray-100 text-gray-600'}`}
            >
              {status}
            </span>
            {progress && <span className="text-[10px] text-gray-400">{progress} docs</span>}
            {pkg.estimated_value && (
              <span className="text-[10px] text-gray-400">{formatValue(pkg.estimated_value)}</span>
            )}
          </div>
          {pkg.created_at && (
            <p className="text-[9px] text-gray-400 mt-0.5">{relativeTime(pkg.created_at)}</p>
          )}
        </div>
        {onDelete && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (window.confirm(`Delete package "${pkg.title}"? This cannot be undone.`)) {
                onDelete();
              }
            }}
            className="shrink-0 p-1 text-gray-300 hover:text-red-500 rounded transition"
            title="Delete package"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </button>

      {/* Expanded: show documents */}
      {isExpanded && (
        <div className="border-t border-[#D8DEE6] px-3 py-2 bg-gray-50">
          {isLoadingDocs && (
            <p className="text-[10px] text-gray-400 animate-pulse">Loading documents...</p>
          )}
          {!isLoadingDocs && documents.length === 0 && (
            <p className="text-[10px] text-gray-400">No documents yet.</p>
          )}
          {!isLoadingDocs && documents.length > 0 && (
            <div className="space-y-1">
              {documents.map((doc) => (
                <button
                  key={doc.document_id}
                  type="button"
                  onClick={() => openDoc(doc)}
                  className="w-full text-left flex items-center gap-2 px-2 py-1.5 rounded hover:bg-white transition"
                  title="Open document"
                >
                  <span className="text-sm shrink-0">{getDocIcon(doc.doc_type)}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-medium text-[#003366] truncate">{doc.title}</p>
                    <div className="flex items-center gap-1.5 text-[9px] text-gray-400">
                      <span className="uppercase">{doc.doc_type.replace(/_/g, ' ')}</span>
                      <span>v{doc.version}</span>
                      {doc.status && (
                        <span
                          className={`px-1 py-0.5 rounded-full font-medium ${
                            doc.status === 'final'
                              ? 'bg-green-100 text-green-700'
                              : doc.status === 'draft'
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {doc.status}
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** All Packages list component. */
function AllPackagesList({
  getToken,
  activePackageId,
  isStreaming,
  hasActiveChecklist,
}: {
  getToken: () => Promise<string | null>;
  activePackageId?: string;
  isStreaming?: boolean;
  hasActiveChecklist?: boolean;
}) {
  const { packages, loading, error, refetch, removePackage, fetchDocuments, documentsCache, loadingDocs } =
    useAllPackages(getToken);
  const [expandedPkg, setExpandedPkg] = useState<string | null>(null);
  const wasStreamingRef = useRef(false);

  // Auto-refetch when streaming completes (new packages may have been created)
  useEffect(() => {
    if (wasStreamingRef.current && !isStreaming) {
      refetch();
    }
    wasStreamingRef.current = !!isStreaming;
  }, [isStreaming, refetch]);

  const handleToggle = async (pkgId: string) => {
    if (expandedPkg === pkgId) {
      setExpandedPkg(null);
    } else {
      setExpandedPkg(pkgId);
      await fetchDocuments(pkgId);
    }
  };

  // Only hide the active package when its checklist is visible above
  const filteredPackages = activePackageId && hasActiveChecklist
    ? packages.filter((p) => p.package_id !== activePackageId)
    : packages;

  if (loading && packages.length === 0) {
    return (
      <div className="py-4 text-center">
        <p className="text-[10px] text-gray-400 animate-pulse">Loading packages...</p>
      </div>
    );
  }

  if (error && packages.length === 0) {
    return (
      <div className="py-4 text-center">
        <p className="text-[10px] text-red-400">Failed to load packages</p>
        <button onClick={refetch} className="text-[10px] text-blue-500 hover:underline mt-1">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-[10px] font-medium text-gray-400 uppercase tracking-wider">
          My Packages
          {packages.length > 0 && (
            <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-[9px] bg-gray-200 text-gray-600 font-bold">
              {packages.length}
            </span>
          )}
        </h4>
        <button
          onClick={refetch}
          className="p-1 text-gray-400 hover:text-gray-600 rounded transition"
          title="Refresh packages"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {filteredPackages.length === 0 && !activePackageId && (
        <p className="text-[10px] text-gray-400 text-center py-2">No packages yet.</p>
      )}

      <div className="space-y-1.5">
        {filteredPackages.map((pkg) => (
          <PackageCard
            key={pkg.package_id}
            pkg={pkg}
            isExpanded={expandedPkg === pkg.package_id}
            onToggle={() => handleToggle(pkg.package_id)}
            onDelete={
              ['intake', 'drafting'].includes(pkg.status ?? '')
                ? () => removePackage(pkg.package_id)
                : undefined
            }
            documents={documentsCache[pkg.package_id] ?? []}
            isLoadingDocs={loadingDocs.has(pkg.package_id)}
          />
        ))}
      </div>
    </div>
  );
}

function DocumentsTab({
  documents,
  sessionId,
}: {
  documents: Record<string, DocumentInfo[]>;
  sessionId?: string;
}) {
  const allDocs = Object.values(documents).flat();

  const openDoc = (doc: DocumentInfo) => {
    const raw = doc.s3_key || doc.document_id || doc.title;
    const docId = encodeURIComponent(raw);
    const params = new URLSearchParams();
    if (sessionId) params.set('session', sessionId);
    window.open(`/documents/${docId}?${params.toString()}`, '_blank');
  };

  if (allDocs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <FileText className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No documents generated yet.</p>
        <p className="text-xs text-gray-400 mt-1">
          Documents will appear here as they&apos;re created.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {allDocs.map((doc, i) => (
        <button
          key={doc.document_id ?? i}
          type="button"
          onClick={() => openDoc(doc)}
          className="w-full text-left rounded-lg border border-[#D8DEE6] bg-white p-3 hover:shadow-sm transition"
          title="Open document"
        >
          <div className="flex items-start gap-2">
            <span className="text-lg shrink-0">{getDocIcon(doc.document_type)}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-[#003366] truncate">
                {doc.title.replace(/\.md$/i, '')}
              </p>
              <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
                <span className="uppercase font-medium">{getDocTypeLabel(doc)}</span>
                {doc.word_count && <span>&middot; {doc.word_count.toLocaleString()} words</span>}
                {doc.status && (
                  <span
                    className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${
                      doc.status === 'saved'
                        ? 'bg-green-100 text-green-700'
                        : doc.status === 'template'
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {doc.status}
                  </span>
                )}
              </div>
              {doc.generated_at && (
                <p className="text-[10px] text-gray-400 mt-0.5">
                  {new Date(doc.generated_at).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              )}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

/** Notification entry for document & package updates. */
interface Notification {
  id: string;
  icon: 'doc_created' | 'doc_updated' | 'pkg_created';
  title: string;
  detail: string;
  status?: string;
  timestamp: string;
}

/** Document types that are part of an acquisition package vs standalone docs. */
const PACKAGE_DOC_TYPES = new Set([
  'sow',
  'igce',
  'acquisition_plan',
  'justification',
  'eval_criteria',
]);

function NotificationsTab({ documents }: { documents: Record<string, DocumentInfo[]> }) {
  const notifications = useMemo(() => {
    const items: Notification[] = [];
    const allDocs = Object.values(documents).flat();

    // Track package doc types seen — if multiple, it's a package update
    const packageTypes = allDocs.filter((d) => PACKAGE_DOC_TYPES.has(d.document_type));

    // Package-level notification if 2+ package docs exist
    if (packageTypes.length >= 2) {
      const latest = packageTypes.reduce((a, b) =>
        new Date(b.generated_at ?? 0).getTime() > new Date(a.generated_at ?? 0).getTime() ? b : a,
      );
      items.push({
        id: 'pkg-update',
        icon: 'pkg_created',
        title: 'Acquisition package updated',
        detail: `${packageTypes.length} documents — ${packageTypes.map((d) => d.document_type.replace(/_/g, ' ')).join(', ')}`,
        timestamp: latest.generated_at ?? new Date().toISOString(),
      });
    }

    // Individual document notifications
    for (const doc of allDocs) {
      items.push({
        id: `doc-${doc.document_id ?? doc.title}`,
        icon: 'doc_created',
        title: doc.title,
        detail: doc.document_type.replace(/_/g, ' '),
        status: doc.status,
        timestamp: doc.generated_at ?? new Date().toISOString(),
      });
    }

    // Sort newest first
    items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    return items;
  }, [documents]);

  if (notifications.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <Bell className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No notifications yet.</p>
        <p className="text-xs text-gray-400 mt-1">Document and package updates will appear here.</p>
      </div>
    );
  }

  const iconStyles: Record<Notification['icon'], { bg: string; glyph: string }> = {
    doc_created: { bg: 'bg-blue-100', glyph: '\u{1F4C4}' },
    doc_updated: { bg: 'bg-amber-100', glyph: '\u{1F4DD}' },
    pkg_created: { bg: 'bg-indigo-100', glyph: '\u{1F4E6}' },
  };

  return (
    <div className="space-y-1.5">
      {notifications.map((n) => {
        const style = iconStyles[n.icon];
        return (
          <div
            key={n.id}
            className="flex items-start gap-2.5 rounded-lg border border-[#D8DEE6] bg-white px-3 py-2.5 hover:shadow-sm transition"
          >
            <span
              className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-sm ${style.bg}`}
            >
              {style.glyph}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-[#003366]">{n.title}</p>
              <p className="text-[11px] text-gray-500 truncate">{n.detail}</p>
              <div className="flex items-center gap-2 mt-0.5">
                {n.status && (
                  <span
                    className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${
                      n.status === 'saved'
                        ? 'bg-green-100 text-green-700'
                        : n.status === 'template'
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {n.status}
                  </span>
                )}
                <p className="text-[10px] text-gray-400">
                  {new Date(n.timestamp).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sources Tab — surfaces all documents the system read
// ---------------------------------------------------------------------------

const SOURCE_DOC_TYPE_ICONS: Record<string, string> = {
  template: '\u{1F4DD}',    // memo
  checklist: '\u{2705}',    // checkmark
  regulation: '\u{2696}',   // scales
  guidance: '\u{1F4D8}',    // blue book
  policy: '\u{1F3DB}',      // classical building
  document: '\u{1F4C4}',    // page
  memo: '\u{1F4E8}',        // envelope
  reference: '\u{1F4DA}',   // books
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

const SOURCE_GROUP_ORDER = ['regulation', 'checklist', 'template', 'guidance', 'policy', 'document', 'memo', 'reference'];

interface SourcesTabContentProps {
  stateChangesByMsg: Record<string, StateChangeEntry[]>;
}

function SourcesTabContent({ stateChangesByMsg }: SourcesTabContentProps) {
  const sources = useMemo(() => {
    const seen = new Set<string>();
    const result: StateChangeEntry[] = [];
    for (const entries of Object.values(stateChangesByMsg)) {
      for (const entry of entries) {
        if (entry.stateType !== 'sources_read') continue;
        const key = entry.sourceS3Key || entry.sourceTitle || '';
        if (key && seen.has(key)) continue;
        if (key) seen.add(key);
        result.push(entry);
      }
    }
    return result;
  }, [stateChangesByMsg]);

  // Summary entry (if present)
  const summary = useMemo(() => {
    for (const entries of Object.values(stateChangesByMsg)) {
      for (const entry of entries) {
        if (entry.stateType === 'sources_summary') return entry;
      }
    }
    return null;
  }, [stateChangesByMsg]);

  // Group by docType
  const grouped = useMemo(() => {
    const groups: Record<string, StateChangeEntry[]> = {};
    for (const src of sources) {
      const dt = src.sourceDocType || 'document';
      if (!groups[dt]) groups[dt] = [];
      groups[dt].push(src);
    }
    return groups;
  }, [sources]);

  const totalChars = summary?.totalCharsRead ?? sources.reduce((sum, s) => sum + (s.sourceCharsRead ?? 0), 0);

  if (sources.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400">
        <BookOpenText className="w-8 h-8 mb-2 opacity-50" />
        <p className="text-xs">No documents read yet</p>
        <p className="text-[10px] mt-1">Sources will appear here as the agent reads documents</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary header */}
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-medium text-[#003366]">
          {sources.length} source{sources.length !== 1 ? 's' : ''} read
        </span>
        <span className="text-[10px] text-gray-400">
          {totalChars.toLocaleString()} chars total
        </span>
      </div>

      {/* Grouped source list */}
      {SOURCE_GROUP_ORDER.filter((dt) => grouped[dt]).map((dt) => {
        const style = SOURCE_DOC_TYPE_STYLES[dt] ?? SOURCE_DOC_TYPE_STYLES.document;
        const items = grouped[dt];
        return (
          <div key={dt}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-sm">{SOURCE_DOC_TYPE_ICONS[dt] ?? '\u{1F4C4}'}</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${style.bg} ${style.text}`}>
                {style.label}
              </span>
              <span className="text-[10px] text-gray-400">({items.length})</span>
            </div>
            <ul className="space-y-1 ml-1">
              {items.map((src, i) => (
                <li
                  key={src.sourceS3Key || i}
                  className="flex items-start gap-2 text-xs px-2 py-1.5 rounded-md hover:bg-gray-50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-gray-700 font-medium truncate">{src.sourceTitle || 'Untitled'}</p>
                    {src.sourceS3Key && (
                      <p className="font-mono text-[10px] text-gray-400 truncate">
                        {src.sourceS3Key.includes('/') ? src.sourceS3Key.split('/').pop() : src.sourceS3Key}
                      </p>
                    )}
                  </div>
                  {src.sourceCharsRead != null && src.sourceCharsRead > 0 && (
                    <span className="text-[10px] text-gray-400 whitespace-nowrap shrink-0">
                      {src.sourceCharsRead.toLocaleString()} chars
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export default function ActivityPanel({
  logs,
  clearLogs,
  documents,
  sessionId,
  isStreaming,
  isOpen,
  onToggle,
  packageState,
  getToken,
  onRefreshPackage,
  isRefreshingPackage,
  stateChangesByMsg,
}: ActivityPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('package');
  const [viewerDocType, setViewerDocType] = useState<string | null>(null);

  const docCount = Object.values(documents).flat().length;
  const logDisplayCount = useMemo(() => buildDisplayEntries(logs).length, [logs]);
  const notifCount = docCount;
  const packageRequired = packageState?.checklist?.required?.length ?? 0;
  const packageCompleted = packageState?.checklist?.completed?.length ?? 0;

  // Count unique sources for badge
  const sourcesCount = useMemo(() => {
    if (!stateChangesByMsg) return 0;
    const seen = new Set<string>();
    for (const entries of Object.values(stateChangesByMsg)) {
      for (const entry of entries) {
        if (entry.stateType !== 'sources_read') continue;
        const key = entry.sourceS3Key || entry.sourceTitle || '';
        if (key) seen.add(key);
      }
    }
    return seen.size;
  }, [stateChangesByMsg]);

  // Collapsed strip
  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="w-9 shrink-0 border-l border-[#D8DEE6] bg-[#F5F7FA] hover:bg-[#EDF0F4] transition flex flex-col items-center justify-center gap-1.5 cursor-pointer"
        title="Open panel"
      >
        <PanelRightOpen className="w-4 h-4 text-gray-400" />
      </button>
    );
  }

  return (
    <div className="w-[380px] shrink-0 border-l border-[#D8DEE6] bg-white flex flex-col">
      {/* Tab bar */}
      <div className="flex items-center gap-1 p-2 bg-[#F5F7FA] border-b border-[#D8DEE6] overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const badge =
            tab.id === 'package' && packageRequired > 0
              ? `${packageCompleted}/${packageRequired}`
              : tab.id === 'sources' && sourcesCount > 0
                ? sourcesCount
                : tab.id === 'logs' && logDisplayCount > 0
                  ? logDisplayCount
                  : tab.id === 'documents' && docCount > 0
                    ? docCount
                    : tab.id === 'notifications' && notifCount > 0
                      ? notifCount
                      : 0;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium transition shrink-0 ${
                activeTab === tab.id
                  ? 'bg-white text-[#003366] shadow-sm border border-[#D8DEE6]'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-white/50'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
              {(typeof badge === 'string' || badge > 0) && (
                <span className="ml-0.5 px-1.5 py-0.5 rounded-full text-[9px] bg-[#003366] text-white font-bold min-w-[18px] text-center">
                  {badge}
                </span>
              )}
            </button>
          );
        })}

        {/* Collapse toggle */}
        <button
          onClick={onToggle}
          className="ml-auto p-1 text-gray-400 hover:text-gray-600 rounded transition"
          title="Collapse panel"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      {/* Tab-specific header (Agent Logs clear button) */}
      {activeTab === 'logs' && logDisplayCount > 0 && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#D8DEE6]">
          <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wider">
            {logDisplayCount} event{logDisplayCount !== 1 ? 's' : ''}
            {isStreaming && (
              <span className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            )}
          </span>
          <button
            onClick={clearLogs}
            className="text-[10px] text-red-500 hover:text-red-700 font-medium"
          >
            Clear
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab === 'package' && (
          <>
            {/* Section A: Active package checklist (from SSE) */}
            {packageState && (
              <ChecklistTabContent
                state={packageState}
                onDocumentClick={setViewerDocType}
              />
            )}

            {/* Refresh: scan chat for latest document and link active package */}
            {onRefreshPackage && (
              <div className={packageState?.packageId ? 'mt-2 mb-1' : 'mb-3'}>
                <button
                  onClick={onRefreshPackage}
                  disabled={isRefreshingPackage || isStreaming}
                  className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-medium rounded-md border border-[#D8DEE6] text-gray-500 hover:text-[#003366] hover:border-[#003366] hover:bg-blue-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  title="Scan chat for the most recent document and link the active package"
                >
                  <RefreshCw className={`w-3 h-3 ${isRefreshingPackage ? 'animate-spin' : ''}`} />
                  <span>{isRefreshingPackage ? 'Detecting...' : 'Detect Package from Chat'}</span>
                </button>
              </div>
            )}

            {/* Divider between active checklist and all packages */}
            {packageState?.packageId && <div className="border-t border-[#D8DEE6] my-4" />}

            {/* Section B: All packages from API */}
            <AllPackagesList
              getToken={getToken}
              activePackageId={packageState?.packageId ?? undefined}
              isStreaming={isStreaming}
              hasActiveChecklist={!!packageState?.checklist}
            />
          </>
        )}
        {activeTab === 'documents' && <DocumentsTab documents={documents} sessionId={sessionId} />}
        {activeTab === 'sources' && stateChangesByMsg && (
          <SourcesTabContent stateChangesByMsg={stateChangesByMsg} />
        )}
        {activeTab === 'notifications' && <NotificationsTab documents={documents} />}
        {activeTab === 'logs' && <AgentLogs logs={logs} />}
      </div>

      {/* Document viewer modal — opened by clicking completed checklist items */}
      <DocumentViewerModal
        isOpen={!!viewerDocType}
        onClose={() => setViewerDocType(null)}
        packageId={packageState?.packageId ?? ''}
        docType={viewerDocType ?? ''}
        docLabel={docLabel(viewerDocType ?? '')}
        getToken={getToken}
        completedDocTypes={packageState?.checklist?.completed}
      />
    </div>
  );
}
