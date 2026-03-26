/**
 * streaming-checkpoint.ts
 *
 * Lightweight localStorage-based checkpoint for in-flight SSE streams.
 * Written on a throttled interval during streaming so that a page refresh
 * mid-stream can recover the partial assistant message, tool call chips,
 * and state change cards.
 *
 * localStorage key pattern: `eagle_stream_cp_{sessionId}`
 * Each session has at most one checkpoint. Cleared on COMPLETE.
 */

import type { TrackedToolCall } from '@/components/chat-simple/simple-chat-interface';
import type { StateChangeEntry } from '@/contexts/chat-runtime-context';
import type { DocumentInfo } from '@/types/chat';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface StreamingCheckpoint {
    sessionId: string;
    requestId: string;
    streamingMsgId: string;
    text: string;
    toolCalls: TrackedToolCall[];
    stateChanges: StateChangeEntry[];
    documents: DocumentInfo[];
    updatedAt: number; // Date.now()
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const KEY_PREFIX = 'eagle_stream_cp_';
/** Checkpoints older than this are considered stale and discarded. */
const MAX_AGE_MS = 60 * 60 * 1000; // 1 hour

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Persist a streaming checkpoint to localStorage.
 * Safe to call frequently — the caller should throttle (e.g., every 2 s).
 */
export function saveCheckpoint(cp: StreamingCheckpoint): void {
    if (typeof window === 'undefined') return;
    // Skip saving empty checkpoints
    if (!cp.text && cp.toolCalls.length === 0 && cp.stateChanges.length === 0) return;
    try {
        localStorage.setItem(KEY_PREFIX + cp.sessionId, JSON.stringify(cp));
    } catch {
        // localStorage full or unavailable — silently drop
    }
}

/**
 * Load a checkpoint for the given session.
 * Returns null if missing, corrupt, or stale (>1 hour old).
 * Automatically removes stale checkpoints from localStorage.
 */
export function loadCheckpoint(sessionId: string): StreamingCheckpoint | null {
    if (typeof window === 'undefined') return null;
    try {
        const raw = localStorage.getItem(KEY_PREFIX + sessionId);
        if (!raw) return null;

        const parsed: StreamingCheckpoint = JSON.parse(raw);

        // Validate shape
        if (!parsed.sessionId || !parsed.streamingMsgId || typeof parsed.text !== 'string') {
            clearCheckpoint(sessionId);
            return null;
        }

        // Garbage-collect stale checkpoints
        if (Date.now() - (parsed.updatedAt ?? 0) > MAX_AGE_MS) {
            clearCheckpoint(sessionId);
            return null;
        }

        // Ensure arrays exist (defensive — old data may lack new fields)
        parsed.toolCalls = parsed.toolCalls ?? [];
        parsed.stateChanges = parsed.stateChanges ?? [];
        parsed.documents = parsed.documents ?? [];

        return parsed;
    } catch {
        // Corrupt JSON — remove it
        clearCheckpoint(sessionId);
        return null;
    }
}

/** Remove a checkpoint for the given session. */
export function clearCheckpoint(sessionId: string): void {
    if (typeof window === 'undefined') return;
    try {
        localStorage.removeItem(KEY_PREFIX + sessionId);
    } catch {
        // ignore
    }
}
