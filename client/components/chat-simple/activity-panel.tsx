'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { FileText, Bell, Terminal, PanelRightClose, PanelRightOpen, History, Bot, User, Braces, Copy, Check } from 'lucide-react';
import { AuditLogEntry } from '@/types/stream';
import { DocumentInfo } from '@/types/chat';
import { PackageState } from '@/hooks/use-package-state';
import AgentLogs from './agent-logs';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Changelog entry from the API */
interface ChangelogEntry {
  changelog_id: string;
  change_type: 'create' | 'update' | 'finalize';
  change_source: 'agent_tool' | 'user_edit';
  change_summary: string;
  doc_type: string;
  version: number;
  actor_user_id: string;
  created_at: string;
}

interface ActivityPanelProps {
  logs: AuditLogEntry[];
  clearLogs: () => void;
  documents: Record<string, DocumentInfo[]>;
  sessionId?: string;
  packageId?: string;
  packageState?: PackageState;
  isStreaming: boolean;
  isOpen: boolean;
  onToggle: () => void;
}

type TabId = 'documents' | 'notifications' | 'logs' | 'changelog' | 'state';

interface TabDef {
  id: TabId;
  label: string;
  icon: typeof FileText;
}

const TABS: TabDef[] = [
  { id: 'documents',     label: 'Documents',     icon: FileText },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'changelog',     label: 'Changelog',     icon: History },
  { id: 'logs',          label: 'Agent Logs',    icon: Terminal },
  { id: 'state',         label: 'State',         icon: Braces },
];

// ---------------------------------------------------------------------------
// Document type icon helper
// ---------------------------------------------------------------------------

import { DOCUMENT_TYPE_ICONS, type DocumentType } from '@/types/schema';

