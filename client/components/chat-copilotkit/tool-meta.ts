/**
 * Shared tool metadata — icon + human-friendly label for each tool/subagent.
 * Used by both inline tool cards (chat-v2) and tool-use-display (chat-v1).
 */

export interface ToolMeta {
  icon: string;
  label: string;
}

export const TOOL_META: Record<string, ToolMeta> = {
  // Specialist subagents
  oa_intake: { icon: '\u{1F4CB}', label: 'Intake Assessment' },
  legal_counsel: { icon: '\u{2696}\uFE0F', label: 'Legal Analysis' },
  market_intelligence: { icon: '\u{1F4CA}', label: 'Market Research' },
  tech_translator: { icon: '\u{1F527}', label: 'Technical Review' },
  tech_review: { icon: '\u{1F527}', label: 'Technical Review' },
  public_interest: { icon: '\u{1F3DB}\uFE0F', label: 'Public Interest Review' },
  document_generator: { icon: '\u{1F4C4}', label: 'Generating Document' },
  compliance: { icon: '\u2705', label: 'Compliance Check' },
  policy_analyst: { icon: '\u{1F4DC}', label: 'Policy Analysis' },
  policy_librarian: { icon: '\u{1F4DA}', label: 'Policy Lookup' },
  policy_supervisor: { icon: '\u{1F464}', label: 'Policy Review' },
  ingest_document: { icon: '\u{1F4E5}', label: 'Document Ingestion' },
  knowledge_retrieval: { icon: '\u{1F50D}', label: 'Knowledge Search' },
  // Service tools
  s3_document_ops: { icon: '\u{1F4C1}', label: 'Document Storage' },
  dynamodb_intake: { icon: '\u{1F5C3}\uFE0F', label: 'Intake Records' },
  create_document: { icon: '\u{1F4DD}', label: 'Creating Document' },
  get_intake_status: { icon: '\u{1F4CA}', label: 'Intake Status' },
  intake_workflow: { icon: '\u{1F504}', label: 'Intake Workflow' },
  search_far: { icon: '\u{1F4D6}', label: 'Searching FAR/DFARS' },
  query_compliance_matrix: { icon: '\u2705', label: 'Compliance Matrix' },
  // Client-side tools
  think: { icon: '\u{1F4AD}', label: 'Reasoning' },
  code: { icon: '\u{1F4BB}', label: 'Running Code' },
  editor: { icon: '\u270F\uFE0F', label: 'Editing' },
};

/** Subagent tool names — results are markdown text from specialist agents. */
export const SUBAGENT_TOOLS = new Set([
  'oa_intake',
  'legal_counsel',
  'market_intelligence',
  'tech_translator',
  'tech_review',
  'public_interest',
  'compliance',
  'policy_analyst',
  'policy_librarian',
  'policy_supervisor',
  'document_generator',
  'ingest_document',
  'knowledge_retrieval',
]);

export function getToolMeta(toolName: string): ToolMeta {
  return TOOL_META[toolName] ?? { icon: '\u2699\uFE0F', label: toolName.replace(/_/g, ' ') };
}
