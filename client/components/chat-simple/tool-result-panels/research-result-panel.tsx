'use client';

import {
  LaneBreakdownStrip,
  SourceRow,
  SourcesTable,
  sortSources,
} from '../sources-breakdown';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ResearchMeta {
  lane_breakdown?: Record<string, number>;
  total_surfaced?: number;
  fetched_count?: number;
  kb_results_cap?: number;
}

interface ResearchData {
  kb_results_count?: number;
  fetched_count?: number;
  checklists_loaded?: string[];
  detected_method?: string;
  compliance_matrix_included?: boolean;
  // SSE-emit slim per-entry array — preferred source for the table.
  // Each entry already carries title, s3_key, lane, score, score_pct, rationale, read.
  sources?: SourceRow[];
  lane_breakdown?: Record<string, number>;
  total_surfaced?: number;
  // Full packet (LLM payload) — fallback shape, used when the panel is rendered
  // from a non-SSE source (e.g. a stored tool_result body).
  kb_results?: SourceRow[];
  fetched_documents?: SourceRow[];
  checklists?: Record<string, string>;
  compliance_matrix?: Record<string, unknown>;
  _meta?: ResearchMeta;
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

// Build the row list. Preferred source is `data.sources` (the SSE emit slim
// array). Fall back to combining fetched_documents + kb_results from the full
// packet shape so older messages and any non-SSE paths still render.
function buildSourceList(data: ResearchData): SourceRow[] {
  if (Array.isArray(data.sources) && data.sources.length > 0) {
    return sortSources(data.sources.map((d) => ({ ...d })));
  }
  const fetched = (data.fetched_documents ?? []).map((d) => ({ ...d, read: d.read ?? true }));
  const surfaced = (data.kb_results ?? []).map((d) => ({ ...d, read: d.read ?? false }));
  return sortSources([...fetched, ...surfaced]);
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

  // Derive counts — support both emit-summary and full-packet formats
  const sources = buildSourceList(data);
  const fetchedCount =
    data.fetched_count ?? data.fetched_documents?.length ?? sources.filter((s) => s.read).length;
  const kbCount =
    data.kb_results_count ?? data.kb_results?.length ?? sources.filter((s) => !s.read).length;
  const checklists = data.checklists_loaded ?? (data.checklists ? Object.keys(data.checklists) : []);
  const method = data.detected_method ?? '';
  const hasMatrix = data.compliance_matrix_included ?? !!data.compliance_matrix;
  // Lane breakdown — SSE emit puts it at top level; full-packet path nests it under _meta.
  const laneBreakdown = data.lane_breakdown ?? data._meta?.lane_breakdown;

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
        <StatCell value={kbCount + fetchedCount} label="Sources" icon="🔍" />
        <StatCell value={fetchedCount} label="Read" icon="📄" highlight={fetchedCount > 0} />
        <StatCell value={checklists.length} label="Checklists" icon="📋" />
        <StatCell
          value={hasMatrix ? 'Yes' : 'No'}
          label="Compliance Matrix"
          icon="✅"
          highlight={hasMatrix}
        />
      </div>

      {/* Lane breakdown strip */}
      <LaneBreakdownStrip breakdown={laneBreakdown} />

      {/* Sources table */}
      {sources.length > 0 && (
        <div className="px-3 py-2 border-b border-gray-100">
          <SourcesTable sources={sources} />
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
