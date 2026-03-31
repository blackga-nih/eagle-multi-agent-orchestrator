'use client';

import { useMemo } from 'react';
import MarkdownRenderer from '@/components/ui/markdown-renderer';

/** Internal fields to skip when converting JSON to markdown. */
const SKIP_KEYS = new Set([
  'PK', 'SK', 'created_at', 'updated_at', 'entity_type',
  'is_active', 'content_type', 'version',
]);

/** Fields that contain narrative text and should be rendered as top-level prose. */
const NARRATIVE_KEYS = [
  'report', 'message', 'answer', 'summary', 'content',
  'description', 'text', 'output', 'result', 'response',
];

/**
 * Convert a JSON value to a GFM table if it's an array of objects with
 * consistent keys. Returns null if the shape doesn't fit.
 */
function tryTable(arr: Record<string, unknown>[]): string | null {
  if (arr.length === 0) return null;
  const keys = Object.keys(arr[0]).filter((k) => !SKIP_KEYS.has(k));
  if (keys.length === 0 || keys.length > 8) return null;

  // Check that at least half the rows share the same keys
  const consistent = arr.filter(
    (row) => keys.filter((k) => k in row).length >= keys.length * 0.5,
  );
  if (consistent.length < arr.length * 0.5) return null;

  const header = `| ${keys.map((k) => k.replace(/_/g, ' ')).join(' | ')} |`;
  const sep = `| ${keys.map(() => '---').join(' | ')} |`;
  const rows = consistent.slice(0, 50).map((row) => {
    const cells = keys.map((k) => {
      const v = row[k];
      if (v === null || v === undefined) return '';
      const s = typeof v === 'string' ? v : JSON.stringify(v);
      return s.replace(/\|/g, '\\|').replace(/\n/g, ' ').slice(0, 120);
    });
    return `| ${cells.join(' | ')} |`;
  });
  return [header, sep, ...rows].join('\n');
}

/** Format a single key-value pair as a markdown line. */
function kvLine(key: string, value: unknown): string {
  const label = key.replace(/_/g, ' ');
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return `**${label}:** ${value ? 'Yes' : 'No'}`;
  if (typeof value === 'number') return `**${label}:** ${value.toLocaleString()}`;
  if (typeof value === 'string') {
    if (value.length > 500) return `**${label}:**\n\n${value.slice(0, 500)}...`;
    return `**${label}:** ${value}`;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '';
    if (value.every((v) => typeof v === 'string')) {
      return `**${label}:**\n${value.map((v) => `- ${v}`).join('\n')}`;
    }
    // Array of objects — try table
    if (value.every((v) => typeof v === 'object' && v !== null)) {
      const table = tryTable(value as Record<string, unknown>[]);
      if (table) return `### ${label}\n\n${table}`;
    }
    return `**${label}:** ${JSON.stringify(value).slice(0, 300)}`;
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(
      ([k]) => !SKIP_KEYS.has(k),
    );
    if (entries.length === 0) return '';
    const inner = entries.map(([k, v]) => kvLine(k, v)).filter(Boolean).join('\n');
    return `### ${label}\n\n${inner}`;
  }
  return `**${label}:** ${String(value)}`;
}

/**
 * Convert a JSON string (or plain text) into human-readable markdown.
 * Handles objects, arrays, nested structures, and graceful fallback.
 */
function jsonToMarkdown(text: string, _toolName: string): string {
  // Try to parse as JSON
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    // Not valid JSON — return as-is (plain text or truncated JSON)
    return text;
  }

  // If it parsed to a string, return directly
  if (typeof data === 'string') return data;

  // If it's an array, try rendering as a table or list
  if (Array.isArray(data)) {
    if (data.length === 0) return '*No results*';
    if (data.every((v) => typeof v === 'string')) {
      return data.map((v) => `- ${v}`).join('\n');
    }
    if (data.every((v) => typeof v === 'object' && v !== null)) {
      const table = tryTable(data as Record<string, unknown>[]);
      if (table) return table;
    }
    return data.map((item, i) => `${i + 1}. ${JSON.stringify(item)}`).join('\n');
  }

  // Object — extract narrative fields first, then structured data
  if (typeof data === 'object' && data !== null) {
    const obj = data as Record<string, unknown>;
    const parts: string[] = [];

    // Extract narrative prose
    for (const key of NARRATIVE_KEYS) {
      const val = obj[key];
      if (typeof val === 'string' && val.length > 0) {
        parts.push(val.length > 2000 ? val.slice(0, 2000) + '...' : val);
      }
    }

    // Extract status/error as callouts
    if (obj.error && typeof obj.error === 'string') {
      parts.push(`> **Error:** ${obj.error}`);
    }
    if (obj.status && typeof obj.status === 'string' && !NARRATIVE_KEYS.includes('status')) {
      parts.push(`**Status:** ${obj.status}`);
    }

    // Remaining key-value pairs
    const usedKeys = new Set([...NARRATIVE_KEYS, 'error', 'status']);
    const remaining = Object.entries(obj).filter(
      ([k]) => !usedKeys.has(k) && !SKIP_KEYS.has(k),
    );

    if (remaining.length > 0) {
      if (parts.length > 0) parts.push('---');
      for (const [k, v] of remaining) {
        const line = kvLine(k, v);
        if (line) parts.push(line);
      }
    }

    const result = parts.join('\n\n');
    return result || '*Empty result*';
  }

  return String(data);
}

export default function MarkdownFallbackPanel({
  text,
  toolName,
}: {
  text: string;
  toolName: string;
}) {
  const markdown = useMemo(() => jsonToMarkdown(text, toolName), [text, toolName]);

  return (
    <div className="border-t border-[#E5E9F0] bg-white">
      <div className="relative">
        <div className="overflow-y-auto max-h-[60vh] px-5 py-4">
          <MarkdownRenderer content={markdown} />
        </div>
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-white to-transparent" />
      </div>
    </div>
  );
}
