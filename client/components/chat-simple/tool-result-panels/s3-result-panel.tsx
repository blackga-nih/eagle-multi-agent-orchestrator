'use client';

import ReactMarkdown from 'react-markdown';
import { stripMetadata } from './markdown-result-panel';

export default function S3ResultPanel({
  text,
  input,
}: {
  text: string;
  input: Record<string, unknown>;
}) {
  const op = String(input.operation ?? 'list');

  // List operation — parse as JSON array of files
  if (op === 'list') {
    try {
      const files = JSON.parse(text);
      if (Array.isArray(files)) {
        return (
          <div className="border-t border-[#E5E9F0] bg-white">
            <div className="overflow-y-auto max-h-48 divide-y divide-gray-100">
              {files.map((file: string, idx: number) => (
                <div key={idx} className="flex items-center gap-2 px-3 py-1.5 text-xs text-gray-700">
                  <span className="text-gray-400">{'📄'}</span>
                  <span className="truncate">{typeof file === 'string' ? file : JSON.stringify(file)}</span>
                </div>
              ))}
            </div>
            <div className="px-3 py-1.5 border-t border-gray-100 text-[10px] text-gray-400">
              {files.length} file{files.length !== 1 ? 's' : ''}
            </div>
          </div>
        );
      }
    } catch { /* fall through */ }
  }

  // Read operations — show content preview with filename header
  const key = String(input.key ?? '');
  const filename = key.split('/').pop() || 'file';
  const isMarkdown = filename.endsWith('.md');

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      {key && (
        <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
          <span className="text-[10px] text-gray-400">{op}</span>
          <span className="text-[10px] font-mono text-gray-600 truncate">{filename}</span>
          <span className="text-[10px] text-gray-400 ml-auto">{text.length.toLocaleString()} chars</span>
        </div>
      )}
      <div className="relative">
        <div className="overflow-y-auto max-h-64 px-3 py-2">
          {isMarkdown ? (
            <div className="prose prose-xs prose-gray max-w-none text-[11px] leading-relaxed
                            [&_h1]:text-xs [&_h1]:font-bold [&_h2]:text-[11px] [&_h2]:font-bold
                            [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0
                            [&_code]:text-[10px] [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded">
              <ReactMarkdown>{stripMetadata(text)}</ReactMarkdown>
            </div>
          ) : (
            <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap break-all">
              {text.slice(0, 5000)}
              {text.length > 5000 && '\n\u2026 (truncated)'}
            </pre>
          )}
        </div>
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent" />
      </div>
    </div>
  );
}
