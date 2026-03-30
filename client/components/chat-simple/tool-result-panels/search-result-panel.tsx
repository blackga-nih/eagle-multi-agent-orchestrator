'use client';

import MarkdownResultPanel from './markdown-result-panel';

interface SearchItem {
  title?: string;
  name?: string;
  section?: string;
  part?: string;
  description?: string;
  summary?: string;
  applicability?: string;
  url?: string;
  link?: string;
}

/** Extract an array of result items from various backend shapes. */
function extractItems(data: unknown): SearchItem[] | null {
  if (Array.isArray(data)) return data;
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    // search_far returns { clauses: [...] }
    if (Array.isArray(obj.clauses)) return obj.clauses;
    // Other shapes: { results: [...] }, { items: [...] }
    if (Array.isArray(obj.results)) return obj.results;
    if (Array.isArray(obj.items)) return obj.items;
  }
  return null;
}

export default function SearchResultPanel({ text }: { text: string }) {
  try {
    const data = JSON.parse(text);
    const items = extractItems(data);

    if (items && items.length > 0) {
      // Header with result count
      const count =
        data && typeof data === 'object' && (data as Record<string, unknown>).results_count
          ? Number((data as Record<string, unknown>).results_count)
          : items.length;

      return (
        <div className="border-t border-[#E5E9F0] bg-white">
          <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
            <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">
              Policy Lookup
            </span>
            <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
              {count} result{count !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="overflow-y-auto max-h-64 divide-y divide-gray-100">
            {items.map((item: SearchItem, idx: number) => {
              const title = item.title || item.name || `Result ${idx + 1}`;
              const desc = item.summary || item.description || item.applicability || '';
              const section = item.section || (item.part ? `Part ${item.part}` : '');

              return (
                <div
                  key={idx}
                  className="flex items-start gap-3 px-3 py-2 hover:bg-blue-50/50 transition-colors"
                >
                  <span className="text-xs shrink-0 mt-0.5">{'📖'}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-gray-800">{title}</p>
                    {desc && (
                      <p className="text-[10px] text-gray-500 mt-0.5 line-clamp-2">{desc}</p>
                    )}
                  </div>
                  {section && (
                    <span className="text-[9px] text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                      {section}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      );
    }
  } catch {
    // Not structured JSON — fall through to markdown
  }
  return <MarkdownResultPanel text={text} />;
}
