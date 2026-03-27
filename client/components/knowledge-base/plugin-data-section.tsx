'use client';

import { useState, useEffect, useCallback } from 'react';
import { Database, FileJson, Loader2, Search, ChevronRight } from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import Modal from '@/components/ui/modal';
import Badge from '@/components/ui/badge';

interface PluginFile {
  name: string;
  description: string;
  size_bytes: number;
  item_count: number;
}

const fileIcons: Record<string, React.ReactNode> = {
  'far-database.json': <Database className="w-5 h-5" />,
  'matrix.json': <FileJson className="w-5 h-5" />,
  'thresholds.json': <FileJson className="w-5 h-5" />,
  'contract-vehicles.json': <FileJson className="w-5 h-5" />,
};

export default function PluginDataSection() {
  const { getToken } = useAuth();
  const [files, setFiles] = useState<PluginFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<unknown>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const token = await getToken();
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const res = await fetch('/api/knowledge-base/plugin-data', { headers });
        if (res.ok) {
          const data = await res.json();
          setFiles(data.files || []);
        }
      } catch {
        // silently fail
      } finally {
        setLoading(false);
      }
    })();
  }, [getToken]);

  const openFile = useCallback(
    async (name: string) => {
      setSelectedFile(name);
      setContentLoading(true);
      setFileContent(null);
      setSearchQuery('');
      try {
        const token = await getToken();
        const headers: Record<string, string> = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const res = await fetch(
          `/api/knowledge-base/plugin-data?file=${encodeURIComponent(name)}`,
          { headers },
        );
        if (res.ok) {
          const data = await res.json();
          setFileContent(data.content);
        }
      } catch {
        setFileContent(null);
      } finally {
        setContentLoading(false);
      }
    },
    [getToken],
  );

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
            <div className="h-5 bg-gray-200 rounded w-2/3 mb-3" />
            <div className="h-3 bg-gray-100 rounded w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {files.map((file) => (
          <button
            key={file.name}
            onClick={() => openFile(file.name)}
            className="text-left bg-white rounded-xl border border-gray-200 p-5 hover:border-blue-300 hover:shadow-md transition-all group"
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-amber-50 text-amber-600 shrink-0">
                {fileIcons[file.name] || <FileJson className="w-5 h-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                  {file.name}
                </h3>
                <p className="text-sm text-gray-500 mt-1">{file.description}</p>
                <div className="flex items-center gap-3 mt-3 text-xs text-gray-400">
                  <span>{formatBytes(file.size_bytes)}</span>
                  <span>{file.item_count} items</span>
                </div>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-300 group-hover:text-blue-400 mt-1" />
            </div>
          </button>
        ))}
      </div>

      {/* File content modal */}
      <Modal
        isOpen={!!selectedFile}
        onClose={() => {
          setSelectedFile(null);
          setFileContent(null);
        }}
        title={selectedFile || ''}
        size="xl"
      >
        {contentLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            <span className="ml-2 text-gray-500">Loading...</span>
          </div>
        ) : fileContent !== null ? (
          <PluginFileViewer
            name={selectedFile!}
            content={fileContent}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
          />
        ) : (
          <p className="text-gray-400">Failed to load file content.</p>
        )}
      </Modal>
    </>
  );
}

function PluginFileViewer({
  name,
  content,
  searchQuery,
  onSearchChange,
}: {
  name: string;
  content: unknown;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}) {
  // FAR database: render as searchable table
  if (name === 'far-database.json' && Array.isArray(content)) {
    const filtered = searchQuery
      ? content.filter((item: Record<string, unknown>) => {
          const text = JSON.stringify(item).toLowerCase();
          return text.includes(searchQuery.toLowerCase());
        })
      : content;

    return (
      <div>
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search FAR clauses..."
            className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="text-xs text-gray-400 mb-2">
          Showing {filtered.length} of {content.length} clauses
        </div>
        <div className="max-h-[500px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-50">
              <tr className="text-left text-xs text-gray-500 uppercase tracking-wide">
                <th className="px-3 py-2">Part</th>
                <th className="px-3 py-2">Section</th>
                <th className="px-3 py-2">Title</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 200).map((item: Record<string, unknown>, i: number) => (
                <tr key={i} className="border-t border-gray-100 hover:bg-blue-50">
                  <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                    {String(item.part || '')}
                  </td>
                  <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                    {String(item.section || '')}
                  </td>
                  <td className="px-3 py-2 text-gray-900">
                    {String(item.title || item.name || '')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length > 200 && (
            <p className="text-xs text-gray-400 text-center py-2">Showing first 200 results</p>
          )}
        </div>
      </div>
    );
  }

  // Matrix / thresholds / contract-vehicles: render as formatted JSON with key sections
  if (typeof content === 'object' && content !== null && !Array.isArray(content)) {
    const obj = content as Record<string, unknown>;
    const keys = Object.keys(obj);

    return (
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2 mb-4">
          {keys.map((key) => (
            <Badge key={key} variant="primary">
              {key}
            </Badge>
          ))}
        </div>
        <pre className="whitespace-pre-wrap text-sm text-gray-700 bg-gray-50 rounded-lg p-4 max-h-[500px] overflow-y-auto font-mono leading-relaxed">
          {JSON.stringify(content, null, 2)}
        </pre>
      </div>
    );
  }

  // Array fallback
  if (Array.isArray(content)) {
    return (
      <div>
        <div className="text-sm text-gray-500 mb-2">{content.length} items</div>
        <pre className="whitespace-pre-wrap text-sm text-gray-700 bg-gray-50 rounded-lg p-4 max-h-[500px] overflow-y-auto font-mono leading-relaxed">
          {JSON.stringify(content, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <pre className="whitespace-pre-wrap text-sm text-gray-700 bg-gray-50 rounded-lg p-4 max-h-[500px] overflow-y-auto font-mono">
      {JSON.stringify(content, null, 2)}
    </pre>
  );
}
