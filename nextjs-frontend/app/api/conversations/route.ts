/**
 * Conversations API Route
 *
 * GET /api/conversations?user_id=xxx
 *   - List all agent sessions for a user
 *   - Returns sessions with message counts
 *
 * This is the source of truth for cross-device sync.
 * localStorage acts as a local cache.
 */

import { NextRequest, NextResponse } from 'next/server';
import { memoryStore } from '@/lib/conversation-store';

// Backend URL - in production this would be the database service
const BACKEND_URL = process.env.AGENTCORE_URL || 'http://localhost:8081';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get('user_id');

  if (!userId) {
    return NextResponse.json(
      { error: 'Missing required parameter: user_id' },
      { status: 400 }
    );
  }

  try {
    // Try backend first
    const response = await fetch(`${BACKEND_URL}/conversations?user_id=${userId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(3000),
    });

    if (response.ok) {
      const data = await response.json();
      return NextResponse.json(data);
    }
  } catch {
    // Backend unavailable - use in-memory store
  }

  // Return from in-memory store (development mode)
  const userStore = memoryStore.get(userId);

  if (!userStore) {
    // Return empty store for new user
    return NextResponse.json({
      userId,
      sessions: {
        frontend: null,
        backend: null,
        aws_admin: null,
        analyst: null,
      },
      sharedContext: {},
      lastUpdated: new Date().toISOString(),
    });
  }

  return NextResponse.json({
    userId,
    sessions: userStore.sessions,
    sharedContext: userStore.sharedContext,
    lastUpdated: userStore.lastUpdated,
  });
}

/**
 * Bulk update all sessions (for initial sync from localStorage)
 */
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { userId, sessions, sharedContext } = body;

    if (!userId) {
      return NextResponse.json(
        { error: 'Missing required field: userId' },
        { status: 400 }
      );
    }

    try {
      // Try backend first
      const response = await fetch(`${BACKEND_URL}/conversations`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(5000),
      });

      if (response.ok) {
        const data = await response.json();
        return NextResponse.json(data);
      }
    } catch {
      // Backend unavailable - use in-memory store
    }

    // Update in-memory store (development mode)
    const now = new Date().toISOString();
    memoryStore.set(userId, {
      sessions: sessions || {
        frontend: null,
        backend: null,
        aws_admin: null,
        analyst: null,
      },
      sharedContext: sharedContext || {},
      lastUpdated: now,
    });

    return NextResponse.json({
      success: true,
      lastUpdated: now,
    });

  } catch (error) {
    console.error('Conversations PUT error:', error);
    return NextResponse.json(
      { error: 'Failed to update conversations' },
      { status: 500 }
    );
  }
}

