'use client';

import { useState, useMemo, useEffect, Suspense } from 'react';
import {
  Palette,
  Server,
  Cloud,
  BarChart3,
  Bot,
  Wifi,
  WifiOff,
  ShieldAlert,
  MessageSquare,
} from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import AgentChat from '@/components/agents/agent-chat';
import {
  AGENT_CONFIGS,
  USE_MOCK_MCP,
  getAgentsForRole,
  getDefaultAgentForRole,
} from '@/lib/mcp-config';
import { CURRENT_USER, getUserRoleLabel } from '@/lib/mock-data';
import { AgentType } from '@/types/mcp';
import { loadConversationStore } from '@/lib/conversation-store';

const AGENT_ICONS: Record<AgentType, React.ReactNode> = {
  frontend: <Palette className="w-4 h-4" />,
  backend: <Server className="w-4 h-4" />,
  aws_admin: <Cloud className="w-4 h-4" />,
  analyst: <BarChart3 className="w-4 h-4" />,
};

// Inner component that uses useSearchParams
function AgentsPageContent() {
  // Get available agents based on user role
  const availableAgents = useMemo(
    () => getAgentsForRole(CURRENT_USER.role),
    []
  );

  const defaultAgent = useMemo(
    () => getDefaultAgentForRole(CURRENT_USER.role),
    []
  );

  const [activeAgent, setActiveAgent] = useState<AgentType>(defaultAgent);
  const searchParams = useSearchParams();
  const requestedAgent = searchParams.get('agent') as AgentType | null;
  const [messageCounts, setMessageCounts] = useState<Record<AgentType, number>>({
    frontend: 0,
    backend: 0,
    aws_admin: 0,
    analyst: 0,
  });

  // Load message counts from storage
  useEffect(() => {
    const result = loadConversationStore(CURRENT_USER.id);
    if (result.success && result.data) {
      const counts: Record<AgentType, number> = {
        frontend: 0,
        backend: 0,
        aws_admin: 0,
        analyst: 0,
      };
      for (const agentId of Object.keys(result.data.sessions) as AgentType[]) {
        const session = result.data.sessions[agentId];
        if (session) {
          counts[agentId] = session.messageCount;
        }
      }
      setMessageCounts(counts);
    }
  }, [activeAgent]); // Refresh when switching agents

  useEffect(() => {
    if (requestedAgent && availableAgents.includes(requestedAgent)) {
      setActiveAgent(requestedAgent);
    }
  }, [requestedAgent, availableAgents]);

  const activeConfig = AGENT_CONFIGS[activeAgent];

  // If user has no access to any agents
  if (availableAgents.length === 0) {
    return (
      <div className="flex h-screen bg-gray-50">
        <SidebarNav />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center p-8">
            <div className="p-4 rounded-full bg-red-100 text-red-600 mx-auto w-fit mb-4">
              <ShieldAlert className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Access Restricted</h2>
            <p className="text-gray-500">
              Your role ({getUserRoleLabel(CURRENT_USER.role)}) does not have access to any agents.
            </p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={`p-3 rounded-xl ${activeConfig.bgColor}`}>
                <Bot className={`w-6 h-6 ${activeConfig.color}`} />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">Agent Workbench</h1>
                <p className="text-sm text-gray-500">
                  Specialized AI agents with MCP tool access
                </p>
              </div>
            </div>

            {/* Connection Status */}
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                USE_MOCK_MCP
                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                  : 'bg-green-50 text-green-700 border border-green-200'
              }`}
            >
              {USE_MOCK_MCP ? (
                <>
                  <WifiOff className="w-4 h-4" />
                  Mock Mode
                </>
              ) : (
                <>
                  <Wifi className="w-4 h-4" />
                  Connected
                </>
              )}
            </div>
          </div>

          {/* Agent Tabs - filtered by user role */}
          <div className="flex gap-2 mt-6">
            {availableAgents.map((agentId) => {
              const config = AGENT_CONFIGS[agentId];
              const isActive = activeAgent === agentId;
              const count = messageCounts[agentId];

              return (
                <button
                  key={agentId}
                  onClick={() => setActiveAgent(agentId)}
                  className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                    isActive
                      ? `${config.bgColor} ${config.color} border-2 ${config.borderColor} shadow-sm`
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200 border-2 border-transparent'
                  }`}
                >
                  {AGENT_ICONS[agentId]}
                  <span>{config.name}</span>
                  {count > 0 && (
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        isActive
                          ? 'bg-white/30'
                          : 'bg-gray-200 text-gray-500'
                      }`}
                    >
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Role indicator */}
          <p className="text-xs text-gray-400 mt-2">
            Showing {availableAgents.length} agent{availableAgents.length !== 1 ? 's' : ''} for{' '}
            <span className="font-medium">{getUserRoleLabel(CURRENT_USER.role)}</span> role
          </p>
        </div>

        {/* Chat Area */}
        <div className="flex-1 overflow-hidden">
          <AgentChat key={activeAgent} config={activeConfig} />
        </div>
      </main>
    </div>
  );
}

// Wrapper component with Suspense boundary for useSearchParams
export default function AgentsPage() {
  return (
    <AuthGuard>
    <Suspense fallback={
      <div className="flex h-screen bg-gray-50">
        <SidebarNav />
        <main className="flex-1 flex items-center justify-center">
          <div className="animate-pulse text-gray-400">Loading agents...</div>
        </main>
      </div>
    }>
      <AgentsPageContent />
    </Suspense>
    </AuthGuard>
  );
}
