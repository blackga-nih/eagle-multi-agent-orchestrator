'use client';

import ReactMarkdown from 'react-markdown';

/** Strip <metadata>...</metadata> tags from raw markdown before rendering. */
function stripMetadata(text: string): string {
  return text.replace(/<metadata[\s\S]*?<\/metadata>/gi, '');
}

export { stripMetadata };

export default function MarkdownResultPanel({ text }: { text: string }) {
  const clean = stripMetadata(text);
  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      <div className="relative">
        <div className="overflow-y-auto max-h-72 px-4 py-3">
          <div
            className="prose prose-xs prose-gray max-w-none text-[11px] leading-relaxed
                          [&_h1]:text-xs [&_h1]:font-bold [&_h1]:mt-2 [&_h1]:mb-1
                          [&_h2]:text-[11px] [&_h2]:font-bold [&_h2]:mt-2 [&_h2]:mb-1
                          [&_h3]:text-[11px] [&_h3]:font-semibold [&_h3]:mt-1.5 [&_h3]:mb-0.5
                          [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0
                          [&_code]:text-[10px] [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded"
          >
            <ReactMarkdown>{clean}</ReactMarkdown>
          </div>
        </div>
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent" />
      </div>
    </div>
  );
}
