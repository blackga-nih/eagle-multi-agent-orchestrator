/**
 * EAGLE Intake MVP - Type Exports
 *
 * Central export point for all TypeScript types used in the application.
 */

// Backend schema types
export * from './schema';

// Streaming types for multi-agent communication
export * from './stream';

// Admin store types (plugins, workspaces, skills, prompts, templates)
export * from './admin';

// Chat types (ChatMessage, DocumentInfo) — re-exported via stream.ts above
// export * from './chat';

// Conversation persistence types
export * from './conversation';
