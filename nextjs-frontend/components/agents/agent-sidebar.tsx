'use client';

import { CheckCircle2, XCircle, Loader2, Terminal, Server, Info } from 'lucide-react';
import { AgentConfig, MCPTool, ToolResult } from '@/types/mcp';

interface AgentSidebarProps {
  config: AgentConfig;
  isConnected: boolean;
  isMockMode?: boolean;
  tools: MCPTool[];
  recentToolResults: ToolResult[];
}

export default function AgentSidebar({
  config,
  isConnected,
  isMockMode = true,
  tools,
  recentToolResults,
}: AgentSidebarProps) {
  return (
    <div className="space-y-6">
      {/* Agent Info */}
      <div className={`p-4 rounded-xl ${config.bgColor} border ${config.borderColor}`}>
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg bg-white ${config.color}`}>
            <Info className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{config.name}</h3>
            <p className="text-sm text-gray-600">{config.description}</p>
          </div>
        </div>
      </div>

      {/* Connection Status */}
      <div>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          MCP Servers
        </h4>
        <div className="space-y-2">
          {config.mcpServers.map((server) => (
            <div
              key={server.name}
              className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100"
            >
              <Server className="w-4 h-4 text-gray-400" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-700">{server.name}</p>
                <p className="text-[10px] text-gray-400 truncate">{server.url}</p>
              </div>
              {isConnected ? (
                <div className={`flex items-center gap-1 ${isMockMode ? 'text-amber-600' : 'text-green-600'}`}>
                  <CheckCircle2 className="w-4 h-4" />
                  <span className="text-[10px] font-medium">{isMockMode ? 'Mock' : 'Live'}</span>
                </div>
              ) : (
                <div className="flex items-center gap-1 text-gray-400">
                  <XCircle className="w-4 h-4" />
                  <span className="text-[10px] font-medium">Offline</span>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Available Tools */}
      <div>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Available Tools ({tools.length})
        </h4>
        <div className="space-y-1 max-h-48 overflow-y-auto">
          {tools.map((tool) => (
            <div
              key={tool.name}
              className="flex items-start gap-2 p-2 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <Terminal className="w-4 h-4 text-gray-400 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-gray-700">{tool.name}</p>
                <p className="text-[10px] text-gray-400 line-clamp-1">{tool.description}</p>
              </div>
            </div>
          ))}
          {tools.length === 0 && (
            <p className="text-sm text-gray-400 italic p-2">No tools available</p>
          )}
        </div>
      </div>

      {/* Recent Tool Calls */}
      {recentToolResults.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Recent Tool Calls
          </h4>
          <div className="space-y-2 max-h-40 overflow-y-auto">
            {recentToolResults.slice(-5).reverse().map((result, idx) => (
              <div
                key={`${result.name}-${idx}`}
                className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg"
              >
                <Terminal className="w-3 h-3 text-gray-400" />
                <span className="text-xs font-mono text-gray-600">{result.name}</span>
                {result.error ? (
                  <XCircle className="w-3 h-3 text-red-400 ml-auto" />
                ) : (
                  <CheckCircle2 className="w-3 h-3 text-green-400 ml-auto" />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* System Prompt Preview */}
      <div>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Expertise Context
        </h4>
        <div className="p-3 bg-gray-50 rounded-lg border border-gray-100">
          <p className="text-xs text-gray-600 line-clamp-6">{config.systemPrompt}</p>
        </div>
      </div>
    </div>
  );
}
