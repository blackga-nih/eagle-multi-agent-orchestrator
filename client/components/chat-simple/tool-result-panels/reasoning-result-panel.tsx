'use client';

export default function ReasoningResultPanel({
  text,
  input,
}: {
  text: string;
  input: Record<string, unknown>;
}) {
  const thought = String(input.thought ?? input.query ?? '');
  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      {thought && (
        <div className="px-3 py-2 border-b border-gray-100">
          <div className="text-[10px] text-gray-400 mb-0.5">Thought</div>
          <p className="text-xs text-gray-600 italic whitespace-pre-wrap">{thought}</p>
        </div>
      )}
      {text && (
        <div className="px-3 py-2">
          <div className="text-[10px] text-gray-400 mb-0.5">Result</div>
          <pre className="text-[11px] text-gray-700 font-mono whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
            {text}
          </pre>
        </div>
      )}
    </div>
  );
}
