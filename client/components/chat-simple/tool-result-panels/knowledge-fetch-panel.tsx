'use client';

import ReactMarkdown from 'react-markdown';
import { stripMetadata } from './markdown-result-panel';

interface FetchData {
  document_id?: string;
  content?: string;
  s3_key?: string;
  title?: string;
}

export default function KnowledgeFetchPanel({ text }: { text: string }) {
  let data: FetchData = {};
  let content = '';

  try {
    const parsed = JSON.parse(text);
    if (typeof parsed === 'object' && parsed !== null) {
      data = parsed;
      content = String(data.content || '');
    }
  } catch {
    // Plain text — use as-is
    content = text;
  }

  if (!content) {
    return (
      <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">
          {text}
        </pre>
      </div>
    );
  }

  // Extract filename from document_id or s3_key
  const docPath = data.document_id || data.s3_key || '';
  const filename = docPath.split('/').pop() || data.title || 'Document';

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      {/* Header with filename */}
      <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
        <span className="text-[10px] font-mono text-gray-600 truncate">{filename}</span>
        <span className="text-[10px] text-gray-400 ml-auto">
          {content.length.toLocaleString()} chars
        </span>
      </div>
      <div className="relative">
        <div className="overflow-y-auto max-h-64 px-3 py-2">
          <div
            className="prose prose-xs prose-gray max-w-none text-[11px] leading-relaxed
                          [&_h1]:text-xs [&_h1]:font-bold [&_h1]:mt-2 [&_h1]:mb-1
                          [&_h2]:text-[11px] [&_h2]:font-bold [&_h2]:mt-2 [&_h2]:mb-1
                          [&_h3]:text-[11px] [&_h3]:font-semibold [&_h3]:mt-1.5 [&_h3]:mb-0.5
                          [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0
                          [&_code]:text-[10px] [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded"
          >
            <ReactMarkdown>{stripMetadata(content.slice(0, 5000))}</ReactMarkdown>
          </div>
        </div>
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent" />
      </div>
    </div>
  );
}
