'use client';

import { useState, useMemo, useRef, useCallback } from 'react';
import type { MatrixState } from './matrix-types';
import {
  METHODS,
  TYPES,
  getCellData,
  cellColor,
  fmtDollar,
  sliderToDollar,
  dollarToSlider,
} from './matrix-data';

interface GridMatrixTabProps {
  state: MatrixState;
  onSelectCell: (methodId: string, typeId: string) => void;
}

interface PopoverData {
  methodId: string;
  typeId: string;
  x: number;
  y: number;
}

export default function GridMatrixTab({ state, onSelectCell }: GridMatrixTabProps) {
  const [gridDollar, setGridDollar] = useState(state.dollarValue);
  const [gridFlags, setGridFlags] = useState({
    isIT: state.isIT,
    isSB: state.isSB,
    isRD: state.isRD,
    isServices: state.isServices,
  });
  const [popover, setPopover] = useState<PopoverData | null>(null);
  const popoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const gridState: MatrixState = useMemo(
    () => ({
      method: state.method,
      type: state.type,
      dollarValue: gridDollar,
      isIT: gridFlags.isIT,
      isSB: gridFlags.isSB,
      isRD: gridFlags.isRD,
      isHS: false,
      isServices: gridFlags.isServices,
    }),
    [state.method, state.type, gridDollar, gridFlags],
  );

  // Pre-compute all cells
  const cells = useMemo(() => {
    const result: Record<string, ReturnType<typeof getCellData>> = {};
    for (const m of METHODS) {
      for (const t of TYPES) {
        result[`${m.id}:${t.id}`] = getCellData(m.id, t.id, gridState);
      }
    }
    return result;
  }, [gridState]);

  // Grid summary
  const summary = useMemo(() => {
    let validCount = 0,
      invalidCount = 0;
    let simplest: { method: string; type: string; docs: number; time: string } | null = null;
    let heaviest: { method: string; type: string; docs: number; time: string } | null = null;
    for (const m of METHODS) {
      for (const t of TYPES) {
        const data = cells[`${m.id}:${t.id}`];
        if (data.invalid) {
          invalidCount++;
          continue;
        }
        validCount++;
        if (!simplest || (data.reqDocs ?? 99) < simplest.docs)
          simplest = {
            method: m.label,
            type: t.label,
            docs: data.reqDocs!,
            time: `${data.timeMin}-${data.timeMax}wk`,
          };
        if (!heaviest || (data.reqDocs ?? 0) > heaviest.docs)
          heaviest = {
            method: m.label,
            type: t.label,
            docs: data.reqDocs!,
            time: `${data.timeMin}-${data.timeMax}wk`,
          };
      }
    }
    return { validCount, invalidCount, simplest, heaviest };
  }, [cells]);

  const toggleGridFlag = useCallback((key: 'isIT' | 'isSB' | 'isRD' | 'isServices') => {
    setGridFlags((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const handleCellEnter = useCallback((e: React.MouseEvent, methodId: string, typeId: string) => {
    if (popoverTimeout.current) clearTimeout(popoverTimeout.current);
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopover({ methodId, typeId, x: rect.right + 8, y: rect.top });
  }, []);

  const handleCellLeave = useCallback(() => {
    popoverTimeout.current = setTimeout(() => setPopover(null), 200);
  }, []);

  const typeShortLabel: Record<string, string> = {
    ffp: 'FFP',
    'fp-epa': 'FP-EPA',
    fpi: 'FPI',
    cpff: 'CPFF',
    cpif: 'CPIF',
    cpaf: 'CPAF',
    tm: 'T&M',
    lh: 'LH',
  };

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-6 px-5 py-3 border-b border-gray-100 bg-gray-50/50 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Dollar Value
          </span>
          <span className="text-sm font-bold font-mono text-amber-600">
            {fmtDollar(gridDollar)}
          </span>
          <input
            type="range"
            min="0"
            max="22"
            step="0.01"
            value={dollarToSlider(gridDollar)}
            onChange={(e) => setGridDollar(sliderToDollar(parseFloat(e.target.value)))}
            className="w-48 h-1.5 rounded-full appearance-none cursor-pointer"
            style={{ background: 'linear-gradient(to right, #22c55e, #eab308, #f97316, #ef4444)' }}
          />
        </div>
        <div className="flex items-center gap-3">
          {[
            { key: 'isIT' as const, label: 'IT' },
            { key: 'isSB' as const, label: 'Small Biz' },
            { key: 'isRD' as const, label: 'R&D' },
            { key: 'isServices' as const, label: 'Services' },
          ].map((f) => (
            <button
              key={f.key}
              onClick={() => toggleGridFlag(f.key)}
              className={`flex items-center gap-1.5 text-[11px] ${
                gridFlags[f.key] ? 'text-blue-600' : 'text-gray-400'
              }`}
            >
              <div
                className={`w-6 h-3.5 rounded-full relative transition-colors ${
                  gridFlags[f.key] ? 'bg-blue-500' : 'bg-gray-300'
                }`}
              >
                <div
                  className={`absolute top-[1px] w-3 h-3 bg-white rounded-full transition-all shadow-sm ${
                    gridFlags[f.key] ? 'left-[11px]' : 'left-[1px]'
                  }`}
                />
              </div>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto p-4">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 bg-white z-10 text-left px-3 py-2 text-[10px] font-bold text-gray-400 uppercase w-44">
                Method \ Type
              </th>
              {TYPES.map((t) => (
                <th key={t.id} className="px-2 py-2 text-center">
                  <div className="text-[11px] font-bold text-gray-700">{typeShortLabel[t.id]}</div>
                  <div className="text-[9px] text-gray-400">
                    {t.category === 'fp'
                      ? 'Fixed-Price'
                      : t.category === 'cr'
                        ? 'Cost-Reimb'
                        : 'Level-of-Effort'}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {METHODS.map((m) => (
              <tr key={m.id}>
                <th className="sticky left-0 bg-white z-10 text-left px-3 py-2">
                  <div className="text-xs font-semibold text-gray-800 uppercase">{m.label}</div>
                  <div className="text-[9px] text-gray-400">FAR {m.far}</div>
                </th>
                {TYPES.map((t) => {
                  const data = cells[`${m.id}:${t.id}`];
                  if (data.invalid) {
                    return (
                      <td key={t.id} className="px-1 py-1">
                        <div className="h-20 rounded-md bg-gray-50 border border-gray-100 flex items-center justify-center text-gray-300 text-[10px] opacity-40">
                          N/A
                        </div>
                      </td>
                    );
                  }
                  const clr = cellColor(data.reqDocs!);
                  return (
                    <td key={t.id} className="px-1 py-1">
                      <div
                        className="h-20 rounded-md border cursor-pointer transition-transform hover:scale-105 flex flex-col items-center justify-center gap-0.5 relative"
                        style={{ background: clr.bg, borderColor: clr.border }}
                        onMouseEnter={(e) => handleCellEnter(e, m.id, t.id)}
                        onMouseLeave={handleCellLeave}
                        onClick={() => onSelectCell(m.id, t.id)}
                      >
                        <div className="text-xl font-bold" style={{ color: clr.text }}>
                          {data.reqDocs}
                        </div>
                        <div className="text-[9px] font-medium" style={{ color: clr.text }}>
                          DOCS
                        </div>
                        {/* Risk bar */}
                        <div className="w-10/12 h-1 rounded-full overflow-hidden flex mt-0.5">
                          <div
                            className="bg-green-500 h-full"
                            style={{ width: `${100 - (data.riskPct ?? 50)}%` }}
                          />
                          <div
                            className="bg-red-400 h-full"
                            style={{ width: `${data.riskPct ?? 50}%` }}
                          />
                        </div>
                        {/* Badges */}
                        <div className="flex gap-0.5 mt-0.5">
                          {(data.errors ?? 0) > 0 && (
                            <span className="text-[7px] px-1 rounded bg-red-200 text-red-700 font-bold">
                              ERR
                            </span>
                          )}
                          {data.hasJA && (
                            <span className="text-[7px] px-1 rounded bg-amber-200 text-amber-700 font-bold">
                              J&A
                            </span>
                          )}
                          {data.hasDF && (
                            <span className="text-[7px] px-1 rounded bg-orange-200 text-orange-700 font-bold">
                              D&F
                            </span>
                          )}
                          {(data.warnings ?? 0) > 0 && !(data.errors ?? 0) && (
                            <span className="text-[7px] px-1 rounded bg-amber-100 text-amber-600 font-bold">
                              !
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 px-5 py-2 border-t border-gray-100 bg-gray-50/50 text-[10px] text-gray-500 flex-shrink-0">
        <LegendItem
          color="rgba(34,197,94,0.12)"
          border="rgba(34,197,94,0.3)"
          label="1-3 docs (simple)"
        />
        <LegendItem
          color="rgba(234,179,8,0.12)"
          border="rgba(234,179,8,0.3)"
          label="4-6 docs (moderate)"
        />
        <LegendItem
          color="rgba(249,115,22,0.12)"
          border="rgba(249,115,22,0.3)"
          label="7-9 docs (complex)"
        />
        <LegendItem
          color="rgba(239,68,68,0.12)"
          border="rgba(239,68,68,0.3)"
          label="10+ docs (heavy)"
        />
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-gray-50 border border-gray-200 opacity-40" /> N/A
        </div>
        <div className="ml-auto text-gray-400">Click any cell for full detail</div>
      </div>

      {/* Summary bar */}
      <div className="px-5 py-2 border-t border-gray-100 text-[11px] font-mono text-gray-500 flex-shrink-0">
        Contract Requirements Matrix at {fmtDollar(gridDollar)}. {summary.validCount} valid,{' '}
        {summary.invalidCount} prohibited.
        {summary.simplest && (
          <>
            {' '}
            Simplest: {summary.simplest.method} + {summary.simplest.type} ({summary.simplest.docs}{' '}
            docs, {summary.simplest.time}).
          </>
        )}
        {summary.heaviest && (
          <>
            {' '}
            Most complex: {summary.heaviest.method} + {summary.heaviest.type} (
            {summary.heaviest.docs} docs, {summary.heaviest.time}).
          </>
        )}
      </div>

      {/* Popover */}
      {popover && <CellPopover popover={popover} cells={cells} onSelectCell={onSelectCell} />}
    </div>
  );
}

function LegendItem({ color, border, label }: { color: string; border: string; label: string }) {
  return (
    <div className="flex items-center gap-1">
      <div
        className="w-3 h-3 rounded"
        style={{ background: color, border: `1px solid ${border}` }}
      />
      {label}
    </div>
  );
}

function CellPopover({
  popover,
  cells,
  onSelectCell,
}: {
  popover: PopoverData;
  cells: Record<string, ReturnType<typeof getCellData>>;
  onSelectCell: (m: string, t: string) => void;
}) {
  const data = cells[`${popover.methodId}:${popover.typeId}`];
  if (!data || data.invalid) return null;

  const mObj = METHODS.find((x) => x.id === popover.methodId)!;
  const tObj = TYPES.find((x) => x.id === popover.typeId)!;

  // Clamp position
  let left = popover.x;
  let top = popover.y;
  if (left + 320 > window.innerWidth) left = popover.x - 340;
  if (top + 400 > window.innerHeight) top = window.innerHeight - 410;
  if (top < 8) top = 8;

  return (
    <div
      className="fixed z-[60] w-[300px] bg-white border border-gray-200 rounded-lg shadow-xl p-4 space-y-3 animate-in fade-in duration-100"
      style={{ left, top }}
    >
      <div className="font-semibold text-sm text-gray-900">
        {mObj.label} + {tObj.label}
      </div>
      <div className="text-[11px] text-gray-400">
        Risk: Gov {100 - (data.riskPct ?? 50)}% / Con {data.riskPct ?? 50}% &mdash; {data.timeMin}
        \u2013{data.timeMax} wk
      </div>

      {data.docs && (
        <div>
          <div className="text-[10px] font-bold uppercase text-gray-400 mb-1">
            Required Documents
          </div>
          {data.docs
            .filter((d) => d.required)
            .map((d, i) => (
              <div key={i} className="flex items-center gap-1.5 text-[11px]">
                <div className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
                {d.name}
              </div>
            ))}
        </div>
      )}

      {data.allWarnings && data.allWarnings.length > 0 && (
        <div>
          <div className="text-[10px] font-bold uppercase text-amber-500 mb-1">Warnings</div>
          {data.allWarnings.map((w, i) => (
            <div key={i} className="text-[10px] text-amber-700">
              {w}
            </div>
          ))}
        </div>
      )}

      <button
        onClick={() => onSelectCell(popover.methodId, popover.typeId)}
        className="w-full text-center text-[11px] font-medium text-blue-600 bg-blue-50 rounded py-1.5 hover:bg-blue-100 transition-colors"
      >
        Open in Detail Explorer
      </button>
    </div>
  );
}
