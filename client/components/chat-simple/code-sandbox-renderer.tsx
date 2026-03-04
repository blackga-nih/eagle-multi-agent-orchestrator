'use client';

import { useState } from 'react';
import { CodeResult } from '@/lib/client-tools';

interface CodeSandboxRendererProps {
  language: 'javascript' | 'html' | string;
  source: string;
  result: CodeResult;
}

/**
 * Renders the output of a code tool execution.
 *
 * For JavaScript: shows a collapsible console log panel.
 * For HTML: renders the sandbox output in a visible srcdoc iframe
 *   (sandbox="allow-scripts" — no allow-same-origin) plus a collapsible
 *   console panel when there are captured logs.
 *
 * Security: The iframe uses sandbox="allow-scripts" only, which prevents
 * the sandboxed page from accessing localStorage, cookies, or the parent
 * DOM. This is the appropriate setting for a government-context code runner.
 */
export default function CodeSandboxRenderer({
  language,
  source,
  result,
}: CodeSandboxRendererProps) {
  const [logsExpanded, setLogsExpanded] = useState(false);
  const { logs = [], html, height } = result;
  const hasLogs = logs.length > 0;

  // Compute a reasonable iframe height — use the captured scroll height
  // from the execution sandbox when available, clamp between 80–400px.
  const iframeHeight = height ? Math.min(Math.max(height, 80), 400) : 200;

  return (
    <div className="my-2 rounded-xl border border-[#E5E9F0] overflow-hidden bg-white">
      {/* Source code header */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#F8FAFC] border-b border-[#E5E9F0]">
        <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
          {language} output
        </span>
        {hasLogs && (
          <button
            onClick={() => setLogsExpanded((v) => !v)}
            className="text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
          >
            {logsExpanded ? 'Hide console' : `Console (${logs.length})`}
          </button>
        )}
      </div>

      {/* HTML iframe output */}
      {language === 'html' && html && (
        <div className="w-full overflow-hidden">
          <iframe
            srcDoc={html}
            sandbox="allow-scripts"
            title="Code sandbox output"
            style={{ width: '100%', height: iframeHeight, border: 'none', display: 'block' }}
            scrolling="auto"
          />
        </div>
      )}

      {/* JavaScript — no visible output area, just console logs */}
      {language === 'javascript' && !hasLogs && (
        <div className="px-3 py-3">
          <span className="text-[11px] text-gray-400 italic">No console output</span>
        </div>
      )}

      {/* Console log panel */}
      {hasLogs && (
        <>
          {/* Collapsed summary */}
          {!logsExpanded && (
            <button
              onClick={() => setLogsExpanded(true)}
              className="w-full px-3 py-2 text-left text-[11px] text-gray-500 hover:bg-gray-50 transition-colors border-t border-[#E5E9F0]"
            >
              {logs.length} console {logs.length === 1 ? 'entry' : 'entries'} — click to expand
            </button>
          )}

          {/* Expanded log lines */}
          {logsExpanded && (
            <div className="border-t border-[#E5E9F0] bg-[#1e1e2e]">
              <div className="flex items-center justify-between px-3 py-1.5 border-b border-[#2a2d3a]">
                <span className="text-[10px] font-semibold text-[#cdd6f4] uppercase tracking-wider">
                  Console
                </span>
                <button
                  onClick={() => setLogsExpanded(false)}
                  className="text-[10px] text-[#6c7086] hover:text-[#cdd6f4] transition-colors"
                >
                  close
                </button>
              </div>
              <div className="px-3 py-2 max-h-48 overflow-y-auto font-mono text-[11px] space-y-0.5">
                {logs.map((line, i) => (
                  <div key={i} className="text-[#a6e3a1] whitespace-pre-wrap break-all leading-snug">
                    <span className="text-[#6c7086] select-none mr-2">{i + 1}</span>
                    {line}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
