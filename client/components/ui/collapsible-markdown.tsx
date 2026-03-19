'use client';

import { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronRight } from 'lucide-react';
import { markdownComponents } from './markdown-renderer';

interface Section {
  level: number;
  title: string;
  body: string;
}

function parseSections(markdown: string): { preamble: string; sections: Section[] } {
  const lines = markdown.split('\n');
  let preamble = '';
  const sections: Section[] = [];
  let current: Section | null = null;

  for (const line of lines) {
    const match = line.match(/^(#{1,4})\s+(.+)/);
    if (match) {
      if (current) {
        sections.push(current);
      } else {
        // Everything before the first heading is preamble
        preamble = preamble.trimEnd();
      }
      current = { level: match[1].length, title: match[2], body: '' };
    } else if (current) {
      current.body += line + '\n';
    } else {
      preamble += line + '\n';
    }
  }
  if (current) {
    sections.push(current);
  }

  // Trim trailing whitespace from section bodies
  for (const s of sections) {
    s.body = s.body.trimEnd();
  }

  return { preamble: preamble.trim(), sections };
}

interface CollapsibleMarkdownProps {
  content: string;
  defaultExpanded?: boolean;
}

export default function CollapsibleMarkdown({ content, defaultExpanded = false }: CollapsibleMarkdownProps) {
  const { preamble, sections } = useMemo(() => parseSections(content), [content]);
  const [expanded, setExpanded] = useState<Record<number, boolean>>(() => {
    if (defaultExpanded) {
      return Object.fromEntries(sections.map((_, i) => [i, true]));
    }
    return {};
  });

  function toggle(index: number) {
    setExpanded(prev => ({ ...prev, [index]: !prev[index] }));
  }

  function expandAll() {
    setExpanded(Object.fromEntries(sections.map((_, i) => [i, true])));
  }

  function collapseAll() {
    setExpanded({});
  }

  const allExpanded = sections.length > 0 && sections.every((_, i) => expanded[i]);

  if (sections.length === 0) {
    // No headings — render as plain markdown
    return (
      <div className="prose prose-sm max-w-none bg-white rounded-xl border border-gray-200 p-5">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
    );
  }

  const headingSizes: Record<number, string> = {
    1: 'text-lg font-bold text-gray-900',
    2: 'text-base font-semibold text-gray-900',
    3: 'text-sm font-semibold text-gray-800',
    4: 'text-sm font-medium text-gray-800',
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
      {/* Expand/Collapse all toggle */}
      <div className="flex justify-end px-4 py-2 bg-gray-50 rounded-t-xl">
        <button
          onClick={allExpanded ? collapseAll : expandAll}
          className="text-xs text-blue-600 hover:text-blue-800 font-medium"
        >
          {allExpanded ? 'Collapse All' : 'Expand All'}
        </button>
      </div>

      {/* Preamble — always visible */}
      {preamble && (
        <div className="px-5 py-4 prose prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {preamble}
          </ReactMarkdown>
        </div>
      )}

      {/* Collapsible sections */}
      {sections.map((section, i) => {
        const isOpen = !!expanded[i];
        return (
          <div key={i}>
            <button
              onClick={() => toggle(i)}
              className="w-full flex items-center gap-2 px-5 py-3 text-left hover:bg-gray-50 transition-colors"
              style={{ paddingLeft: `${1.25 + (section.level - 1) * 0.75}rem` }}
            >
              <ChevronRight
                className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}
              />
              <span className={headingSizes[section.level] || headingSizes[2]}>
                {section.title}
              </span>
            </button>
            {isOpen && section.body && (
              <div
                className="px-5 pb-4 prose prose-sm max-w-none"
                style={{ paddingLeft: `${1.25 + (section.level - 1) * 0.75 + 1.5}rem` }}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                  {section.body}
                </ReactMarkdown>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
