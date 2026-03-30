'use client';

import { useState } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DocItem {
  name: string;
  required: boolean;
  note: string;
}

interface ComplianceItem {
  name: string;
  status: string;
  note: string;
}

interface ThresholdItem {
  value: number;
  label: string;
  short: string;
}

interface ApprovalItem {
  type: string;
  authority: string;
}

interface FeeCapItem {
  type: string;
  cap: string;
  authority: string;
}

interface ComplianceData {
  // Legacy fields (basic format)
  threshold?: string;
  required_documents?: string[] | DocItem[];
  far_citations?: string[];
  citations?: string[];
  vehicle?: string;
  recommendation?: string;
  reasoning?: string;
  message?: string;
  results?: unknown[];

  // Full get_requirements() output
  errors?: string[];
  warnings?: string[];
  documents_required?: DocItem[] | string[];
  compliance_items?: ComplianceItem[];
  competition_rules?: string;
  thresholds_triggered?: ThresholdItem[];
  thresholds_not_triggered?: ThresholdItem[];
  timeline_estimate?: { min_weeks: number; max_weeks: number };
  risk_allocation?: { contractor_risk_pct: number; category: string };
  fee_caps?: FeeCapItem[];
  pmr_checklist?: string;
  approvals_required?: ApprovalItem[];
  method?: { id: string; label: string; sub: string; far: string };
  contract_type?: { id: string; label: string; risk: number; category: string };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Detect whether data is in rich (get_requirements) format vs legacy. */
function isRichFormat(data: ComplianceData): boolean {
  const docs = data.documents_required ?? data.required_documents;
  if (Array.isArray(docs) && docs.length > 0 && typeof docs[0] === 'object' && 'name' in (docs[0] as DocItem)) {
    return true;
  }
  if (data.compliance_items || data.thresholds_triggered || data.risk_allocation || data.method) {
    return true;
  }
  return false;
}

function riskColor(pct: number): string {
  if (pct >= 80) return 'text-green-700';
  if (pct >= 50) return 'text-amber-700';
  return 'text-red-700';
}

function riskLabel(category: string): string {
  switch (category) {
    case 'fp': return 'Fixed-Price';
    case 'cr': return 'Cost-Reimbursement';
    case 'loe': return 'Level-of-Effort';
    default: return category;
  }
}

function formatDollars(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toLocaleString()}`;
}

// ---------------------------------------------------------------------------
// Section: Summary Banner
// ---------------------------------------------------------------------------

function SummaryBanner({ data }: { data: ComplianceData }) {
  const method = data.method;
  const ctype = data.contract_type;
  const timeline = data.timeline_estimate;
  const risk = data.risk_allocation;

  if (!method && !ctype) return null;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-gradient-to-r from-blue-50 to-slate-50 border border-blue-200 rounded-lg p-4">
      {method && (
        <div className="text-center">
          <div className="text-sm font-bold text-gray-900">{method.label}</div>
          <div className="text-[10px] text-blue-600 font-medium">FAR {method.far}</div>
          <div className="text-[9px] text-gray-400 mt-0.5">Method</div>
        </div>
      )}
      {ctype && (
        <div className="text-center">
          <div className="text-sm font-bold text-gray-900">{ctype.label}</div>
          <div className="text-[10px] text-gray-500">{riskLabel(ctype.category)}</div>
          <div className="text-[9px] text-gray-400 mt-0.5">Contract Type</div>
        </div>
      )}
      {timeline && (
        <div className="text-center">
          <div className="text-sm font-bold text-gray-900">
            {timeline.min_weeks}–{timeline.max_weeks} wks
          </div>
          <div className="text-[10px] text-gray-500">Estimated Lead Time</div>
          <div className="text-[9px] text-gray-400 mt-0.5">Timeline</div>
        </div>
      )}
      {risk && (
        <div className="text-center">
          <div className={`text-sm font-bold ${riskColor(risk.contractor_risk_pct)}`}>
            {risk.contractor_risk_pct}% Contractor
          </div>
          <div className="text-[10px] text-gray-500">{100 - risk.contractor_risk_pct}% Government</div>
          <div className="text-[9px] text-gray-400 mt-0.5">Risk Split</div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Errors & Warnings
// ---------------------------------------------------------------------------

function AlertBoxes({ errors, warnings }: { errors?: string[]; warnings?: string[] }) {
  if ((!errors || errors.length === 0) && (!warnings || warnings.length === 0)) return null;

  return (
    <div className="space-y-2">
      {errors?.map((e, i) => (
        <div key={`err-${i}`} className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 text-xs text-red-800">
          <span className="shrink-0 text-sm">&#x26D4;</span>
          <span>{e}</span>
        </div>
      ))}
      {warnings?.map((w, i) => (
        <div key={`warn-${i}`} className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs text-amber-800">
          <span className="shrink-0 text-sm">&#x26A0;&#xFE0F;</span>
          <span>{w}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Documents Required
// ---------------------------------------------------------------------------

function DocumentsTable({ docs }: { docs: DocItem[] }) {
  if (docs.length === 0) return null;

  const required = docs.filter(d => d.required);
  const optional = docs.filter(d => !d.required);

  return (
    <div>
      <SectionHeader label="Documents Required" count={required.length} total={docs.length} />
      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="w-8 px-2 py-2"></th>
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase tracking-wider text-[10px]">Document</th>
              <th className="text-left px-3 py-2 font-semibold text-gray-600 uppercase tracking-wider text-[10px]">Citation / Notes</th>
            </tr>
          </thead>
          <tbody>
            {required.map((d, i) => (
              <tr key={`req-${i}`} className="border-b border-gray-100 last:border-b-0">
                <td className="px-2 py-2 text-center">
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-green-100 text-green-700 text-[10px] font-bold">&#x2713;</span>
                </td>
                <td className="px-3 py-2 font-medium text-gray-900">{d.name}</td>
                <td className="px-3 py-2 text-gray-500">{d.note}</td>
              </tr>
            ))}
            {optional.map((d, i) => (
              <tr key={`opt-${i}`} className="border-b border-gray-100 last:border-b-0 opacity-60">
                <td className="px-2 py-2 text-center">
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded bg-gray-100 text-gray-400 text-[10px]">&mdash;</span>
                </td>
                <td className="px-3 py-2 text-gray-600">{d.name}</td>
                <td className="px-3 py-2 text-gray-400">{d.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Thresholds
// ---------------------------------------------------------------------------

function ThresholdBadges({ triggered, notTriggered }: { triggered?: ThresholdItem[]; notTriggered?: ThresholdItem[] }) {
  if ((!triggered || triggered.length === 0) && (!notTriggered || notTriggered.length === 0)) return null;

  return (
    <div>
      <SectionHeader label="Regulatory Thresholds" />
      <div className="flex flex-wrap gap-1.5">
        {triggered?.map((t, i) => (
          <span
            key={`hit-${i}`}
            className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded border border-amber-300 bg-amber-50 text-amber-800"
            title={`${t.label} — ${formatDollars(t.value)}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            {t.label}
          </span>
        ))}
        {notTriggered?.map((t, i) => (
          <span
            key={`miss-${i}`}
            className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-gray-200 bg-gray-50 text-gray-400"
            title={`${t.label} — ${formatDollars(t.value)}`}
          >
            {t.short}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Compliance Items
// ---------------------------------------------------------------------------

function ComplianceItemsList({ items }: { items: ComplianceItem[] }) {
  if (items.length === 0) return null;

  const statusDot = (status: string) => {
    switch (status) {
      case 'required': return 'bg-green-500';
      case 'conditional': return 'bg-amber-500';
      default: return 'bg-gray-300';
    }
  };

  return (
    <div>
      <SectionHeader label="Compliance Requirements" count={items.filter(i => i.status === 'required').length} total={items.length} />
      <div className="space-y-1">
        {items.map((item, i) => (
          <div key={i} className="flex items-start gap-2 py-1">
            <span className={`w-2 h-2 rounded-full mt-1 shrink-0 ${statusDot(item.status)}`} />
            <div className="min-w-0">
              <span className="text-xs font-medium text-gray-800">{item.name}</span>
              {item.note && (
                <span className="text-[10px] text-blue-600 ml-1.5">{item.note}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Risk Allocation Bar
// ---------------------------------------------------------------------------

function RiskBar({ risk }: { risk: { contractor_risk_pct: number; category: string } }) {
  const conPct = risk.contractor_risk_pct;
  const govPct = 100 - conPct;

  return (
    <div>
      <SectionHeader label="Risk Allocation" />
      <div className="space-y-1.5">
        <div className="flex justify-between text-[10px] text-gray-500">
          <span>Contractor ({conPct}%)</span>
          <span>Government ({govPct}%)</span>
        </div>
        <div className="h-6 flex rounded overflow-hidden border border-gray-200">
          <div
            className="bg-green-500 flex items-center justify-center text-[10px] font-bold text-white transition-all"
            style={{ width: `${conPct}%` }}
          >
            {conPct > 15 ? `${conPct}%` : ''}
          </div>
          <div
            className="bg-red-400 flex items-center justify-center text-[10px] font-bold text-white transition-all"
            style={{ width: `${govPct}%` }}
          >
            {govPct > 15 ? `${govPct}%` : ''}
          </div>
        </div>
        <div className="text-[10px] text-gray-400 text-center">
          {riskLabel(risk.category)}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Approvals Required
// ---------------------------------------------------------------------------

function ApprovalsChain({ approvals }: { approvals: ApprovalItem[] }) {
  if (approvals.length === 0) return null;

  return (
    <div>
      <SectionHeader label="Approvals Required" />
      <div className="flex items-center gap-0 flex-wrap">
        {approvals.map((a, i) => (
          <div key={i} className="flex items-center">
            <div className="border border-blue-200 bg-blue-50 rounded-lg px-3 py-2 text-center">
              <div className="text-[10px] font-bold text-blue-800">{a.type}</div>
              <div className="text-[9px] text-blue-600 mt-0.5 max-w-[140px]">{a.authority}</div>
            </div>
            {i < approvals.length - 1 && (
              <span className="text-gray-300 px-1 text-lg">&rarr;</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Additional Info (Competition, PMR, Fee Caps)
// ---------------------------------------------------------------------------

function AdditionalInfo({ data }: { data: ComplianceData }) {
  const [expanded, setExpanded] = useState(false);
  const hasContent = data.competition_rules || data.pmr_checklist || (data.fee_caps && data.fee_caps.length > 0);

  if (!hasContent) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[10px] font-bold uppercase text-gray-400 tracking-wider hover:text-gray-600 transition-colors"
      >
        <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>&#x25B6;</span>
        Additional Details
      </button>
      {expanded && (
        <div className="mt-2 space-y-3">
          {data.competition_rules && (
            <div>
              <div className="text-[10px] font-semibold text-gray-500 mb-1">Competition Rules</div>
              <p className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed">{data.competition_rules}</p>
            </div>
          )}
          {data.pmr_checklist && (
            <div>
              <div className="text-[10px] font-semibold text-gray-500 mb-1">PMR Checklist</div>
              <div className="inline-block text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
                {data.pmr_checklist}
              </div>
            </div>
          )}
          {data.fee_caps && data.fee_caps.length > 0 && (
            <div>
              <div className="text-[10px] font-semibold text-gray-500 mb-1">Fee Caps</div>
              <div className="flex flex-wrap gap-1.5">
                {data.fee_caps.map((fc, i) => (
                  <span key={i} className="text-[10px] font-semibold px-2 py-1 rounded border border-purple-300 bg-purple-50 text-purple-800">
                    {fc.type}: {fc.cap} ({fc.authority})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared: Section Header
// ---------------------------------------------------------------------------

function SectionHeader({ label, count, total }: { label: string; count?: number; total?: number }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <span className="text-[10px] font-bold uppercase text-gray-400 tracking-wider">{label}</span>
      {count !== undefined && total !== undefined && (
        <span className="text-[10px] text-gray-400">
          {count} required / {total} total
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legacy Panel (backward compat)
// ---------------------------------------------------------------------------

function LegacyPanel({ data, text }: { data: ComplianceData; text: string }) {
  const citations = data.far_citations || data.citations || [];
  const docs = Array.isArray(data.required_documents)
    ? (data.required_documents as string[])
    : [];

  return (
    <div className="border-t border-[#E5E9F0] bg-white px-3 py-2.5">
      <div className="text-[9px] font-bold uppercase text-blue-600 tracking-wider mb-1.5">
        Compliance Check
      </div>

      {(data.vehicle || data.recommendation) && (
        <div className="mb-2">
          <p className="text-xs font-medium text-gray-900">{data.vehicle || data.recommendation}</p>
          {data.reasoning && <p className="text-[10px] text-gray-500 mt-0.5">{data.reasoning}</p>}
        </div>
      )}

      {data.threshold && (
        <span className="inline-block text-[9px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded mb-1.5">
          Threshold: {data.threshold}
        </span>
      )}

      {citations.length > 0 && (
        <div className="mb-1.5">
          <div className="text-[10px] text-gray-400 mb-0.5">FAR Citations</div>
          <div className="flex flex-wrap gap-1">
            {citations.map((c, i) => (
              <span key={i} className="text-[9px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">
                {String(c)}
              </span>
            ))}
          </div>
        </div>
      )}

      {docs.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-400 mb-0.5">Required Documents</div>
          <ul className="text-[10px] text-gray-600 space-y-0.5">
            {docs.map((d, i) => (
              <li key={i} className="flex items-center gap-1">
                <span className="text-gray-400">&#x2022;</span>
                {d}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.message && !data.vehicle && !data.recommendation && (
        <p className="text-[10px] text-gray-600">{data.message}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rich Panel (full visualization)
// ---------------------------------------------------------------------------

function RichPanel({ data }: { data: ComplianceData }) {
  const docs: DocItem[] = (data.documents_required ?? data.required_documents ?? []) as DocItem[];

  return (
    <div className="bg-white space-y-5 py-1">
      <SummaryBanner data={data} />
      <AlertBoxes errors={data.errors} warnings={data.warnings} />
      <DocumentsTable docs={docs} />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div className="space-y-5">
          <ThresholdBadges
            triggered={data.thresholds_triggered}
            notTriggered={data.thresholds_not_triggered}
          />
          {data.compliance_items && data.compliance_items.length > 0 && (
            <ComplianceItemsList items={data.compliance_items} />
          )}
        </div>
        <div className="space-y-5">
          {data.risk_allocation && <RiskBar risk={data.risk_allocation} />}
          {data.approvals_required && data.approvals_required.length > 0 && (
            <ApprovalsChain approvals={data.approvals_required} />
          )}
        </div>
      </div>

      <AdditionalInfo data={data} />

      {/* Vehicle recommendation (can also appear in rich format) */}
      {(data.vehicle || data.recommendation) && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div className="text-[10px] font-bold uppercase text-blue-600 tracking-wider mb-1">
            Vehicle Recommendation
          </div>
          <p className="text-xs font-medium text-gray-900">{data.vehicle || data.recommendation}</p>
          {data.reasoning && <p className="text-[10px] text-gray-500 mt-1">{data.reasoning}</p>}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function ComplianceResultPanel({ text }: { text: string }) {
  let data: ComplianceData = {};
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      data = { results: parsed };
    } else if (typeof parsed === 'object' && parsed !== null) {
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

  if (isRichFormat(data)) {
    return <RichPanel data={data} />;
  }

  return <LegacyPanel data={data} text={text} />;
}
