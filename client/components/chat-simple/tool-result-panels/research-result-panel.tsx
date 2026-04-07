'use client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FetchedDoc {
  title?: string;
  s3_key?: string;
  content?: string;
}

interface ResearchData {
  kb_results_count?: number;
  fetched_count?: number;
  checklists_loaded?: string[];
  detected_method?: string;
  compliance_matrix_included?: boolean;
  // Full packet fields (if the raw tool result is shown instead of emit summary)
  kb_results?: Array<{ title?: string; s3_key?: string; summary?: string; document_type?: string; confidence_score?: number }>;
  fetched_documents?: FetchedDoc[];
  checklists?: Record<string, string>;
  compliance_matrix?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const METHOD_LABELS: Record<string, string> = {
  negotiated: 'Negotiated',
  sap: 'Simplified (SAP)',
  sole: 'Sole Source',
  fss: 'Federal Supply Schedule',
  bpa: 'Blanket Purchase Agreement',
  idiq: 'IDIQ',
  micro: 'Micro-Purchase',
};

function methodLabel(method: string): string {
  return METHOD_LABELS[method] || method.replace(/_/g, ' ');
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ResearchResultPanel({ text }: { text: string }) {
  let data: ResearchData = {};

  try {
    const parsed = JSON.parse(text);
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      data = parsed;
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

  // Derive counts — support both emit summary and full packet formats
  const kbCount = data.kb_results_count ?? data.kb_results?.length ?? 0;
  const fetchedCount = data.fetched_count ?? data.fetched_documents?.length ?? 0;
  const checklists = data.checklists_loaded ?? (data.checklists ? Object.keys(data.checklists) : []);
  const method = data.detected_method ?? '';
  const hasMatrix = data.compliance_matrix_included ?? !!data.compliance_matrix;

  // Fetched document titles (from full packet)
  const fetchedDocs = data.fetched_documents ?? [];

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      {/* Header */}
      <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-2">
        <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">
          Research Results
        </span>
        {method && (
          <span className="text-[9px] bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded-full font-medium">
            {methodLabel(method)}
          </span>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-4 gap-0 border-b border-gray-100">
        <StatCell value={kbCount} label="KB Results" icon="🔍" />
        <StatCell value={fetchedCount} label="Docs Fetched" icon="📄" />
        <StatCell value={checklists.length} label="Checklists" icon="📋" />
        <StatCell
          value={hasMatrix ? 'Yes' : 'No'}
          label="Compliance Matrix"
          icon="✅"
          highlight={hasMatrix}
        />
      </div>

      {/* Fetched documents */}
      {fetchedDocs.length > 0 && (
        <div className="px-3 py-2 border-b border-gray-100">
          <div className="text-[9px] font-bold uppercase text-gray-400 tracking-wider mb-1.5">
            Documents Fetched
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {fetchedDocs.map((doc, idx) => {
              const filename = doc.s3_key?.split('/').pop() ?? '';
              const charCount = doc.content?.length ?? 0;
              return (
                <div key={idx} className="flex items-center gap-2 py-0.5">
                  <span className="text-gray-300 text-[10px]">📄</span>
                  <span className="text-xs text-gray-800 truncate flex-1">
                    {doc.title || filename || `Document ${idx + 1}`}
                  </span>
                  {charCount > 0 && (
                    <span className="text-[9px] text-gray-400 shrink-0">
                      {charCount >= 1000 ? `${Math.round(charCount / 1000)}K` : charCount} chars
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Checklists */}
      {checklists.length > 0 && (
        <div className="px-3 py-2">
          <div className="text-[9px] font-bold uppercase text-gray-400 tracking-wider mb-1.5">
            Checklists Loaded
          </div>
          <div className="flex flex-wrap gap-1.5">
            {checklists.map((name, idx) => (
              <span
                key={idx}
                className="text-[10px] font-medium px-2 py-1 rounded border border-green-200 bg-green-50 text-green-800"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat cell sub-component
// ---------------------------------------------------------------------------

function StatCell({
  value,
  label,
  icon,
  highlight,
}: {
  value: number | string;
  label: string;
  icon: string;
  highlight?: boolean;
}) {
  return (
    <div className="text-center py-3 px-2 border-r border-gray-100 last:border-r-0">
      <div className="text-lg mb-0.5">{icon}</div>
      <div
        className={`text-sm font-bold ${
          highlight === false ? 'text-gray-400' : 'text-gray-900'
        }`}
      >
        {value}
      </div>
      <div className="text-[9px] text-gray-400 mt-0.5">{label}</div>
    </div>
  );
}
