'use client';

import { useRef } from 'react';
import type { MatrixState, Requirements } from './matrix-types';
import {
  METHODS,
  TYPES,
  THRESHOLDS,
  APPROVAL_CHAINS,
  isTypeDisabled,
  apApproval,
  jaApproval,
  fmtDollar,
  dollarToSlider,
  sliderToDollar,
  getActiveApprovalIndex,
} from './matrix-data';

interface DetailExplorerTabProps {
  state: MatrixState;
  requirements: Requirements;
  onSetMethod: (id: string) => void;
  onSetType: (id: string) => void;
  onSetDollarValue: (v: number) => void;
  onToggleFlag: (key: 'isIT' | 'isSB' | 'isRD' | 'isHS' | 'isServices') => void;
  onApplyPreset: (name: string) => void;
}

export default function DetailExplorerTab({
  state,
  requirements: r,
  onSetMethod,
  onSetType,
  onSetDollarValue,
  onToggleFlag,
  onApplyPreset,
}: DetailExplorerTabProps) {
  const dollarInputRef = useRef<HTMLInputElement>(null);

  const mObj = METHODS.find((x) => x.id === state.method)!;
  const tObj = TYPES.find((x) => x.id === state.type)!;
  const v = state.dollarValue;

  function handleDollarInput(raw: string) {
    const num = parseInt(raw.replace(/[^0-9]/g, ''), 10) || 0;
    onSetDollarValue(num);
  }

  function handleSliderInput(val: string) {
    onSetDollarValue(sliderToDollar(parseFloat(val)));
  }

  const presets = [
    { id: 'micro', label: 'Micro-Purchase' },
    { id: 'simple-product', label: 'Simple Product <SAT' },
    { id: 'it-services', label: 'IT Services IDIQ' },
    { id: 'rd-contract', label: 'R&D Cost-Plus' },
    { id: 'large-sole', label: 'Large Sole Source' },
  ];

  const flags: { key: 'isIT' | 'isSB' | 'isRD' | 'isHS' | 'isServices'; label: string }[] = [
    { key: 'isIT', label: 'IT Requirement' },
    { key: 'isSB', label: 'Small Business Awardee' },
    { key: 'isRD', label: 'R&D Effort' },
    { key: 'isHS', label: 'Human Subjects' },
    { key: 'isServices', label: 'Services (not products)' },
  ];

  return (
    <div className="flex h-full">
      {/* ── Left Sidebar ── */}
      <div className="w-[340px] min-w-[340px] border-r border-gray-200 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {/* Presets */}
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Presets
          </label>
          <div className="flex flex-wrap gap-1 mt-1">
            {presets.map((p) => (
              <button
                key={p.id}
                onClick={() => onApplyPreset(p.id)}
                className="text-[10px] px-2.5 py-1 rounded border border-gray-200 bg-white text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* Acquisition Method */}
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Acquisition Method{' '}
            <span className="font-normal normal-case tracking-normal text-blue-500">
              HOW you buy
            </span>
          </label>
          <div className="flex flex-col gap-1 mt-1">
            {METHODS.map((m) => (
              <button
                key={m.id}
                onClick={() => onSetMethod(m.id)}
                className={`flex items-center gap-2.5 px-2.5 py-2 rounded-md border text-left transition-all ${
                  state.method === m.id
                    ? 'border-blue-500 bg-blue-50'
                    : 'border-gray-200 bg-white hover:border-blue-300'
                }`}
              >
                <div
                  className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${
                    state.method === m.id ? 'border-blue-500' : 'border-gray-300'
                  } relative`}
                >
                  {state.method === m.id && (
                    <div className="absolute inset-[2px] bg-blue-500 rounded-full" />
                  )}
                </div>
                <div>
                  <div className="text-xs font-medium text-gray-800">{m.label}</div>
                  <div className="text-[10px] text-gray-400">{m.sub}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Contract Type */}
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Contract Type{' '}
            <span className="font-normal normal-case tracking-normal text-blue-500">
              HOW you pay
            </span>
          </label>
          <div className="flex flex-col gap-1 mt-1">
            {TYPES.map((t) => {
              const disabled = isTypeDisabled(state.method, t.id);
              return (
                <button
                  key={t.id}
                  onClick={() => !disabled && onSetType(t.id)}
                  className={`flex items-center gap-2.5 px-2.5 py-2 rounded-md border text-left transition-all ${
                    disabled
                      ? 'opacity-35 cursor-not-allowed border-gray-200 bg-white'
                      : state.type === t.id
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 bg-white hover:border-blue-300'
                  }`}
                  disabled={disabled}
                >
                  <div
                    className={`w-3 h-3 rounded-full border-2 flex-shrink-0 ${
                      state.type === t.id ? 'border-blue-500' : 'border-gray-300'
                    } relative`}
                  >
                    {state.type === t.id && (
                      <div className="absolute inset-[2px] bg-blue-500 rounded-full" />
                    )}
                  </div>
                  <div className="text-xs font-medium text-gray-800">{t.label}</div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Dollar Value */}
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Estimated Dollar Value
          </label>
          <div className="mt-1 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-amber-600">$</span>
              <input
                ref={dollarInputRef}
                type="text"
                value={v.toLocaleString()}
                onChange={(e) => handleDollarInput(e.target.value)}
                className="flex-1 px-3 py-2 border border-gray-200 rounded-md text-base font-mono font-semibold text-gray-800 focus:outline-none focus:border-blue-500"
              />
            </div>
            <input
              type="range"
              min="0"
              max="22"
              step="0.01"
              value={dollarToSlider(v)}
              onChange={(e) => handleSliderInput(e.target.value)}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
              style={{
                background: 'linear-gradient(to right, #22c55e, #eab308, #f97316, #ef4444)',
              }}
            />
            <div className="flex flex-wrap gap-1">
              {THRESHOLDS.map((t) => (
                <button
                  key={t.value}
                  onClick={() => onSetDollarValue(t.value)}
                  className={`text-[9px] px-1.5 py-0.5 rounded border transition-all ${
                    v >= t.value
                      ? 'bg-blue-50 border-blue-400 text-blue-600 font-semibold'
                      : 'border-gray-200 bg-white text-gray-400 hover:border-blue-300'
                  }`}
                >
                  {t.short}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Flags */}
        <div>
          <label className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Additional Factors
          </label>
          <div className="mt-1 space-y-1">
            {flags.map((f) => (
              <div key={f.key} className="flex items-center justify-between py-1.5">
                <span className="text-xs text-gray-700">{f.label}</span>
                <button
                  onClick={() => onToggleFlag(f.key)}
                  className={`w-9 h-5 rounded-full relative transition-colors ${
                    state[f.key] ? 'bg-blue-500' : 'bg-gray-300'
                  }`}
                >
                  <div
                    className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all shadow-sm ${
                      state[f.key] ? 'left-[18px]' : 'left-0.5'
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Right Preview Panel ── */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {/* Summary Banner */}
        <div className="grid grid-cols-3 gap-3 p-4 rounded-lg bg-gradient-to-r from-blue-50 to-white border border-blue-200">
          <div className="text-center">
            <div className="text-lg font-bold font-mono text-amber-600">{fmtDollar(v)}</div>
            <div className="text-[10px] text-gray-400">Estimated Value</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-bold text-gray-800">{mObj.label}</div>
            <div className="text-[10px] text-gray-400">FAR {mObj.far}</div>
          </div>
          <div className="text-center">
            <div className="text-sm font-bold text-gray-800">{tObj.label.split('(')[0].trim()}</div>
            <div className="text-[10px] text-gray-400">
              {r.isCR ? 'Cost-Reimbursement' : r.isLOE ? 'Level-of-Effort' : 'Fixed-Price'}
            </div>
          </div>
        </div>

        {/* Errors */}
        {r.errors.map((e, i) => (
          <div
            key={i}
            className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-xs text-red-800"
          >
            <span className="flex-shrink-0">&#x26D4;</span>
            <div>{e}</div>
          </div>
        ))}

        {/* Warnings */}
        {r.warnings.map((w, i) => (
          <div
            key={i}
            className="flex items-start gap-2 p-3 rounded-md bg-amber-50 border border-amber-200 text-xs text-amber-800"
          >
            <span className="flex-shrink-0">&#x26A0;</span>
            <div>{w}</div>
          </div>
        ))}

        {/* Risk + Timeline row */}
        <div className="grid grid-cols-2 gap-4">
          {/* Risk Allocation */}
          <Card title="Risk Allocation" icon="\u2696">
            <div className="space-y-2">
              <div className="flex justify-between text-[10px] text-gray-500">
                <span>Government Risk</span>
                <span>Contractor Risk</span>
              </div>
              <div className="flex h-5 rounded-full overflow-hidden text-[10px] font-semibold">
                <div
                  className="bg-blue-500 text-white flex items-center justify-center"
                  style={{ width: `${100 - r.riskPct}%` }}
                >
                  {100 - r.riskPct}%
                </div>
                <div
                  className="bg-orange-400 text-white flex items-center justify-center"
                  style={{ width: `${r.riskPct}%` }}
                >
                  {r.riskPct}%
                </div>
              </div>
              {r.feeCaps.length > 0 && (
                <>
                  <div className="text-[10px] font-semibold text-gray-400 uppercase mt-2">
                    Fee Caps
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {r.feeCaps.map((f, i) => (
                      <span
                        key={i}
                        className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-600"
                      >
                        {f}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          </Card>

          {/* Timeline & Approvals */}
          <Card title="Timeline & Approvals" icon="\u23F1">
            <div className="space-y-3">
              <div className="h-5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full flex items-center justify-center text-[10px] font-semibold text-white"
                  style={{
                    width: `${Math.min(100, (r.timeMax / 52) * 100)}%`,
                    background: `linear-gradient(90deg, #22c55e, ${r.timeMax > 20 ? '#ef4444' : r.timeMax > 10 ? '#f97316' : '#eab308'})`,
                  }}
                >
                  {r.timeMin}\u2013{r.timeMax} weeks
                </div>
              </div>
              <div>
                <div className="text-[10px] font-semibold text-gray-400 uppercase">AP Approval</div>
                <div className="text-xs text-gray-700">
                  {v > 350000 ? apApproval(v) : 'Not required below SAT'}
                </div>
              </div>
              <div>
                <div className="text-[10px] font-semibold text-gray-400 uppercase">
                  J&A Approval (if sole source)
                </div>
                <div className="text-xs text-gray-700">{jaApproval(v)}</div>
              </div>
            </div>
          </Card>
        </div>

        {/* Approval Authority Chain */}
        <Card title="Approval Authority Chain" icon="\uD83C\uDFDB">
          <div className="space-y-3">
            {(['ap', 'ja', 'as'] as const).map((chainKey) => {
              const chain = APPROVAL_CHAINS[chainKey];
              const activeIdx = getActiveApprovalIndex(chain, v);
              const labels: Record<string, string> = {
                ap: 'Acquisition Plan',
                ja: 'J&A (Sole Source)',
                as: 'Acquisition Strategy',
              };
              return (
                <div key={chainKey}>
                  <div className="text-[10px] font-semibold text-gray-400 uppercase mb-1">
                    {labels[chainKey]}
                  </div>
                  <div className="flex items-center gap-1 flex-wrap">
                    {chain.map((node, i) => (
                      <span key={i} className="flex items-center gap-1">
                        <span
                          className={`text-[10px] px-2 py-1 rounded ${
                            i === activeIdx
                              ? 'bg-blue-500 text-white font-semibold'
                              : i < activeIdx
                                ? 'bg-blue-100 text-blue-600'
                                : 'bg-gray-100 text-gray-400'
                          }`}
                        >
                          {node.label}
                        </span>
                        {i < chain.length - 1 && <span className="text-gray-300">\u2192</span>}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Required Documents */}
        <Card
          title={`Required Documents (${r.docs.filter((d) => d.required).length} of ${r.docs.length})`}
          icon="\uD83D\uDCCB"
        >
          <ul className="space-y-1.5">
            {r.docs.map((d, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className={`flex-shrink-0 w-5 h-5 rounded flex items-center justify-center text-xs ${
                    d.required ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
                  }`}
                >
                  {d.required ? '\u2713' : '\u2014'}
                </span>
                <div>
                  <div className="text-xs font-medium text-gray-800">{d.name}</div>
                  <div className="text-[10px] text-gray-400">{d.note}</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        {/* Dollar Thresholds */}
        <Card title="Dollar Thresholds" icon="\uD83D\uDCCA">
          <div className="flex flex-wrap gap-1.5">
            {THRESHOLDS.map((t) => (
              <span
                key={t.value}
                className={`text-[10px] px-2 py-1 rounded border ${
                  v >= t.value
                    ? 'bg-green-50 border-green-300 text-green-700'
                    : 'bg-gray-50 border-gray-200 text-gray-400'
                }`}
              >
                {v >= t.value ? '\u2713' : '\u2717'} {t.label}
              </span>
            ))}
          </div>
        </Card>

        {/* Competition + Compliance row */}
        <div className="grid grid-cols-2 gap-4">
          <Card title="Competition Requirements" icon="\uD83C\uDFAF">
            <p className="text-xs leading-relaxed text-gray-700">{r.competition}</p>
          </Card>

          <Card title="Compliance Clauses" icon="\u2611">
            <div className="space-y-1.5">
              {r.compliance.map((c, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div
                    className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${
                      c.status === 'req'
                        ? 'bg-green-500'
                        : c.status === 'cond'
                          ? 'bg-amber-500'
                          : 'bg-gray-300'
                    }`}
                  />
                  <div>
                    <div className="text-xs text-gray-800">{c.name}</div>
                    <div className="text-[10px] text-gray-400">{c.note}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* PMR Checklist */}
        <Card title="Applicable PMR Checklist" icon="\uD83D\uDCD6">
          <p className="text-sm font-medium text-blue-600">{r.pmr}</p>
        </Card>
      </div>
    </div>
  );
}

// ── Reusable Card ──

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-100 flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-gray-500">
        <span className="text-sm">{icon}</span>
        {title}
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}
