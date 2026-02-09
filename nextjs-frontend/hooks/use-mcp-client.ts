'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  MCPTool,
  ToolResult,
  MCPClientReturn,
  AgentType,
  AgentMessage,
} from '@/types/mcp';
import {
  AGENT_CONFIGS,
  USE_MOCK_MCP,
  MOCK_TOOL_DEFINITIONS,
  generateMockResponse,
} from '@/lib/mcp-config';
import { useAgentSession } from './use-agent-session';
import { CURRENT_USER } from '@/lib/mock-data';

interface UseMCPClientOptions {
  agentId: AgentType;
  enablePersistence?: boolean; // Enable conversation persistence (default: true)
  enableSync?: boolean; // Enable backend sync for cross-device support (default: true)
  onMessage?: (message: AgentMessage) => void;
  onToolResult?: (result: ToolResult) => void;
  onError?: (error: string) => void;
}

interface UseMCPClientReturn extends MCPClientReturn {
  sendMessage: (content: string) => Promise<void>;
  messages: AgentMessage[];
  isLoading: boolean;
  clearMessages: () => void;
  // Persistence features
  sessionId: string;
  messageCount: number;
  exportAsMarkdown: () => string;
  exportAsJSON: () => string;
  contextPrompt: string | undefined;
  // Sync status
  isSynced: boolean;
  hasPendingChanges: boolean;
  forceSync: () => Promise<void>;
}

/**
 * Custom hook for interacting with MCP servers and AI agents.
 *
 * In mock mode (default), simulates MCP server responses.
 * When MCP servers are available, connects via Streamable HTTP transport.
 *
 * Features:
 * - Automatic conversation persistence via useAgentSession
 * - Cross-agent context sharing
 * - Export conversations as Markdown/JSON
 */
