/**
 * Shared Chat Types
 *
 * Common types used across chat interfaces (simple and advanced)
 * and the document viewer.
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  reasoning?: string;
  agent_id?: string;
  agent_name?: string;
}

/** Backward-compatible alias so existing imports of `Message` keep working. */
export type Message = ChatMessage;

export interface DocumentInfo {
  document_id?: string;
  document_type: string;
  title: string;
  content?: string;
  status?: string;
  word_count?: number;
  generated_at?: string;
  s3_key?: string;
  s3_location?: string;
}
