'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { X, Copy, Check, Code, ChevronRight, ChevronDown, Download } from 'lucide-react';

// ---------------------------------------------------------------------------
// Collapsible JSON Tree
// ---------------------------------------------------------------------------

function JsonTree({ data, depth = 0 }: { data: unknown; depth?: number }) {
  const [collapsed, setCollapsed] = useState(depth > 2);

  if (data === null) return <span className="text-gray-400">null</span>;
  if (data === undefined) return <span className="text-gray-400">undefined</span>;
  if (typeof data === 'boolean') return <span className="text-blue-400">{String(data)}</span>;
  if (typeof data === 'number') return <span className="text-amber-400">{data}</span>;
  if (typeof data === 'string') {
    if (data.length > 300) {
      return (
        <span className="text-green-400">
          &quot;{collapsed ? data.slice(0, 120) + '...' : data}&quot;
          {data.length > 120 && (
            <button
              onClick={() => setCollapsed(!collapsed)}
              className="ml-1 text-[9px] text-gray-500 hover:text-gray-300 underline"
            >
              {collapsed ? `(${data.length} chars)` : 'collapse'}
            </button>
          )}
        </span>
      );
    }
    return <span className="text-green-400">&quot;{data}&quot;</span>;
  }

  if (Array.isArray(data)) {
    if (data.length === 0) return <span className="text-gray-500">[]</span>;
    return (
      <span>
        <button onClick={() => setCollapsed(!collapsed)} className="text-gray-500 hover:text-gray-300 inline-flex items-center">
          {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          <span className="text-gray-500">[{collapsed ? `${data.length} items` : ''}]</span>
        </button>
        {!collapsed && (
          <div className="ml-4 border-l border-gray-700 pl-2">
            {data.map((item, i) => (
              <div key={i} className="py-0.5">
                <span className="text-gray-600 mr-1">{i}:</span>
                <JsonTree data={item} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
        {!collapsed && <span className="text-gray-500">]</span>}
      </span>
    );
  }

  if (typeof data === 'object') {
    const keys = Object.keys(data as Record<string, unknown>);
    if (keys.length === 0) return <span className="text-gray-500">{'{}'}</span>;
    return (
      <span>
        <button onClick={() => setCollapsed(!collapsed)} className="text-gray-500 hover:text-gray-300 inline-flex items-center">
          {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          <span className="text-gray-500">{'{'}{collapsed ? `${keys.length} keys` : ''}</span>
        </button>
        {!collapsed && (
          <div className="ml-4 border-l border-gray-700 pl-2">
            {keys.map((key) => (
              <div key={key} className="py-0.5">
                <span className="text-purple-400">&quot;{key}&quot;</span>
                <span className="text-gray-500">: </span>
                <JsonTree data={(data as Record<string, unknown>)[key]} depth={depth + 1} />
              </div>
            ))}
          </div>
        )}
        {!collapsed && <span className="text-gray-500">{'}'}</span>}
      </span>
    );
  }

  return <span className="text-gray-400">{String(data)}</span>;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ViewMode = 'formatted' | 'raw' | 'tree';

export interface TraceDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** The raw JSON data to display. */
  data: unknown;
  /** Header content rendered above the view toggle. */
  header?: React.ReactNode;
  /** Formatted view — rendered when view mode is 'formatted'. */
  formattedView?: React.ReactNode;
  /** Title for the download file. */
  downloadFilename?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TraceDetailModal({
  isOpen,
  onClose,
  data,
  header,
  formattedView,
  downloadFilename = 'trace.json',
}: TraceDetailModalProps) {
  const [viewMode, setViewMode] = useState<ViewMode>(formattedView ? 'formatted' : 'raw');
  const [copied, setCopied] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleEsc);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleEsc);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  const jsonStr = useMemo(() => JSON.stringify(data, null, 2), [data]);

  if (!isOpen) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(jsonStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = downloadFilename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const viewButtons: { mode: ViewMode; label: string }[] = [
    ...(formattedView ? [{ mode: 'formatted' as ViewMode, label: 'Formatted' }] : []),
    { mode: 'raw', label: 'Raw JSON' },
    { mode: 'tree', label: 'Tree View' },
  ];

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => e.target === overlayRef.current && onClose()}
    >
      <div
        className="max-w-[90vw] w-full max-h-[85vh] bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {header && (
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between shrink-0">
            <div className="flex items-center gap-2 min-w-0 flex-1">{header}</div>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors shrink-0 ml-3"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center justify-between px-5 py-2 border-b border-gray-100 bg-gray-50 shrink-0">
          {/* View mode toggle */}
          <div className="flex items-center gap-1 bg-gray-200 rounded-lg p-0.5">
            {viewButtons.map(({ mode, label }) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  viewMode === mode
                    ? 'bg-white text-[#003366] shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2.5 py-1 text-xs bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
            >
              {copied ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Copied!' : 'Copy'}
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-1 px-2.5 py-1 text-xs bg-white border border-gray-200 hover:bg-gray-50 rounded-lg transition-colors"
            >
              <Download className="w-3 h-3" />
              Download
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5">
          {viewMode === 'formatted' && formattedView}

          {viewMode === 'raw' && (
            <pre className="bg-gray-900 text-green-400 p-5 rounded-xl text-xs font-mono whitespace-pre-wrap break-all leading-relaxed">
              {jsonStr}
            </pre>
          )}

          {viewMode === 'tree' && (
            <div className="bg-gray-900 p-5 rounded-xl text-xs font-mono leading-relaxed">
              <JsonTree data={data} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
