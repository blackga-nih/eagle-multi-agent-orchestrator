'use client';

interface KnowledgeResult {
  title?: string;
  summary?: string;
  topic?: string;
  primary_topic?: string;
  document_type?: string;
  confidence?: number;
  confidence_score?: number;
  score?: number;
  s3_key?: string;
}

export default function KnowledgeSearchPanel({ text }: { text: string }) {
  let results: KnowledgeResult[] = [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      results = parsed;
    } else if (parsed.results && Array.isArray(parsed.results)) {
      results = parsed.results;
    } else if (parsed.documents && Array.isArray(parsed.documents)) {
      results = parsed.documents;
    } else if (parsed.matches && Array.isArray(parsed.matches)) {
      results = parsed.matches;
    } else if (parsed.title || parsed.summary || parsed.document_id) {
      // Single result object
      results = [parsed];
    }
  } catch {
    // Can't parse — fall back to raw
    return (
      <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">{text}</pre>
      </div>
    );
  }

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
        <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">Knowledge Search</span>
        <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
          {results.length} result{results.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="overflow-y-auto max-h-64 divide-y divide-gray-100">
        {results.map((item, idx) => {
          const confidence = item.confidence_score ?? item.confidence ?? item.score;
          const topic = item.primary_topic || item.topic || item.document_type || '';
          const summary = item.summary ?? '';
          const truncated = summary.length > 150 ? summary.slice(0, 150) + '...' : summary;
          return (
            <div key={idx} className="px-3 py-1.5">
              <div className="flex items-center gap-2">
                <p className="text-xs font-medium text-gray-800 truncate flex-1">
                  {item.title || `Result ${idx + 1}`}
                </p>
                {topic && (
                  <span className="text-[9px] bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded-full shrink-0">
                    {topic}
                  </span>
                )}
                {confidence != null && (
                  <span className="text-[9px] text-gray-400 shrink-0">
                    {Math.round(confidence * 100)}%
                  </span>
                )}
              </div>
              {truncated && (
                <p className="text-[10px] text-gray-500 mt-0.5">{truncated}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
