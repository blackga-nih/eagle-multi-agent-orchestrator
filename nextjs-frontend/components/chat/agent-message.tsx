'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Brain, ChevronDown, ChevronUp, Search, FileText, Cpu } from 'lucide-react';
import { Message } from '@/types/stream';
import { getAgentColors, getAgentName, getAgentIcon, AgentColorScheme } from '@/lib/agent-colors';

interface AgentMessageProps {
  message: Message;
}

/**
 * Agent Message Component
 * 
 * Renders a single message from an agent with:
 * - Color-coded header based on agent_id
 * - Agent name and icon
 * - Expandable reasoning section
 * - Markdown-rendered content
 */
export default function AgentMessage({ message }: AgentMessageProps) {
  const [showReasoning, setShowReasoning] = useState(false);
  
  const agentId = message.agent_id || 'oa-intake';
  const colors = getAgentColors(agentId);
  const agentName = message.agent_name || getAgentName(agentId);
  const icon = getAgentIcon(agentId);
  
  // Select icon component based on agent type
  const IconComponent = agentId === 'knowledge-retrieval' 
    ? Search 
    : agentId === 'document-generator' 
      ? FileText 
      : agentId === 'supervisor' 
        ? Cpu 
        : null;

  return (
    <div className={`max-w-[85%] rounded-2xl shadow-sm bg-white border ${colors.border} p-5`}>
      {/* Agent Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-8 h-8 rounded-xl ${colors.icon} flex items-center justify-center text-white text-xs font-bold shadow-sm`}>
            {IconComponent ? <IconComponent className="w-4 h-4" /> : icon}
          </div>
          <div>
            <div className="text-xs font-bold text-gray-900 tracking-tight">{agentName}</div>
            <div className={`text-[9px] font-bold uppercase tracking-wider ${colors.text}`}>
              {agentId === 'supervisor' ? 'Orchestrator' : 'Specialist'}
            </div>
          </div>
        </div>
        
        {/* Agent Badge */}
        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${colors.badge}`}>
          {agentId}
        </span>
      </div>
      
      {/* Reasoning Toggle */}
      {message.reasoning && (
        <button
          onClick={() => setShowReasoning(!showReasoning)}
          className={`flex items-center gap-1.5 px-2 py-1 rounded-md hover:${colors.bg} text-[10px] font-bold text-gray-400 hover:${colors.text} transition-colors mb-3`}
        >
          <Brain className="w-3 h-3" />
          Reasoning {showReasoning ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      )}
      
      {/* Reasoning Panel */}
      {message.reasoning && showReasoning && (
        <div className={`mb-4 p-3 ${colors.bg} border ${colors.border} rounded-xl text-[11px] ${colors.text} leading-relaxed italic animate-in slide-in-from-top-2 duration-200`}>
          <div className={`font-bold text-[9px] uppercase tracking-widest mb-1 flex items-center gap-1 ${colors.text} opacity-70`}>
            <Brain className="w-2.5 h-2.5" /> Agent Intent Log
          </div>
          {message.reasoning}
        </div>
      )}
      
      {/* Message Content */}
      <div className="text-gray-700 leading-relaxed prose prose-sm max-w-none prose-headings:text-gray-900 prose-strong:text-gray-900 prose-table:border prose-table:border-gray-200 prose-th:bg-gray-50 prose-th:p-2 prose-td:p-2">
        <ReactMarkdown
          components={{
            p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
            ul: ({ children }) => <ul className="list-disc ml-5 mb-3 space-y-1">{children}</ul>,
            ol: ({ children }) => <ol className="list-decimal ml-5 mb-3 space-y-1">{children}</ol>,
            strong: ({ children }) => <strong className="font-bold text-gray-900">{children}</strong>,
            table: ({ children }) => (
              <div className="overflow-x-auto my-4">
                <table className="min-w-full border border-gray-200 rounded-lg">{children}</table>
              </div>
            ),
            th: ({ children }) => (
              <th className="bg-gray-50 px-3 py-2 text-left text-xs font-semibold text-gray-700 border-b border-gray-200">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="px-3 py-2 text-sm text-gray-600 border-b border-gray-100">
                {children}
              </td>
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
      
      {/* Timestamp */}
      <div className="text-[10px] mt-3 font-medium text-gray-400">
        {message.timestamp.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        })}
      </div>
    </div>
  );
}


