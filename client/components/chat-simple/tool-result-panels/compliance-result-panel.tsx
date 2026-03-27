'use client';

interface ComplianceData {
  thresholds?: Record<string, string | number>[];
  threshold?: string;
  required_documents?: string[];
  far_citations?: string[];
  citations?: string[];
  vehicle?: string;
  recommendation?: string;
  reasoning?: string;
  message?: string;
  results?: unknown[];
}

export default function ComplianceResultPanel({ text }: { text: string }) {
  let data: ComplianceData = {};
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      // Array of compliance items — wrap in results
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

  const citations = data.far_citations || data.citations || [];
  const docs = data.required_documents || [];

  return (
    <div className="border-t border-[#E5E9F0] bg-white px-3 py-2.5">
      <div className="text-[9px] font-bold uppercase text-blue-600 tracking-wider mb-1.5">
        Compliance Check
      </div>

      {/* Vehicle recommendation */}
      {(data.vehicle || data.recommendation) && (
        <div className="mb-2">
          <p className="text-xs font-medium text-gray-900">{data.vehicle || data.recommendation}</p>
          {data.reasoning && <p className="text-[10px] text-gray-500 mt-0.5">{data.reasoning}</p>}
        </div>
      )}

      {/* Threshold badges */}
      {data.threshold && (
        <span className="inline-block text-[9px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded mb-1.5">
          Threshold: {data.threshold}
        </span>
      )}

      {/* FAR citations */}
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

      {/* Required documents */}
      {docs.length > 0 && (
        <div>
          <div className="text-[10px] text-gray-400 mb-0.5">Required Documents</div>
          <ul className="text-[10px] text-gray-600 space-y-0.5">
            {docs.map((d, i) => (
              <li key={i} className="flex items-center gap-1">
                <span className="text-gray-400">{'•'}</span>
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