function getDocIcon(type: string): string {
  return DOCUMENT_TYPE_ICONS[type as DocumentType] ?? '\u{1F4C4}';
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

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
        <p className="text-xs text-gray-400 mt-1">Documents will appear here as they&apos;re created.</p>
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
              <p className="text-sm font-medium text-[#003366] truncate">{doc.title}</p>
              <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
                <span className="uppercase font-medium">{doc.document_type.replace(/_/g, ' ')}</span>
                {doc.word_count && <span>&middot; {doc.word_count.toLocaleString()} words</span>}
                {doc.status && (
                  <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${
                    doc.status === 'saved' ? 'bg-green-100 text-green-700' :
                    doc.status === 'template' ? 'bg-amber-100 text-amber-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {doc.status}
                  </span>
                )}
              </div>
              {doc.generated_at && (
                <p className="text-[10px] text-gray-400 mt-0.5">
                  {new Date(doc.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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
  'sow', 'igce', 'acquisition_plan', 'justification', 'eval_criteria',
]);

function NotificationsTab({ documents }: {
  documents: Record<string, DocumentInfo[]>;
}) {
  const notifications = useMemo(() => {
    const items: Notification[] = [];
    const allDocs = Object.values(documents).flat();

    // Track package doc types seen — if multiple, it's a package update
    const packageTypes = allDocs.filter(d => PACKAGE_DOC_TYPES.has(d.document_type));

    // Package-level notification if 2+ package docs exist
    if (packageTypes.length >= 2) {
      const latest = packageTypes.reduce((a, b) =>
        new Date(b.generated_at ?? 0).getTime() > new Date(a.generated_at ?? 0).getTime() ? b : a
      );
      items.push({
        id: 'pkg-update',
        icon: 'pkg_created',
        title: 'Acquisition package updated',
        detail: `${packageTypes.length} documents — ${packageTypes.map(d => d.document_type.replace(/_/g, ' ')).join(', ')}`,
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
    doc_created:  { bg: 'bg-blue-100',   glyph: '\u{1F4C4}' },
    doc_updated:  { bg: 'bg-amber-100',  glyph: '\u{1F4DD}' },
    pkg_created:  { bg: 'bg-indigo-100', glyph: '\u{1F4E6}' },
  };

  return (
    <div className="space-y-1.5">
      {notifications.map((n) => {
        const style = iconStyles[n.icon];
        return (
          <div key={n.id} className="flex items-start gap-2.5 rounded-lg border border-[#D8DEE6] bg-white px-3 py-2.5 hover:shadow-sm transition">
            <span className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-sm ${style.bg}`}>
              {style.glyph}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-[#003366]">{n.title}</p>
              <p className="text-[11px] text-gray-500 truncate">{n.detail}</p>
              <div className="flex items-center gap-2 mt-0.5">
                {n.status && (
                  <span className={`px-1.5 py-0.5 rounded-full text-[9px] font-medium ${
                    n.status === 'saved' ? 'bg-green-100 text-green-700' :
                    n.status === 'template' ? 'bg-amber-100 text-amber-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {n.status}
                  </span>
                )}
                <p className="text-[10px] text-gray-400">
                  {new Date(n.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Format relative time (e.g., "2 hours ago") */
function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function ChangelogTab({ packageId }: { packageId?: string }) {
  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!packageId) return;

    const fetchChangelog = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`/api/packages/${packageId}/changelog?limit=50`);
        if (!res.ok) throw new Error('Failed to fetch changelog');
        const data = await res.json();
        setEntries(data.entries || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load changelog');
      } finally {
        setLoading(false);
      }
    };

    fetchChangelog();
  }, [packageId]);

  if (!packageId) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <History className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No package selected.</p>
        <p className="text-xs text-gray-400 mt-1">Select a package to view its changelog.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[#003366]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <p className="text-sm text-red-500">{error}</p>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <History className="w-5 h-5 text-gray-400" />
        </div>
        <p className="text-sm text-gray-500">No changelog entries yet.</p>
        <p className="text-xs text-gray-400 mt-1">Document changes will appear here.</p>
      </div>
    );
  }

  const changeTypeStyles: Record<string, { bg: string; text: string }> = {
    create: { bg: 'bg-green-100', text: 'text-green-700' },
    update: { bg: 'bg-blue-100', text: 'text-blue-700' },
    finalize: { bg: 'bg-purple-100', text: 'text-purple-700' },
  };

  return (
    <div className="space-y-1.5">
      {entries.map((entry) => {
        const style = changeTypeStyles[entry.change_type] || { bg: 'bg-gray-100', text: 'text-gray-700' };
        const isAgent = entry.change_source === 'agent_tool';

        return (
          <div
            key={entry.changelog_id || `${entry.created_at}-${entry.doc_type}`}
            className="flex items-start gap-2.5 rounded-lg border border-[#D8DEE6] bg-white px-3 py-2.5 hover:shadow-sm transition"
          >
            <span className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-gray-100">
              {isAgent ? (
                <Bot className="w-4 h-4 text-[#003366]" />
              ) : (
                <User className="w-4 h-4 text-gray-600" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-medium uppercase ${style.bg} ${style.text}`}>
                  {entry.change_type}
                </span>
                <span className="text-[10px] text-gray-400 uppercase">
                  {entry.doc_type.replace(/_/g, ' ')} v{entry.version}
                </span>
              </div>
              <p className="text-xs text-[#003366] mt-1">{entry.change_summary}</p>
              <div className="flex items-center gap-2 mt-1">
                <p className="text-[10px] text-gray-400">
                  {formatRelativeTime(entry.created_at)} by {entry.actor_user_id}
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
// State JSON Tab
// ---------------------------------------------------------------------------

/** JSON replacer that serialises Date objects to ISO strings. */
function jsonReplacer(_key: string, value: unknown) {
  if (value instanceof Date) return value.toISOString();
  return value;
}

function StateTab({ packageState }: { packageState?: PackageState }) {
  const [copied, setCopied] = useState(false);

  const jsonText = useMemo(
    () => JSON.stringify(packageState ?? null, jsonReplacer, 2),
    [packageState],
  );

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(jsonText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [jsonText]);

  const hasActivePackage = !!packageState?.packageId;

  return (
    <div className="flex flex-col h-full">
      {/* Header with copy button */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wider">
            Package State
          </span>
          {hasActivePackage && (
            <span className="w-2 h-2 rounded-full bg-green-400" title="Active package" />
          )}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-400 hover:text-gray-600 rounded transition"
          title="Copy to clipboard"
        >
          {copied ? <Check className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      {/* JSON viewer */}
      <div className="flex-1 overflow-auto rounded-lg">
        <pre className="text-xs font-mono bg-gray-900 text-green-400 p-3 rounded-lg whitespace-pre-wrap break-words min-h-[200px]">
          {jsonText}
        </pre>
      </div>
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
  packageId,
  packageState,
  isStreaming,
  isOpen,
  onToggle,
}: ActivityPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('logs');
  const [changelogCount, setChangelogCount] = useState(0);

  // Fetch changelog count when packageId changes
  useEffect(() => {
    if (!packageId) {
      setChangelogCount(0);
      return;
    }

    fetch(`/api/packages/${packageId}/changelog?limit=1`)
      .then(res => res.ok ? res.json() : { count: 0 })
      .then(data => setChangelogCount(data.count || 0))
      .catch(() => setChangelogCount(0));
  }, [packageId]);

  const docCount = Object.values(documents).flat().length;

  const notifCount = docCount;

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
          const hasActiveState = tab.id === 'state' && !!packageState?.packageId;
          const badge =
            tab.id === 'logs' && logs.length > 0 ? logs.length :
            tab.id === 'documents' && docCount > 0 ? docCount :
            tab.id === 'notifications' && notifCount > 0 ? notifCount :
            tab.id === 'changelog' && changelogCount > 0 ? changelogCount :
            0;

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
              {badge > 0 && (
                <span className="ml-0.5 px-1.5 py-0.5 rounded-full text-[9px] bg-[#003366] text-white font-bold min-w-[18px] text-center">
                  {badge}
                </span>
              )}
              {hasActiveState && (
                <span className="ml-0.5 w-2 h-2 rounded-full bg-green-400" />
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
      {activeTab === 'logs' && logs.length > 0 && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-[#D8DEE6]">
          <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wider">
            {logs.length} event{logs.length !== 1 ? 's' : ''}
            {isStreaming && <span className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />}
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
        {activeTab === 'documents' && <DocumentsTab documents={documents} sessionId={sessionId} />}
        {activeTab === 'notifications' && <NotificationsTab documents={documents} />}
        {activeTab === 'changelog' && <ChangelogTab packageId={packageId} />}
        {activeTab === 'logs' && <AgentLogs logs={logs} />}
        {activeTab === 'state' && <StateTab packageState={packageState} />}
      </div>
    </div>
  );
}