export function useMCPClient(options: UseMCPClientOptions): UseMCPClientReturn {
  const { agentId, enablePersistence = true, enableSync = true, onMessage, onToolResult, onError } = options;
  const config = AGENT_CONFIGS[agentId];

  // Use persistent session storage with sync
  const {
    session,
    isLoading: isSessionLoading,
    addMessage: persistMessage,
    addToolResult: persistToolResult,
    clearHistory,
    getContextPrompt,
    exportAsMarkdown,
    exportAsJSON,
    isSynced,
    hasPendingChanges,
    forceSync,
  } = useAgentSession({
    userId: CURRENT_USER.id,
    agentId,
    enableSync,
    onError,
  });

  const [isConnected, setIsConnected] = useState(USE_MOCK_MCP);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [error, setError] = useState<string | null>(null);

  const messageCountRef = useRef(0);

  // Load persisted messages on mount
  useEffect(() => {
    if (enablePersistence && session.messages.length > 0) {
      setMessages(session.messages);
      messageCountRef.current = session.messageCount;
    }
  }, [enablePersistence, session.messages, session.messageCount]);

  // Initialize tools - mock mode or fetch from MCP servers
  useEffect(() => {
    if (USE_MOCK_MCP) {
      const mockTools = MOCK_TOOL_DEFINITIONS[agentId].map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: {
          type: 'object',
          properties: {},
        },
      }));
      setTools(mockTools);
      setIsConnected(true);
    } else {
      // Fetch tools from real MCP servers
      const fetchToolsFromServers = async () => {
        setIsConnecting(true);
        const allTools: MCPTool[] = [];
        const mcpServers = config.mcpServers || [];

        for (const server of mcpServers) {
          try {
            // First initialize the connection
            await fetch(server.url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'initialize',
                params: {
                  protocolVersion: '2024-11-05',
                  capabilities: {},
                  clientInfo: { name: 'eagle-intake-client', version: '1.0.0' }
                },
                id: 1,
              }),
            });

            // Then fetch tools
            const response = await fetch(server.url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                jsonrpc: '2.0',
                method: 'tools/list',
                params: {},
                id: 2,
              }),
            });

            if (response.ok) {
              const data = await response.json();
              if (data.result?.tools) {
                const serverTools = data.result.tools.map((t: { name: string; description: string; inputSchema?: object }) => ({
                  name: t.name,
                  description: t.description,
                  inputSchema: t.inputSchema || { type: 'object', properties: {} },
                  server: server.name,
                }));
                allTools.push(...serverTools);
              }
            }
          } catch (err) {
            console.warn(`Failed to connect to MCP server ${server.name}:`, err);
          }
        }

        setTools(allTools);
        setIsConnected(allTools.length > 0);
        setIsConnecting(false);
      };

      fetchToolsFromServers();
    }
  }, [agentId, config.mcpServers]);

  const callTool = useCallback(
    async (name: string, args: Record<string, unknown>): Promise<ToolResult> => {
      if (USE_MOCK_MCP) {
        // Simulate tool call in mock mode
        await new Promise((resolve) => setTimeout(resolve, 500));

        const result: ToolResult = {
          name,
          args,
          result: { status: 'success', data: 'Mock result' },
          timestamp: new Date(),
        };

        onToolResult?.(result);
        return result;
      }

      // Real MCP tool call via HTTP to MCP servers
      const mcpServers = config.mcpServers;
      if (!mcpServers || mcpServers.length === 0) {
        throw new Error('No MCP servers configured for this agent');
      }

      // Try each MCP server until we find one that has the tool
      for (const server of mcpServers) {
        try {
          const response = await fetch(server.url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              jsonrpc: '2.0',
              method: 'tools/call',
              params: {
                name,
                arguments: args,
              },
              id: Date.now(),
            }),
          });

          if (!response.ok) {
            continue; // Try next server
          }

          const data = await response.json();

          if (data.error) {
            // Tool not found on this server, try next
            if (data.error.code === -32601 || data.error.message?.includes('Unknown tool')) {
              continue;
            }
            throw new Error(data.error.message);
          }

          // Extract result from MCP response
          const content = data.result?.content || [];
          const textContent = content.find((c: { type: string; text?: string }) => c.type === 'text');
          const resultData = textContent?.text || JSON.stringify(data.result);

          const result: ToolResult = {
            name,
            args,
            result: resultData,
            timestamp: new Date(),
          };

          onToolResult?.(result);
          return result;
        } catch (err) {
          console.warn(`MCP server ${server.name} failed:`, err);
          continue; // Try next server
        }
      }

      throw new Error(`Tool '${name}' not found on any configured MCP server`);
    },
    [config.mcpServers, onToolResult]
  );

  const disconnect = useCallback(() => {
    setIsConnected(false);
    setTools([]);
    setError(null);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    messageCountRef.current = 0;
    setError(null);

    // Also clear persisted history
    if (enablePersistence) {
      clearHistory();
    }
  }, [enablePersistence, clearHistory]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      setIsLoading(true);
      setError(null);

      // Add user message
      const userMessage: AgentMessage = {
        id: `msg-${++messageCountRef.current}`,
        role: 'user',
        content,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMessage]);
      onMessage?.(userMessage);

      // Persist user message
      if (enablePersistence) {
        persistMessage(userMessage);
      }

      try {
        if (USE_MOCK_MCP) {
          // Simulate typing delay
          await new Promise((resolve) => setTimeout(resolve, 800 + Math.random() * 700));

          // Determine if we should include a tool call (50% chance for variety)
          const includeToolCall = Math.random() > 0.5;
          const { content: responseContent, toolCalls } = generateMockResponse(
            agentId,
            content,
            includeToolCall
          );

          const assistantMessage: AgentMessage = {
            id: `msg-${++messageCountRef.current}`,
            role: 'assistant',
            content: responseContent,
            timestamp: new Date(),
            toolCalls: toolCalls?.map((tc) => ({
              name: tc.name,
              args: tc.args,
              result: tc.result,
              timestamp: new Date(),
            })),
          };

          setMessages((prev) => [...prev, assistantMessage]);
          onMessage?.(assistantMessage);

          // Persist assistant message
          if (enablePersistence) {
            persistMessage(assistantMessage);
          }

          // Notify about tool results and persist them
          if (toolCalls) {
            toolCalls.forEach((tc) => {
              const toolResult: ToolResult = {
                name: tc.name,
                args: tc.args,
                result: tc.result,
                timestamp: new Date(),
              };
              onToolResult?.(toolResult);

              if (enablePersistence) {
                persistToolResult(toolResult);
              }
            });
          }
        } else {
          // Real backend integration via /api/invoke
          const response = await fetch('/api/invoke', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              query: content,
              session_id: session.id,
              agent_id: agentId,
              system_prompt: config.systemPrompt,
            }),
          });

          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Backend error: ${response.status} - ${errorText}`);
          }

          const contentType = response.headers.get('content-type');
          let responseContent = '';
          const toolCalls: { name: string; args: Record<string, unknown>; result: unknown }[] = [];

          if (contentType?.includes('text/event-stream')) {
            // Handle SSE stream
            const reader = response.body?.getReader();
            if (!reader) throw new Error('No response body');

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split('\n');
              buffer = lines.pop() || '';

              for (const line of lines) {
                if (line.startsWith('data: ')) {
                  const data = line.slice(6).trim();
                  if (data) {
                    try {
                      const event = JSON.parse(data);
                      // Handle different event types
                      if (event.type === 'text' && event.content) {
                        responseContent += event.content;
                      } else if (event.type === 'tool_use' || event.type === 'tool_result') {
                        toolCalls.push({
                          name: event.tool_name || event.name || 'unknown',
                          args: event.args || event.input || {},
                          result: event.result || event.output || null,
                        });
                      }
                    } catch {
                      // Ignore parse errors for malformed events
                    }
                  }
                }
              }
            }
          } else {
            // Handle JSON response
            const data = await response.json();
            responseContent = data.content || data.response || JSON.stringify(data);
          }

          const assistantMessage: AgentMessage = {
            id: `msg-${++messageCountRef.current}`,
            role: 'assistant',
            content: responseContent || 'No response received.',
            timestamp: new Date(),
            toolCalls: toolCalls.length > 0 ? toolCalls.map((tc) => ({
              name: tc.name,
              args: tc.args,
              result: tc.result,
              timestamp: new Date(),
            })) : undefined,
          };

          setMessages((prev) => [...prev, assistantMessage]);
          onMessage?.(assistantMessage);

          // Persist assistant message
          if (enablePersistence) {
            persistMessage(assistantMessage);
          }

          // Notify about tool results
          if (toolCalls.length > 0) {
            toolCalls.forEach((tc) => {
              const toolResult: ToolResult = {
                name: tc.name,
                args: tc.args,
                result: tc.result,
                timestamp: new Date(),
              };
              onToolResult?.(toolResult);

              if (enablePersistence) {
                persistToolResult(toolResult);
              }
            });
          }
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Unknown error';
        setError(errorMessage);
        onError?.(errorMessage);

        // Add error message to chat
        const errorMsg: AgentMessage = {
          id: `msg-${++messageCountRef.current}`,
          role: 'assistant',
          content: `I encountered an error: ${errorMessage}. Please try again.`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
      }
    },
    [agentId, config, session.id, enablePersistence, persistMessage, persistToolResult, onMessage, onToolResult, onError]
  );

  return {
    isConnected,
    isConnecting,
    tools,
    callTool,
    disconnect,
    error,
    sendMessage,
    messages,
    isLoading: isLoading || isSessionLoading,
    clearMessages,
    // Persistence features
    sessionId: session.id,
    messageCount: session.messageCount,
    exportAsMarkdown,
    exportAsJSON,
    contextPrompt: getContextPrompt(),
    // Sync status
    isSynced,
    hasPendingChanges,
    forceSync,
  };
}

/**
 * Check MCP server health.
 */
export async function checkMCPHealth(serverUrl: string): Promise<boolean> {
  if (USE_MOCK_MCP) return true;

  try {
    const response = await fetch(serverUrl, {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    });
    return response.ok;
  } catch {
    return false;
  }
}
