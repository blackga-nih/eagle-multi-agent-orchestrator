/**
 * Multi-Agent Color Configuration
 *
 * Each agent in the EAGLE system has a unique color scheme for visual tracking
 * in the chat interface and audit logs.
 *
 * Colors align with backend schema definitions in:
 * .claude/commands/experts/backend/expertise.yaml
 */

import {
  SubmissionSource,
  ReviewStatus,
  SUBMISSION_SOURCE_COLORS,
  REVIEW_STATUS_COLORS,
  SUBMISSION_SOURCE_CLASSES,
  REVIEW_STATUS_CLASSES,
} from '@/types/schema';

// Re-export schema colors for convenience
export {
  SUBMISSION_SOURCE_COLORS,
  REVIEW_STATUS_COLORS,
  SUBMISSION_SOURCE_CLASSES,
  REVIEW_STATUS_CLASSES,
};

export interface AgentColorScheme {
  bg: string;
  text: string;
  border: string;
  badge: string;
  icon: string;
  gradient: string;
}

// Helper to get submission source styling
export function getSubmissionSourceClass(source: SubmissionSource): string {
  return SUBMISSION_SOURCE_CLASSES[source] || SUBMISSION_SOURCE_CLASSES.user;
}

// Helper to get review status styling
export function getReviewStatusClass(status: ReviewStatus): string {
  return REVIEW_STATUS_CLASSES[status] || REVIEW_STATUS_CLASSES.pending;
}

export const AGENT_COLORS: Record<string, AgentColorScheme> = {
  // Supervisor Agent - Gray (orchestration layer)
  'supervisor': {
    bg: 'bg-gray-50',
    text: 'text-gray-700',
    border: 'border-gray-200',
    badge: 'bg-gray-100 text-gray-600',
    icon: 'bg-gray-600',
    gradient: 'from-gray-500 to-gray-600',
  },
  
  // OA Intake Agent - Blue (primary interaction)
  'oa-intake': {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
    icon: 'bg-blue-600',
    gradient: 'from-blue-500 to-blue-600',
  },
  
  // Knowledge Retrieval Agent - Green (RAG/search)
  'knowledge-retrieval': {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
    badge: 'bg-green-100 text-green-700',
    icon: 'bg-green-600',
    gradient: 'from-green-500 to-green-600',
  },
  
  // Document Generator Agent - Purple (document creation)
  'document-generator': {
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    badge: 'bg-purple-100 text-purple-700',
    icon: 'bg-purple-600',
    gradient: 'from-purple-500 to-purple-600',
  },
  
  // EAGLE Root Agent - Blue (primary)
  'eagle': {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
    icon: 'bg-blue-600',
    gradient: 'from-blue-500 to-blue-600',
  },

  // Strands Specialist Agents
  'legal-counsel': {
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
    badge: 'bg-rose-100 text-rose-700',
    icon: 'bg-rose-600',
    gradient: 'from-rose-500 to-rose-600',
  },
  'market-intelligence': {
    bg: 'bg-teal-50',
    text: 'text-teal-700',
    border: 'border-teal-200',
    badge: 'bg-teal-100 text-teal-700',
    icon: 'bg-teal-600',
    gradient: 'from-teal-500 to-teal-600',
  },
  'tech-translator': {
    bg: 'bg-cyan-50',
    text: 'text-cyan-700',
    border: 'border-cyan-200',
    badge: 'bg-cyan-100 text-cyan-700',
    icon: 'bg-cyan-600',
    gradient: 'from-cyan-500 to-cyan-600',
  },
  'policy-supervisor': {
    bg: 'bg-indigo-50',
    text: 'text-indigo-700',
    border: 'border-indigo-200',
    badge: 'bg-indigo-100 text-indigo-700',
    icon: 'bg-indigo-600',
    gradient: 'from-indigo-500 to-indigo-600',
  },
  'policy-librarian': {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    badge: 'bg-emerald-100 text-emerald-700',
    icon: 'bg-emerald-600',
    gradient: 'from-emerald-500 to-emerald-600',
  },
  'policy-analyst': {
    bg: 'bg-violet-50',
    text: 'text-violet-700',
    border: 'border-violet-200',
    badge: 'bg-violet-100 text-violet-700',
    icon: 'bg-violet-600',
    gradient: 'from-violet-500 to-violet-600',
  },
  'public-interest': {
    bg: 'bg-orange-50',
    text: 'text-orange-700',
    border: 'border-orange-200',
    badge: 'bg-orange-100 text-orange-700',
    icon: 'bg-orange-600',
    gradient: 'from-orange-500 to-orange-600',
  },

  // Default/Unknown - Amber (fallback)
  'default': {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    badge: 'bg-amber-100 text-amber-700',
    icon: 'bg-amber-600',
    gradient: 'from-amber-500 to-amber-600',
  },
};

export const AGENT_NAMES: Record<string, string> = {
  'supervisor': 'Supervisor',
  'oa-intake': 'OA Intake Agent',
  'knowledge-retrieval': 'Knowledge Retrieval',
  'document-generator': 'Document Generator',
  'eagle': 'EAGLE',
  'legal-counsel': 'Legal Counsel',
  'market-intelligence': 'Market Intelligence',
  'tech-translator': 'Tech Translator',
  'policy-supervisor': 'Policy Supervisor',
  'policy-librarian': 'Policy Librarian',
  'policy-analyst': 'Policy Analyst',
  'public-interest': 'Public Interest',
};

export const AGENT_ICONS: Record<string, string> = {
  'supervisor': 'S',
  'oa-intake': 'E',  // EAGLE
  'knowledge-retrieval': 'K',
  'document-generator': 'D',
  'eagle': 'E',
  'legal-counsel': 'L',
  'market-intelligence': 'M',
  'tech-translator': 'T',
  'policy-supervisor': 'P',
  'policy-librarian': 'B',
  'policy-analyst': 'A',
  'public-interest': 'I',
};

export function getAgentColors(agentId: string): AgentColorScheme {
  return AGENT_COLORS[agentId] || AGENT_COLORS['default'];
}

export function getAgentName(agentId: string): string {
  return AGENT_NAMES[agentId] || agentId;
}

export function getAgentIcon(agentId: string): string {
  return AGENT_ICONS[agentId] || agentId.charAt(0).toUpperCase();
}


