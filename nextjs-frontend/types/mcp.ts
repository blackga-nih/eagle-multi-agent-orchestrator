/**
 * MCP (Model Context Protocol) Types
 *
 * Types for connecting to MCP servers from the browser
 * and interacting with specialized agents.
 */

export interface MCPTool {
  name: string;
  description: string;
  inputSchema?: {
    type: string;
    properties?: Record<string, {
      type: string;
      description?: string;
      enum?: string[];
    }>;
    required?: string[];
  };
}

export interface ToolResult {
  name: string;
  args: Record<string, unknown>;
  result: unknown;
  error?: string;
  timestamp: Date;
}

export interface MCPServer {
  name: string;
  url: string;
  description?: string;
}

export type AgentType = 'frontend' | 'backend' | 'aws_admin' | 'analyst';

export interface AgentConfig {
  id: AgentType;
  name: string;
  description: string;
  systemPrompt: string;
  mcpServers: MCPServer[];
  icon: string;
  color: string;
  bgColor: string;
  borderColor: string;
  mockTools: string[];
}

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ToolResult[];
  isStreaming?: boolean;
}

export interface AgentChatState {
  messages: AgentMessage[];
  isConnected: boolean;
  isLoading: boolean;
  availableTools: MCPTool[];
  error: string | null;
}

export interface MCPClientOptions {
  serverUrl: string;
  onToolResult?: (result: ToolResult) => void;
  onError?: (error: string) => void;
}

export interface MCPClientReturn {
  isConnected: boolean;
  isConnecting: boolean;
  tools: MCPTool[];
  callTool: (name: string, args: Record<string, unknown>) => Promise<ToolResult>;
  disconnect: () => void;
  error: string | null;
}
