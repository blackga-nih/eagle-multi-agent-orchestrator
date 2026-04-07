'use client';

import { type ReactNode, createElement } from 'react';
import { type ClientToolResult } from '@/lib/client-tools';
import RawResultPanel from './raw-result-panel';
import ReasoningResultPanel from './reasoning-result-panel';
import MarkdownResultPanel from './markdown-result-panel';
import SearchResultPanel from './search-result-panel';
import S3ResultPanel from './s3-result-panel';
import KnowledgeSearchPanel from './knowledge-search-panel';
import IntakeWorkflowPanel from './intake-workflow-panel';
import PackageStatusPanel from './package-status-panel';
import ComplianceResultPanel from './compliance-result-panel';
import KnowledgeFetchPanel from './knowledge-fetch-panel';
import WebSearchPanel from './web-search-panel';
import ResearchResultPanel from './research-result-panel';
import MarkdownFallbackPanel from './markdown-fallback-panel';

export { default as ToolTimingSummary } from './tool-timing-summary';

/** Subagent tools whose results are markdown reports. */
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

/** Extract a displayable text string from a ClientToolResult. */
function extractResultText(result: ClientToolResult | null | undefined): string | null {
  if (!result || result.result === null || result.result === undefined) return null;
  if (typeof result.result === 'string') return result.result;

  // Check for subagent markdown report
  const obj = result.result as Record<string, unknown>;
  if (obj.report && typeof obj.report === 'string') return obj.report;

  return JSON.stringify(result.result, null, 2);
}

/**
 * Resolves the correct result panel for a given tool.
 *
 * Returns a React element (or null) to render in the expanded section
 * of a tool-use card. Handles error display, subagent markdown, and
 * tool-specific structured panels.
 */
export function resolveResultPanel(
  toolName: string,
  input: Record<string, unknown>,
  result: ClientToolResult | null | undefined,
  errorText: string | null | undefined,
): ReactNode {
  // Errors always use the raw panel in error mode
  if (errorText) {
    return createElement(RawResultPanel, { text: null, errorText });
  }

  const resultText = extractResultText(result);
  if (!resultText) return null;

  // Subagent tools → markdown
  if (SUBAGENT_TOOLS.has(toolName)) {
    return createElement(MarkdownResultPanel, { text: resultText });
  }

  // Tool-specific panels
  switch (toolName) {
    case 'think':
      return createElement(ReasoningResultPanel, { text: resultText, input });

    case 's3_document_ops':
      return createElement(S3ResultPanel, { text: resultText, input });

    case 'search_far':
      return createElement(SearchResultPanel, { text: resultText });

    case 'knowledge_search':
      return createElement(KnowledgeSearchPanel, { text: resultText });

    case 'intake_workflow':
      return createElement(IntakeWorkflowPanel, { text: resultText });

    case 'manage_package':
      return createElement(PackageStatusPanel, { text: resultText });

    case 'query_compliance_matrix':
      return createElement(ComplianceResultPanel, { text: resultText });

    case 'knowledge_fetch':
      return createElement(KnowledgeFetchPanel, { text: resultText });

    case 'web_search':
      return createElement(WebSearchPanel, { text: resultText });

    case 'research':
      return createElement(ResearchResultPanel, { text: resultText });

    default:
      return createElement(MarkdownFallbackPanel, { text: resultText, toolName });
  }
}
