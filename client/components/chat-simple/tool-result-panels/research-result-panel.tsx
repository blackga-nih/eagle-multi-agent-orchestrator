'use client';

import { useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Lane = 'semantic' | 'metadata' | 'metadata-broad' | 'path' | 'checklist' | string;

interface SourceRow {
  title?: string;
  s3_key?: string;
  summary?: string;
  document_type?: string;
  confidence_score?: number;
  // Per-lane attribution + score (added 2026-04-28; older packets omit these)
  lane?: Lane;
  score?: number;       // 0.0–1.0, lane-specific scale
  score_pct?: number;   // pre-computed percentage 0–100
  rationale?: string;   // optional one-liner
  read?: boolean;       // true = fetched and read; false = surfaced only
  // Fetched-doc-only
  content?: string;
}

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
  // Full packet
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

// Lane chip — color-coded so users read score in context (semantic 0.7 ≠ path 0.7).
const LANE_META: Record<string, { label: string; icon: string; classes: string }> = {
  semantic:         { label: 'Semantic',  icon: '🧠', classes: 'bg-purple-50 text-purple-700 border-purple-200' },
  metadata:         { label: 'Metadata',  icon: '📁', classes: 'bg-blue-50 text-blue-700 border-blue-200' },
  'metadata-broad': { label: 'Broadened', icon: '🔎', classes: 'bg-slate-50 text-slate-600 border-slate-200' },
  path:             { label: 'Path',      icon: '🗺️', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  checklist:        { label: 'Checklist', icon: '📋', classes: 'bg-teal-50 text-teal-700 border-teal-200' },
};

function laneMeta(lane?: string) {
  if (!lane) return LANE_META.metadata;
  return LANE_META[lane] ?? { label: lane, icon: '•', classes: 'bg-gray-50 text-gray-700 border-gray-200' };
}

function pct(row: SourceRow): number {
  if (typeof row.score_pct === 'number') return Math.max(0, Math.min(100, row.score_pct));
  if (typeof row.score === 'number') return Math.round(row.score * 100);
  // Backward-compat: if no per-query score, fall back to static metadata
  if (typeof row.confidence_score === 'number') return Math.round(row.confidence_score * 100);
  return 0;
}

// Combine fetched (read=true) + kb_results (read=false), sort: read first then score desc.
function buildSourceList(data: ResearchData): SourceRow[] {
  const fetched = (data.fetched_documents ?? []).map((d) => ({ ...d, read: d.read ?? true }));
  const surfaced = (data.kb_results ?? []).map((d) => ({ ...d, read: d.read ?? false }));
  const combined = [...fetched, ...surfaced];
  combined.sort((a, b) => {
    if (a.read !== b.read) return a.read ? -1 : 1;
    return pct(b) - pct(a);
  });
  return combined;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const READ_VISIBLE_LIMIT = 8;

export default function ResearchResultPanel({ text }: { text: string }) {
  const [showMore, setShowMore] = useState(false);

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
  const fetchedCount = data.fetched_count ?? data.fetched_documents?.length ?? sources.filter((s) => s.read).length;
  const kbCount = data.kb_results_count ?? data.kb_results?.length ?? sources.filter((s) => !s.read).length;
  const checklists = data.checklists_loaded ?? (data.checklists ? Object.keys(data.checklists) : []);
  const method = data.detected_method ?? '';
  const hasMatrix = data.compliance_matrix_included ?? !!data.compliance_matrix;
  const laneBreakdown = data._meta?.lane_breakdown;

  // Split for collapsed/expanded view
  const visibleSources = showMore ? sources : sources.slice(0, READ_VISIBLE_LIMIT);
  const hiddenCount = Math.max(0, sources.length - READ_VISIBLE_LIMIT);

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
      {laneBreakdown && Object.keys(laneBreakdown).length > 0 && (
        <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-3 text-[10px] text-gray-500">
          <span className="font-bold uppercase tracking-wider text-gray-400">Lanes</span>
          {Object.entries(laneBreakdown).map(([lane, count]) => {
            const meta = laneMeta(lane);
            return (
              <span key={lane} className="inline-flex items-center gap-1">
                <span>{meta.icon}</span>
                <span className="font-medium text-gray-700">{count}</span>
                <span className="text-gray-400">{meta.label}</span>
              </span>
            );
          })}
        </div>
      )}

      {/* Sources table */}
      {sources.length > 0 && (
        <div className="px-3 py-2 border-b border-gray-100">
          <div className="flex items-center justify-between mb-1.5">
            <div className="text-[9px] font-bold uppercase text-gray-400 tracking-wider">
              Sources ({sources.length})
            </div>
            <div className="text-[9px] text-gray-400">
              ✅ read · ☐ surfaced only
            </div>
          </div>
          <div className="space-y-1">
            {visibleSources.map((row, idx) => (
              <SourceRowView key={`${row.s3_key ?? idx}-${idx}`} row={row} />
            ))}
          </div>
          {hiddenCount > 0 && (
            <button
              type="button"
              onClick={() => setShowMore((v) => !v)}
              className="mt-1.5 text-[10px] font-medium text-blue-600 hover:text-blue-700 hover:underline"
            >
              {showMore ? 'Show less' : `Show ${hiddenCount} more`}
            </button>
          )}
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
// Source row sub-component
// ---------------------------------------------------------------------------

function SourceRowView({ row }: { row: SourceRow }) {
  const meta = laneMeta(row.lane);
  const filename = row.s3_key?.split('/').pop() ?? '';
  const display = row.title || filename || row.s3_key || '(untitled)';
  const score = pct(row);
  const isRead = !!row.read;
  const tooltip = row.s3_key ? `${row.s3_key}${row.rationale ? `\n\n${row.rationale}` : ''}` : row.rationale || '';

  return (
    <div className="flex items-center gap-2 py-0.5" title={tooltip}>
      {/* Read indicator */}
      <span
        className={`text-[10px] shrink-0 ${isRead ? 'text-emerald-600' : 'text-gray-300'}`}
        aria-label={isRead ? 'read' : 'surfaced only'}
      >
        {isRead ? '✅' : '☐'}
      </span>

      {/* Title */}
      <span
        className={`text-xs truncate flex-1 min-w-0 ${isRead ? 'text-gray-900 font-medium' : 'text-gray-600'}`}
      >
        {display}
      </span>

      {/* Lane chip */}
      <span
        className={`text-[9px] font-medium px-1.5 py-0.5 rounded border shrink-0 inline-flex items-center gap-1 ${meta.classes}`}
      >
        <span>{meta.icon}</span>
        <span>{meta.label}</span>
      </span>

      {/* Score bar + numeric */}
      <ScoreBar pct={score} />

      {/* Rationale (truncated; full on hover via title attr) */}
      {row.rationale && (
        <span className="text-[10px] italic text-gray-500 truncate max-w-[180px] hidden md:inline">
          {row.rationale}
        </span>
      )}
    </div>
  );
}

function ScoreBar({ pct: value }: { pct: number }) {
  // Color ramps by relevance band — cosmetic, lane chip carries the meaning.
  const barClass =
    value >= 70 ? 'bg-emerald-500'
    : value >= 40 ? 'bg-blue-500'
    : value >= 15 ? 'bg-amber-400'
    : 'bg-gray-300';
  return (
    <div className="flex items-center gap-1 shrink-0" title={`${value}% match`}>
      <div className="w-12 h-1.5 bg-gray-100 rounded overflow-hidden">
        <div
          className={`h-full ${barClass}`}
          style={{ width: `${Math.max(2, value)}%` }}
        />
      </div>
      <span className="text-[10px] font-mono tabular-nums text-gray-500 w-7 text-right">
        {value}%
      </span>
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
