'use client';

import { useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Lane =
  | 'semantic'
  | 'metadata'
  | 'metadata-broad'
  | 'path'
  | 'checklist'
  | 'manual-fetch'
  | 'far-fetch'
  | string;

export interface SourceRow {
  title?: string;
  s3_key?: string;
  summary?: string;
  document_type?: string;
  confidence_score?: number;
  lane?: Lane;
  score?: number | null;
  score_pct?: number;
  rationale?: string;
  read?: boolean;
  content?: string;
}

// ---------------------------------------------------------------------------
// Lane meta — color-coded chips so users read score in context
// (semantic 0.7 ≠ path 0.7).
// ---------------------------------------------------------------------------

const LANE_META: Record<string, { label: string; icon: string; classes: string }> = {
  semantic:         { label: 'Semantic',  icon: '🧠', classes: 'bg-purple-50 text-purple-700 border-purple-200' },
  metadata:         { label: 'Metadata',  icon: '📁', classes: 'bg-blue-50 text-blue-700 border-blue-200' },
  'metadata-broad': { label: 'Broadened', icon: '🔎', classes: 'bg-slate-50 text-slate-600 border-slate-200' },
  path:             { label: 'Path',      icon: '🗺️', classes: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
  checklist:        { label: 'Checklist', icon: '📋', classes: 'bg-teal-50 text-teal-700 border-teal-200' },
  'manual-fetch':   { label: 'Direct',    icon: '📥', classes: 'bg-amber-50 text-amber-700 border-amber-200' },
  'far-fetch':      { label: 'FAR',       icon: '📜', classes: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
};

export function laneMeta(lane?: string) {
  if (!lane) return LANE_META.metadata;
  return (
    LANE_META[lane] ?? {
      label: lane,
      icon: '•',
      classes: 'bg-gray-50 text-gray-700 border-gray-200',
    }
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function pctOf(row: SourceRow): number {
  if (typeof row.score_pct === 'number') return Math.max(0, Math.min(100, row.score_pct));
  if (typeof row.score === 'number') return Math.round(row.score * 100);
  if (typeof row.confidence_score === 'number') return Math.round(row.confidence_score * 100);
  return 0;
}

// Sort: read rows first, then by score desc.
export function sortSources(rows: SourceRow[]): SourceRow[] {
  return [...rows].sort((a, b) => {
    if (a.read !== b.read) return a.read ? -1 : 1;
    return pctOf(b) - pctOf(a);
  });
}

// ---------------------------------------------------------------------------
// Lane breakdown strip
// ---------------------------------------------------------------------------

export function LaneBreakdownStrip({
  breakdown,
  className,
}: {
  breakdown: Record<string, number> | undefined;
  className?: string;
}) {
  if (!breakdown || Object.keys(breakdown).length === 0) return null;
  return (
    <div
      className={
        className ??
        'px-3 py-1.5 border-b border-gray-100 flex items-center gap-3 text-[10px] text-gray-500 flex-wrap'
      }
    >
      <span className="font-bold uppercase tracking-wider text-gray-400">Lanes</span>
      {Object.entries(breakdown).map(([lane, count]) => {
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
  );
}

// ---------------------------------------------------------------------------
// Score bar
// ---------------------------------------------------------------------------

export function ScoreBar({ pct: value }: { pct: number }) {
  // Color ramps by relevance band — cosmetic, lane chip carries the meaning.
  const barClass =
    value >= 70
      ? 'bg-emerald-500'
      : value >= 40
        ? 'bg-blue-500'
        : value >= 15
          ? 'bg-amber-400'
          : 'bg-gray-300';
  return (
    <div className="flex items-center gap-1 shrink-0" title={`${value}% match`}>
      <div className="w-12 h-1.5 bg-gray-100 rounded overflow-hidden">
        <div className={`h-full ${barClass}`} style={{ width: `${Math.max(2, value)}%` }} />
      </div>
      <span className="text-[10px] font-mono tabular-nums text-gray-500 w-7 text-right">
        {value}%
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Single row
// ---------------------------------------------------------------------------

export function SourceRowView({ row }: { row: SourceRow }) {
  const meta = laneMeta(row.lane);
  const sourceKey = row.s3_key ?? '';
  const display = row.title || sourceKey || '(untitled)';
  const score = pctOf(row);
  const isRead = !!row.read;
  const tooltip = row.s3_key
    ? `${row.s3_key}${row.rationale ? `\n\n${row.rationale}` : ''}`
    : row.rationale || '';

  return (
    <div className={`flex items-start gap-2 py-1 ${isRead ? '' : 'opacity-70'}`} title={tooltip}>
      {/* Read indicator — solid colored circle (emoji renders unreliably in
          headless Chromium). Filled emerald when read; outlined slate when
          surfaced-only. */}
      <span
        className={`shrink-0 mt-1 inline-flex items-center justify-center w-4 h-4 rounded-full border text-[9px] font-bold leading-none ${
          isRead
            ? 'bg-emerald-500 border-emerald-600 text-white'
            : 'bg-white border-gray-300 text-gray-300'
        }`}
        aria-label={isRead ? 'read' : 'surfaced only'}
        title={isRead ? 'Read by agent' : 'Surfaced but not read'}
      >
        {isRead ? '✓' : ''}
      </span>

      {/* Title + s3_key */}
      <div className="flex-1 min-w-0">
        <div
          className={`text-xs truncate ${isRead ? 'text-gray-900 font-medium' : 'text-gray-500'}`}
        >
          {display}
        </div>
        {sourceKey && (
          <div className="font-mono text-[10px] text-gray-400 break-all">{sourceKey}</div>
        )}
      </div>

      {/* Lane chip */}
      <span
        className={`text-[9px] font-medium px-1.5 py-0.5 rounded border shrink-0 inline-flex items-center gap-1 mt-0.5 ${meta.classes}`}
      >
        <span>{meta.icon}</span>
        <span>{meta.label}</span>
      </span>

      {/* Score bar */}
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

// ---------------------------------------------------------------------------
// Read-state legend (re-used in headers)
// ---------------------------------------------------------------------------

export function ReadStateLegend() {
  return (
    <div className="text-[9px] text-gray-400 inline-flex items-center gap-2">
      <span className="inline-flex items-center gap-1">
        <span className="w-3 h-3 rounded-full bg-emerald-500 border border-emerald-600 inline-flex items-center justify-center text-white text-[8px] font-bold leading-none">
          ✓
        </span>
        read
      </span>
      <span className="text-gray-300">·</span>
      <span className="inline-flex items-center gap-1">
        <span className="w-3 h-3 rounded-full bg-white border border-gray-300 inline-block" />
        surfaced only
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sources table — full breakdown with collapse/expand
// ---------------------------------------------------------------------------

const READ_VISIBLE_LIMIT = 8;

export function SourcesTable({
  sources,
  visibleLimit = READ_VISIBLE_LIMIT,
}: {
  sources: SourceRow[];
  visibleLimit?: number;
}) {
  const [showMore, setShowMore] = useState(false);
  if (sources.length === 0) return null;
  const sorted = sortSources(sources);
  const visible = showMore ? sorted : sorted.slice(0, visibleLimit);
  const hiddenCount = Math.max(0, sorted.length - visibleLimit);

  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="text-[9px] font-bold uppercase text-gray-400 tracking-wider">
          Sources ({sorted.length})
        </div>
        <ReadStateLegend />
      </div>
      <div className="space-y-1">
        {visible.map((row, idx) => (
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
  );
}
