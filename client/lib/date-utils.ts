/**
 * Unified date/time formatting utilities for EAGLE frontend.
 *
 * Consolidates duplicate implementations from:
 * - components/chat-simple/agent-logs.tsx
 * - components/chat-simple/activity-panel.tsx
 * - app/documents/[id]/page.tsx
 * - app/admin/tests/page.tsx
 * - lib/mock-data.ts
 *
 * Created: 2026-03-19 (Phase 1 refactor)
 */

/**
 * Format timestamp as relative time (e.g., "just now", "2m ago", "3h ago", "1d ago")
 * Falls back to localized date for timestamps older than 7 days.
 */
export function formatRelativeTime(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return formatDate(date);
  } catch {
    return '';
  }
}

/**
 * Format timestamp as time only (e.g., "02:30:45")
 * Includes seconds for precision in logs and activity feeds.
 */
export function formatTime(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '';
  }
}

/**
 * Format timestamp as short time (e.g., "2:30 PM")
 * Without seconds, for display contexts where precision isn't needed.
 */
export function formatTimeShort(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

/**
 * Format timestamp as date only (e.g., "Mar 19")
 */
export function formatDate(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return typeof timestamp === 'string' ? timestamp : '';
  }
}

/**
 * Format timestamp as full date (e.g., "Mar 19, 2026")
 */
export function formatDateFull(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return date.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return typeof timestamp === 'string' ? timestamp : '';
  }
}

/**
 * Format timestamp as full datetime (e.g., "3/19/2026, 2:30:45 PM")
 * Uses browser's default locale formatting.
 */
export function formatDateTime(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return date.toLocaleString();
  } catch {
    return typeof timestamp === 'string' ? timestamp : '';
  }
}

/**
 * Format timestamp as ISO string (e.g., "2026-03-19T14:30:45.000Z")
 * Useful for API calls and data serialization.
 */
export function formatISO(timestamp: string | Date): string {
  try {
    const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
    return date.toISOString();
  } catch {
    return typeof timestamp === 'string' ? timestamp : '';
  }
}
