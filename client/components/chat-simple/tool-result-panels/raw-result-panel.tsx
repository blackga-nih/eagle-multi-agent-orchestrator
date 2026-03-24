'use client';

export default function RawResultPanel({
  text,
  errorText,
}: {
  text: string | null;
  errorText: string | null;
}) {
  return (
    <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
      {errorText ? (
        <p className="text-red-600 font-mono text-[11px] whitespace-pre-wrap break-all">
          {errorText}
        </p>
      ) : text ? (
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all max-h-48 overflow-y-auto">
          {text}
        </pre>
      ) : null}
    </div>
  );
}
