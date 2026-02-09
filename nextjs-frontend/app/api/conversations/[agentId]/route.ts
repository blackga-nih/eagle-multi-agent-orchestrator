/**
 * Agent Session API Route
 *
 * GET /api/conversations/:agentId?user_id=xxx
 *   - Get session for specific agent
 *
 * PUT /api/conversations/:agentId
 *   - Update/sync session for specific agent
 *
 * DELETE /api/conversations/:agentId?user_id=xxx
 *   - Clear session for specific agent
 */

import { NextRequest, NextResponse } from 'next/server';
import { AgentSession, createEmptySession } from '@/types/conversation';
import { AgentType } from '@/types/mcp';

// Backend URL
const BACKEND_URL = process.env.AGENTCORE_URL || 'http://localhost:8081';

// Import shared memory store from lib
// In production, this would be replaced by database queries
import { memoryStore } from '@/lib/conversation-store';

const VALID_AGENT_IDS: AgentType[] = ['frontend', 'backend', 'aws_admin', 'analyst'];

interface RouteParams {
  params: Promise<{ agentId: string }>;
}

export async function GET(request: NextRequest, { params }: RouteParams) {
  const { agentId } = await params;
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get('user_id');

  if (!userId) {
    return NextResponse.json(
      { error: 'Missing required parameter: user_id' },
      { status: 400 }
    );
  }

  if (!VALID_AGENT_IDS.includes(agentId as AgentType)) {
    return NextResponse.json(
      { error: `Invalid agent ID. Must be one of: ${VALID_AGENT_IDS.join(', ')}` },
      { status: 400 }
    );
  }

  try {
    // Try backend first
    const response = await fetch(
      `${BACKEND_URL}/conversations/${agentId}?user_id=${userId}`,
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
  const session = userStore?.sessions[agentId as AgentType] || null;

  return NextResponse.json({
    session,
    agentId,
    userId,
  });
}

export async function PUT(request: NextRequest, { params }: RouteParams) {
  const { agentId } = await params;

  try {
    const body = await request.json();
    const { userId, session } = body;

    if (!userId) {
      return NextResponse.json(
        { error: 'Missing required field: userId' },
        { status: 400 }
      );
    }

    if (!VALID_AGENT_IDS.includes(agentId as AgentType)) {
      return NextResponse.json(
        { error: `Invalid agent ID. Must be one of: ${VALID_AGENT_IDS.join(', ')}` },
        { status: 400 }
      );
    }

    try {
      // Try backend first
      const response = await fetch(`${BACKEND_URL}/conversations/${agentId}`, {
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

    // Update the specific agent session
    userStore.sessions[agentId as AgentType] = session
      ? {
          ...session,
          updatedAt: now,
        }
      : null;
    userStore.lastUpdated = now;

    memoryStore.set(userId, userStore);

    // Log for audit (in production, this would go to audit table)
    console.log(`[AUDIT] Session updated: user=${userId}, agent=${agentId}, messages=${session?.messageCount || 0}`);

    return NextResponse.json({
      success: true,
      agentId,
      lastUpdated: now,
    });

  } catch (error) {
    console.error('Session PUT error:', error);
    return NextResponse.json(
      { error: 'Failed to update session' },
      { status: 500 }
    );
  }
}

export async function DELETE(request: NextRequest, { params }: RouteParams) {
  const { agentId } = await params;
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get('user_id');

  if (!userId) {
    return NextResponse.json(
      { error: 'Missing required parameter: user_id' },
      { status: 400 }
    );
  }

  if (!VALID_AGENT_IDS.includes(agentId as AgentType)) {
    return NextResponse.json(
      { error: `Invalid agent ID. Must be one of: ${VALID_AGENT_IDS.join(', ')}` },
      { status: 400 }
    );
  }

  try {
    // Try backend first
    const response = await fetch(
      `${BACKEND_URL}/conversations/${agentId}?user_id=${userId}`,
      {
        method: 'DELETE',
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

  // Clear from in-memory store
  const userStore = memoryStore.get(userId);
  if (userStore) {
    userStore.sessions[agentId as AgentType] = null;
    userStore.lastUpdated = new Date().toISOString();
    memoryStore.set(userId, userStore);
  }

  // Log for audit
  console.log(`[AUDIT] Session cleared: user=${userId}, agent=${agentId}`);

  return NextResponse.json({
    success: true,
    agentId,
    cleared: true,
  });
}
