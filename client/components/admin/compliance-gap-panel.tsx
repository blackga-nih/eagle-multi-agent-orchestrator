'use client';

import { useState } from 'react';
import { Search, CheckCircle, AlertCircle, XCircle, Loader2 } from 'lucide-react';

// --- Types ---

interface GapItem {
  requirement_name: string;
  far_citations?: string[];
  covering_templates?: string[];
}

interface GapAnalysisResult {
  coverage_percentage: number;
  covered: GapItem[];
  partial: GapItem[];
  gaps: GapItem[];
}

interface FormState {
  value: string;
  method: string;
  type: string;
  is_it: boolean;
  is_services: boolean;
  is_small_business: boolean;
}

const ACQUISITION_METHODS = [
  { value: 'micro', label: 'Micro-Purchase' },
  { value: 'sap', label: 'Simplified Acquisition' },
  { value: 'negotiated', label: 'Negotiated' },
  { value: 'fss', label: 'Federal Supply Schedule' },
  { value: 'bpa-est', label: 'BPA (Establish)' },
  { value: 'bpa-call', label: 'BPA (Call)' },
  { value: 'idiq', label: 'IDIQ (Base)' },
  { value: 'idiq-order', label: 'IDIQ (Order)' },
  { value: 'sole', label: 'Sole Source' },
];

const CONTRACT_TYPES = [
  { value: 'ffp', label: 'Firm-Fixed-Price (FFP)' },
  { value: 'fp-epa', label: 'FP with EPA' },
  { value: 'fpi', label: 'Fixed-Price Incentive (FPI)' },
  { value: 'cpff', label: 'Cost-Plus-Fixed-Fee (CPFF)' },
  { value: 'cpif', label: 'Cost-Plus-Incentive-Fee (CPIF)' },
  { value: 'cpaf', label: 'Cost-Plus-Award-Fee (CPAF)' },
  { value: 'tm', label: 'Time-and-Materials (T&M)' },
  { value: 'lh', label: 'Labor-Hour (LH)' },
];

// --- Sub-components ---

function FarBadge({ citation }: { citation: string }) {
  return (
    <span className="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">
      {citation}
    </span>
  );
}

function RequirementCard({ item }: { item: GapItem }) {
  return (
    <div className="bg-white rounded-md border border-gray-100 p-2.5 space-y-1.5">
      <p className="text-xs font-medium text-gray-800 leading-snug">{item.requirement_name}</p>

      {item.far_citations && item.far_citations.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {item.far_citations.map((c) => (
            <FarBadge key={c} citation={c} />
          ))}
        </div>
      )}

      {item.covering_templates && item.covering_templates.length > 0 && (
        <div className="text-[10px] text-gray-500">
          <span className="font-semibold text-gray-600">Templates: </span>
          {item.covering_templates.join(', ')}
        </div>
      )}
    </div>
  );
}

function Column({
  title,
  items,
  borderColor,
  headerColor,
  icon,
  emptyMessage,
}: {
  title: string;
  items: GapItem[];
  borderColor: string;
  headerColor: string;
  icon: React.ReactNode;
  emptyMessage: string;
}) {
  return (
    <div className={`flex flex-col rounded-xl border-2 ${borderColor} bg-white overflow-hidden`}>
      <div className={`flex items-center gap-2 px-3 py-2 ${headerColor}`}>
        {icon}
        <span className="text-xs font-bold uppercase tracking-wide">{title}</span>
        <span className="ml-auto text-xs font-semibold opacity-70">{items.length}</span>
      </div>
      <div className="flex-1 p-2 space-y-2 overflow-y-auto max-h-96">
        {items.length === 0 ? (
          <p className="text-xs text-gray-400 italic text-center py-4">{emptyMessage}</p>
        ) : (
          items.map((item, i) => <RequirementCard key={i} item={item} />)
        )}
      </div>
    </div>
  );
}

// --- Coverage meter ---

