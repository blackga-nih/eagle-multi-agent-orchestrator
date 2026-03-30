'use client';

interface ToolTiming {
  name: string;
  duration_ms: number;
  error?: string;
}

interface TimingMetadata {
  tool_timings?: ToolTiming[];
  total_duration_ms?: number;
  input_tokens?: number;
  output_tokens?: number;
}

export default function ToolTimingSummary({ metadata }: { metadata: TimingMetadata }) {
  const timings = metadata.tool_timings || [];
  const totalMs = metadata.total_duration_ms || timings.reduce((s, t) => s + t.duration_ms, 0);
  const maxMs = Math.max(...timings.map((t) => t.duration_ms), 1);

  return (
    <div className="space-y-2">
      {/* Total duration */}
      <div className="flex items-center gap-2">
        <span className="text-[9px] font-bold uppercase text-gray-400 tracking-wider">
          Duration
        </span>
        <span className="text-sm font-bold text-gray-700">{(totalMs / 1000).toFixed(1)}s</span>
      </div>

      {/* Per-tool bars */}
      {timings.length > 0 && (
        <div className="space-y-1">
          {timings.map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-[10px]">
              <span
                className={`w-24 truncate shrink-0 ${t.error ? 'text-red-600 font-medium' : 'text-gray-600'}`}
              >
                {t.name}
              </span>
              <div className="flex-1 h-2 bg-gray-100 rounded overflow-hidden">
                <div
                  className={`h-full rounded ${t.error ? 'bg-red-400' : 'bg-blue-400'}`}
                  style={{ width: `${Math.max((t.duration_ms / maxMs) * 100, 2)}%` }}
                />
              </div>
              <span className="text-gray-400 shrink-0 w-12 text-right">{t.duration_ms}ms</span>
            </div>
          ))}
        </div>
      )}

      {/* Token usage */}
      {(metadata.input_tokens || metadata.output_tokens) && (
        <div className="flex items-center gap-3 text-[10px] text-gray-400 pt-1 border-t border-gray-100">
          {metadata.input_tokens && <span>Input: {metadata.input_tokens.toLocaleString()}</span>}
          {metadata.output_tokens && <span>Output: {metadata.output_tokens.toLocaleString()}</span>}
        </div>
      )}
    </div>
  );
}
