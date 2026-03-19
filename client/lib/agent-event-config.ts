/**
 * Shared agent event configuration for log display components.
 *
 * Consolidates duplicate event formatting logic from:
 * - components/chat-simple/agent-logs.tsx
 * - components/chat/multi-agent-logs.tsx
 *
 * Created: 2026-03-19 (Phase 2 refactor)
 */

import { AuditLogEntry } from '@/types/stream';

/**
 * Event type display configuration
 */
export const EVENT_CONFIG = {
  text: {
    label: 'Report',
    badge: 'bg-blue-100 text-blue-700',
    icon: 'MessageSquare',
  },
  reasoning: {
    label: 'Reasoning',
    badge: 'bg-purple-100 text-purple-700',
    icon: 'Brain',
  },
  tool_use: {
    label: 'Tool',
    badge: 'bg-yellow-100 text-yellow-800',
    icon: 'Cpu',
  },
  tool_result: {
    label: 'Result',
    badge: 'bg-orange-100 text-orange-700',
    icon: 'FileText',
  },
  handoff: {
    label: 'Handoff',
    badge: 'bg-pink-100 text-pink-700',
    icon: 'ArrowRight',
  },
  complete: {
    label: 'Complete',
    badge: 'bg-gray-100 text-gray-600',
    icon: 'CheckCircle2',
  },
  error: {
    label: 'Error',
    badge: 'bg-red-100 text-red-700',
    icon: 'AlertCircle',
  },
  user_input: {
    label: 'User Input',
    badge: 'bg-cyan-100 text-cyan-700',
    icon: 'User',
  },
  form_submit: {
    label: 'Form Submit',
    badge: 'bg-teal-100 text-teal-700',
    icon: 'ClipboardCheck',
  },
  metadata: {
    label: 'Metadata',
    badge: 'bg-indigo-100 text-indigo-700',
    icon: 'Code',
  },
  elicitation: {
    label: 'Question',
    badge: 'bg-green-100 text-green-700',
    icon: 'Zap',
  },
  agent_status: {
    label: 'Status',
    badge: 'bg-slate-100 text-slate-700',
    icon: 'Activity',
  },
} as const;

export type EventType = keyof typeof EVENT_CONFIG;

/**
 * Get display label for an event type
 */
export function formatEventType(type: string, log?: AuditLogEntry): string {
  const config = EVENT_CONFIG[type as EventType];
  if (!config) return type;

  // Special handling for tool events to show tool name
  if (type === 'tool_use' && log?.tool_use?.name) {
    return `Tool: ${log.tool_use.name}`;
  }
  if (type === 'tool_result' && log?.tool_result?.name) {
    return `Result: ${log.tool_result.name}`;
  }

  return config.label;
}

/**
 * Get badge CSS classes for an event type
 */
export function getEventTypeBadge(type: string): string {
  return EVENT_CONFIG[type as EventType]?.badge ?? 'bg-gray-100 text-gray-600';
}

/**
 * Get icon name for an event type (for use with lucide-react)
 */
export function getEventIconName(type: string): string {
  return EVENT_CONFIG[type as EventType]?.icon ?? 'Code';
}

/**
 * Check if an event type should be filtered out from display
 */
export function shouldFilterEvent(type: string): boolean {
  // Filter out reasoning events by default
  return type === 'reasoning';
}

/**
 * A display entry that may collapse multiple raw log entries.
 * Used by both agent log components for grouping consecutive text events.
 */
export interface DisplayEntry {
  /** Primary log entry (or the last in a collapsed group). */
  log: AuditLogEntry;
  /** All raw log entries in this group (>1 when consecutive text events are collapsed). */
  group: AuditLogEntry[];
  /** Combined content for collapsed text groups. */
  mergedContent?: string;
}

/**
 * Collapse consecutive text events from the same agent into a single entry.
 * Filter out reasoning events. All other event types pass through 1:1.
 */
export function buildDisplayEntries(logs: AuditLogEntry[]): DisplayEntry[] {
  const entries: DisplayEntry[] = [];
  let textBuffer: AuditLogEntry[] = [];
  let textAgent: string | null = null;

  function flushTextBuffer() {
    if (textBuffer.length === 0) return;
    const merged = textBuffer.map(l => l.content ?? '').join('');
    entries.push({
      log: textBuffer[textBuffer.length - 1],
      group: [...textBuffer],
      mergedContent: merged,
    });
    textBuffer = [];
    textAgent = null;
  }

  for (const log of logs) {
    // Skip reasoning events
    if (shouldFilterEvent(log.type)) continue;

    if (log.type === 'text') {
      // Accumulate consecutive text events from the same agent
      if (textAgent && textAgent !== log.agent_id) {
        flushTextBuffer();
      }
      textBuffer.push(log);
      textAgent = log.agent_id ?? null;
    } else {
      // Non-text event: flush any pending text, then add this event
      flushTextBuffer();
      entries.push({ log, group: [log] });
    }
  }

  // Flush any remaining text buffer
  flushTextBuffer();

  return entries;
}