function CoverageBar({ percentage }: { percentage: number }) {
  const pct = Math.min(100, Math.max(0, Math.round(percentage)));
  const color = pct >= 80 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';
  const textColor = pct >= 80 ? 'text-green-700' : pct >= 50 ? 'text-amber-700' : 'text-red-700';

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-sm font-bold tabular-nums ${textColor}`}>{pct}%</span>
      <span className="text-xs text-gray-500">coverage</span>
    </div>
  );
}

// --- Main component ---

export interface ComplianceGapPanelProps {
  token?: string | null;
}

const INITIAL_FORM: FormState = {
  value: '',
  method: '',
  type: '',
  is_it: false,
  is_services: false,
  is_small_business: false,
};

export default function ComplianceGapPanel({ token }: ComplianceGapPanelProps) {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [result, setResult] = useState<GapAnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const target = e.target;
    if (target instanceof HTMLInputElement && target.type === 'checkbox') {
      setForm((prev) => ({ ...prev, [target.name]: target.checked }));
    } else {
      setForm((prev) => ({ ...prev, [target.name]: target.value }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);

    try {
      const params = new URLSearchParams({
        ...(form.value && { value: form.value }),
        ...(form.method && { method: form.method }),
        ...(form.type && { type: form.type }),
        is_it: String(form.is_it),
        is_services: String(form.is_services),
        is_small_business: String(form.is_small_business),
      });

      const headers: HeadersInit = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`/api/compliance/gap-analysis?${params.toString()}`, { headers });

      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `HTTP ${res.status}`);
      }

      const data: GapAnalysisResult = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const labelClass = 'block text-xs font-semibold text-gray-600 mb-1';
  const inputClass =
    'w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400 text-gray-800 bg-white';

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100 bg-gray-50">
        <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
          <Search className="w-4 h-4 text-blue-600" />
          Compliance Gap Analysis
        </h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Evaluate template coverage against FAR/DFARS requirements for an acquisition.
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="px-5 py-4 border-b border-gray-100">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          {/* Contract Value */}
          <div>
            <label htmlFor="cgp-value" className={labelClass}>
              Contract Value ($)
            </label>
            <input
              id="cgp-value"
              name="value"
              type="number"
              min="0"
              step="1"
              value={form.value}
              onChange={handleChange}
              placeholder="e.g. 250000"
              className={inputClass}
            />
          </div>

          {/* Acquisition Method */}
          <div>
            <label htmlFor="cgp-method" className={labelClass}>
              Acquisition Method
            </label>
            <select
              id="cgp-method"
              name="method"
              value={form.method}
              onChange={handleChange}
              className={inputClass}
            >
              <option value="">Select method...</option>
              {ACQUISITION_METHODS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          {/* Contract Type */}
          <div>
            <label htmlFor="cgp-type" className={labelClass}>
              Contract Type
            </label>
            <select
              id="cgp-type"
              name="type"
              value={form.type}
              onChange={handleChange}
              className={inputClass}
            >
              <option value="">Select type...</option>
              {CONTRACT_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Checkbox toggles */}
        <div className="flex flex-wrap gap-4 mb-4">
          {(
            [
              { name: 'is_it', label: 'IT Acquisition' },
              { name: 'is_services', label: 'Services' },
              { name: 'is_small_business', label: 'Small Business Set-Aside' },
            ] as { name: keyof FormState; label: string }[]
          ).map(({ name, label }) => (
            <label key={name} className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                name={name}
                checked={form[name] as boolean}
                onChange={handleChange}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-400"
              />
              <span className="text-sm text-gray-700">{label}</span>
            </label>
          ))}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Analyzing...
            </>
          ) : (
            <>
              <Search className="w-4 h-4" />
              Run Gap Analysis
            </>
          )}
        </button>
      </form>

      {/* Error state */}
      {error && (
        <div className="px-5 py-3 bg-red-50 border-b border-red-100">
          <p className="text-xs text-red-700 flex items-center gap-1.5">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="px-5 py-4">
          {/* Coverage bar */}
          <div className="mb-5">
            <div className="text-[10px] font-bold uppercase tracking-wide text-gray-400 mb-2">
              Overall Coverage
            </div>
            <CoverageBar percentage={result.coverage_percentage} />
          </div>

          {/* Three-column layout */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Column
              title="Covered"
              items={result.covered}
              borderColor="border-green-300"
              headerColor="bg-green-50 text-green-800"
              icon={<CheckCircle className="w-4 h-4 text-green-600" />}
              emptyMessage="No fully covered requirements"
            />
            <Column
              title="Partial"
              items={result.partial}
              borderColor="border-amber-300"
              headerColor="bg-amber-50 text-amber-800"
              icon={<AlertCircle className="w-4 h-4 text-amber-600" />}
              emptyMessage="No partial requirements"
            />
            <Column
              title="Gaps"
              items={result.gaps}
              borderColor="border-red-300"
              headerColor="bg-red-50 text-red-800"
              icon={<XCircle className="w-4 h-4 text-red-600" />}
              emptyMessage="No gaps identified"
            />
          </div>
        </div>
      )}

      {/* Empty state — before first run */}
      {!result && !loading && !error && (
        <div className="px-5 py-10 text-center">
          <Search className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-sm text-gray-400">
            Configure the acquisition parameters above and run the analysis.
          </p>
        </div>
      )}
    </div>
  );
}
