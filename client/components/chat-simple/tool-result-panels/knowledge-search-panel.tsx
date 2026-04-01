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

interface ParsedData {
  results?: KnowledgeResult[];
  documents?: KnowledgeResult[];
  matches?: KnowledgeResult[];
  message?: string;
  query?: string;
  count?: number;
  [key: string]: unknown;
}

export default function KnowledgeSearchPanel({ text }: { text: string }) {
  let results: KnowledgeResult[] = [];
  let parsed: ParsedData | null = null;

  try {
    const raw = JSON.parse(text);
    if (Array.isArray(raw)) {
      results = raw;
    } else if (raw && typeof raw === 'object') {
      parsed = raw;
      if (Array.isArray(raw.results)) {
        results = raw.results;
      } else if (Array.isArray(raw.documents)) {
        results = raw.documents;
      } else if (Array.isArray(raw.matches)) {
        results = raw.matches;
      } else if (raw.title || raw.summary || raw.document_id) {
        results = [raw];
      }
    }
  } catch {
    return (
      <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">
          {text}
        </pre>
      </div>
    );
  }

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
        <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">
          Knowledge Search
        </span>
        <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
          {results.length} result{results.length !== 1 ? 's' : ''}
        </span>
      </div>

      {results.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <div className="text-2xl mb-2">&#x1F50D;</div>
          <p className="text-sm font-medium text-gray-700 mb-1">
            No matching documents found
          </p>
          {parsed?.message && (
            <p className="text-xs text-gray-500 mb-1">{String(parsed.message)}</p>
          )}
          {parsed?.query && (
            <p className="text-xs text-gray-400 italic mb-2">
              Query: &ldquo;{String(parsed.query)}&rdquo;
            </p>
          )}
          <p className="text-xs text-gray-400 max-w-xs mx-auto">
            Try broadening your search terms, using different keywords,
            or checking that relevant documents have been ingested into the knowledge base.
          </p>
        </div>
      ) : (
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
                {truncated && <p className="text-[10px] text-gray-500 mt-0.5">{truncated}</p>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
