/**
 * Multi-Agent Stream Types
 *
 * These types define the protocol for streaming events from
 * multiple agents in the EAGLE system.
 */

// Import shared chat types for local use and re-export for backward compatibility.
import type { Message as _Message } from './chat';
export type { ChatMessage, Message, DocumentInfo } from './chat';

// Local alias so functions in this file can reference the type.
type Message = _Message;

export type StreamEventType =
  | 'text'
  | 'reasoning'
  | 'tool_use'
  | 'tool_result'
  | 'elicitation'
  | 'metadata'
  | 'complete'
  | 'error'
  | 'handoff'
  | 'user_input'
  | 'form_submit';

export interface ToolUse {
  name: string;
  input: Record<string, any>;
}

export interface ToolResult {
  name: string;
  result: any;
}

export interface ElicitationField {
  name: string;
  label: string;
  type: 'text' | 'select' | 'number' | 'date';
  options?: string[];
  required?: boolean;
}

export interface Elicitation {
  question: string;
  fields?: ElicitationField[];
}

export interface HandoffInfo {
  target_agent: string;
  reason: string;
}

/**
 * A single event in the multi-agent stream.
 * 
 * The `agent_id` field is critical for the frontend to:
 * - Apply the correct color scheme
 * - Group messages by agent
 * - Track agent participation in the conversation
 */
export interface StreamEvent {
  type: StreamEventType;
  agent_id: string;
  agent_name: string;
  timestamp: string;
  
  // Content fields (one will be populated based on type)
  content?: string;
  reasoning?: string;
  tool_use?: ToolUse;
  tool_result?: ToolResult;
  elicitation?: Elicitation;
  metadata?: Record<string, any>;
}

/**
 * Audit log entry for the stream.
 */
export interface AuditLogEntry extends StreamEvent {
  id: string;
}

/**
 * Parse a raw SSE event into a StreamEvent.
 */
export function parseStreamEvent(data: string): StreamEvent | null {
  try {
    return JSON.parse(data) as StreamEvent;
  } catch {
    return null;
  }
}

/**
 * Convert a StreamEvent to a Message for display.
 */
export function streamEventToMessage(event: StreamEvent, messageId: string): Message | null {
  if (event.type !== 'text') return null;
  
  return {
    id: messageId,
    role: 'assistant',
    content: event.content || '',
    timestamp: new Date(event.timestamp),
    reasoning: event.reasoning,
    agent_id: event.agent_id,
    agent_name: event.agent_name,
  };
}


