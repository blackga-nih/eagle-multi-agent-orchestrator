'use client';

interface WebSource {
  url: string;
  domain?: string;
  snippet?: string;
}

interface WebSearchData {
  query?: string;
  answer?: string;
  sources?: WebSource[];
  source_count?: number;
}

/** Parse web search result JSON into structured data. */
function parseData(text: string): WebSearchData | null {
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === 'object' && !parsed.error) return parsed;
    return null;
  } catch {
    return null;
  }
}

export default function WebSearchPanel({ text }: { text: string }) {
  const data = parseData(text);
  if (!data) {
    return (
      <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-48 overflow-y-auto">
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">
          {text}
        </pre>
      </div>
    );
  }

  const sources = data.sources ?? [];
  const sourceCount = data.source_count ?? sources.length;
  const answer = data.answer ?? '';
  const truncatedAnswer = answer.length > 200 ? answer.slice(0, 200) + '...' : answer;

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      {/* Answer preview */}
      {truncatedAnswer && (
        <div className="px-3 py-1.5 border-b border-gray-100">
          <p className="text-[11px] text-gray-600 leading-relaxed line-clamp-3">
            {truncatedAnswer}
          </p>
        </div>
      )}

      {/* Sources list */}
      {sources.length > 0 && (
        <>
          <div className="px-3 py-1 border-b border-gray-100 flex items-center gap-2">
            <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">
              Sources
            </span>
            <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
              {sourceCount}
            </span>
          </div>
          <div className="overflow-y-auto max-h-32 divide-y divide-gray-100">
            {sources.slice(0, 5).map((source, i) => {
              let displayDomain = source.domain || '';
              if (!displayDomain && source.url) {
                try {
                  displayDomain = new URL(source.url).hostname;
                } catch {
                  displayDomain = source.url;
                }
              }
              return (
                <div
                  key={i}
                  className="flex items-center gap-2 px-3 py-1 hover:bg-blue-50/50 transition-colors"
                >
                  <span className="text-[10px] text-gray-400 shrink-0 w-3 text-right">
                    {i + 1}.
                  </span>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] text-blue-600 hover:text-blue-800 hover:underline truncate min-w-0"
                    title={source.url}
                  >
                    {displayDomain}
                  </a>
                </div>
              );
            })}
          </div>
          {sourceCount > 5 && (
            <div className="px-3 py-1 border-t border-gray-100">
              <span className="text-[10px] text-gray-400">+{sourceCount - 5} more</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
