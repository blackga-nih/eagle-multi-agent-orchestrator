'use client';

import MarkdownResultPanel from './markdown-result-panel';

export default function SearchResultPanel({ text }: { text: string }) {
  // Try to parse structured search results; fall back to markdown
  try {
    const data = JSON.parse(text);
    if (Array.isArray(data)) {
      return (
        <div className="border-t border-[#E5E9F0] bg-white">
          <div className="overflow-y-auto max-h-64 divide-y divide-gray-100">
            {data.map((item: Record<string, string>, idx: number) => (
              <a
                key={idx}
                href={item.url || item.link || '#'}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-3 py-2 hover:bg-blue-50/50 transition-colors"
              >
                <span className="text-xs shrink-0">{'📖'}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-gray-800 truncate">
                    {item.title || item.name || `Result ${idx + 1}`}
                  </p>
                  {item.description && (
                    <p className="text-[10px] text-gray-400 truncate">{item.description}</p>
                  )}
                </div>
                {item.section && (
                  <span className="text-[9px] text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded shrink-0">
                    {item.section}
                  </span>
                )}
              </a>
            ))}
          </div>
        </div>
      );
    }
  } catch {
    // Not structured JSON — fall through to markdown
  }
  return <MarkdownResultPanel text={text} />;
}
