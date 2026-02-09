/**
 * Shared Context API Route
 *
 * GET /api/conversations/context?user_id=xxx
 *   - Get shared context across all agents
 *
 * PUT /api/conversations/context
 *   - Update shared context
 *
 * Shared context includes:
 * - Current workflow info
 * - Recent documents
 * - Insights from other agents
 */

import { NextRequest, NextResponse } from 'next/server';
import { SharedContext } from '@/types/conversation';

// Backend URL
const BACKEND_URL = process.env.AGENTCORE_URL || 'http://localhost:8081';

// Import shared memory store from lib
import { memoryStore } from '@/lib/conversation-store';

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
    const response = await fetch(
      `${BACKEND_URL}/conversations/context?user_id=${userId}`,
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(3000),
      }
    );

    if (response.ok) {
      const data = await response.json();
      return NextResponse.json(data);
    }
  } catch {
    // Backend unavailable
  }

  // Return from in-memory store
  const userStore = memoryStore.get(userId);

  return NextResponse.json({
    context: userStore?.sharedContext || {},
    userId,
  });
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { userId, context } = body;

    if (!userId) {
      return NextResponse.json(
        { error: 'Missing required field: userId' },
        { status: 400 }
      );
    }

    try {
      // Try backend first
      const response = await fetch(`${BACKEND_URL}/conversations/context`, {
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
      // Backend unavailable
    }

    // Update in-memory store
    const now = new Date().toISOString();
    let userStore = memoryStore.get(userId);

    if (!userStore) {
      userStore = {
        sessions: {
          frontend: null,
          backend: null,
          aws_admin: null,
          analyst: null,
        },
        sharedContext: {},
        lastUpdated: now,
      };
    }

    // Merge context (don't replace entirely)
    userStore.sharedContext = {
      ...userStore.sharedContext,
      ...context,
    };
    userStore.lastUpdated = now;

    memoryStore.set(userId, userStore);

    return NextResponse.json({
      success: true,
      context: userStore.sharedContext,
      lastUpdated: now,
    });

  } catch (error) {
    console.error('Context PUT error:', error);
    return NextResponse.json(
      { error: 'Failed to update context' },
      { status: 500 }
    );
  }
}
