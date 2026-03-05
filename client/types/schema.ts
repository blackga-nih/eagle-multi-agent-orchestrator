/**
 * EAGLE Frontend Schema — Active Types
 *
 * Only types with real consumers live here.
 * Archived (aspirational) types: ./schema-archive.ts
 */

// =============================================================================
// ENUMS & CONSTANTS
// =============================================================================

export type UserRole = 'co' | 'cor' | 'developer' | 'admin' | 'analyst';

export type WorkflowStatus =
  | 'draft'
  | 'in_progress'
  | 'pending_review'
  | 'approved'
  | 'rejected'
  | 'completed'
  | 'cancelled';

export type AcquisitionType = 'micro_purchase' | 'simplified' | 'negotiated';

export type UrgencyLevel = 'standard' | 'urgent' | 'critical';

export type DocumentStatus = 'not_started' | 'in_progress' | 'draft' | 'final' | 'approved';

/** All 10 document types supported by the backend create_document tool. */
export type DocumentType =
  | 'sow'
  | 'igce'
  | 'market_research'
  | 'acquisition_plan'
  | 'justification'
  | 'funding_doc'
  | 'eval_criteria'
  | 'security_checklist'
  | 'section_508'
  | 'cor_certification'
  | 'contract_type_justification';

export type ChecklistStepStatus = 'pending' | 'in_progress' | 'completed' | 'skipped';

export type SubmissionSource = 'user' | 'ai_generated' | 'imported';

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'modified';

export type CitationSourceType = 'document' | 'url' | 'far_clause' | 'policy' | 'market_data';

export type ConversationRole = 'user' | 'assistant' | 'system';

export type AgentRole = 'intake_agent' | 'document_agent' | 'review_agent' | 'orchestrator';

export type SkillType = 'document_gen' | 'data_extraction' | 'validation' | 'search';

export type FieldType = 'text' | 'select' | 'number' | 'date' | 'boolean' | 'textarea';

export type ChangeSource = 'user_edit' | 'ai_revision' | 'import' | 'merge' | 'rollback';

export type GroupRoleType = 'member' | 'lead' | 'admin';

export type FeedbackType = 'helpful' | 'inaccurate' | 'incomplete' | 'too_verbose';

// =============================================================================
// DOCUMENT TYPE MAPS (shared across components)
// =============================================================================

/** Human-readable labels for each document type. */
export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification & Approval',
  funding_doc: 'Funding Documentation',
  eval_criteria: 'Evaluation Criteria',
  security_checklist: 'Security Checklist',
  section_508: 'Section 508 Compliance',
  cor_certification: 'COR Certification',
  contract_type_justification: 'Contract Type Justification',
};

/** Emoji icons for each document type (used in activity panel, doc cards). */
export const DOCUMENT_TYPE_ICONS: Record<DocumentType, string> = {
  sow: '\u{1F4DD}',                      // memo
  igce: '\u{1F4B0}',                     // money bag
  market_research: '\u{1F50D}',          // magnifying glass
  acquisition_plan: '\u{1F4CB}',         // clipboard
  justification: '\u{2696}',            // scales
  funding_doc: '\u{1F4B5}',             // dollar
  eval_criteria: '\u{2705}',            // check mark
  security_checklist: '\u{1F512}',      // lock
  section_508: '\u{267F}',              // wheelchair
  cor_certification: '\u{1F3C5}',       // medal
  contract_type_justification: '\u{1F4C3}', // page with curl
};

// =============================================================================
// UI COLORS
// =============================================================================

export const SUBMISSION_SOURCE_COLORS: Record<SubmissionSource, string> = {
  user: '#3B82F6',
  ai_generated: '#8B5CF6',
  imported: '#6B7280',
};

export const REVIEW_STATUS_COLORS: Record<ReviewStatus, string> = {
  pending: '#F59E0B',
  approved: '#10B981',
  rejected: '#EF4444',
  modified: '#6366F1',
};

export const SUBMISSION_SOURCE_CLASSES: Record<SubmissionSource, string> = {
  user: 'bg-blue-500 text-white',
  ai_generated: 'bg-violet-500 text-white',
  imported: 'bg-gray-500 text-white',
};

export const REVIEW_STATUS_CLASSES: Record<ReviewStatus, string> = {
  pending: 'bg-amber-500 text-white',
  approved: 'bg-emerald-500 text-white',
  rejected: 'bg-red-500 text-white',
  modified: 'bg-indigo-500 text-white',
};

// =============================================================================
// USERS
// =============================================================================

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  division?: string;
  phone?: string;
  preferences: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  archived: boolean;
}

// =============================================================================
// WORKFLOWS
// =============================================================================

export interface Workflow {
  id: string;
  user_id: string;
  template_id?: string;
  title: string;
  description?: string;
  status: WorkflowStatus;
  acquisition_type?: AcquisitionType;
  estimated_value?: number;
  timeline_deadline?: string;
  urgency_level?: UrgencyLevel;
  current_step?: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  archived: boolean;
}

// =============================================================================
// DOCUMENTS
// =============================================================================

export interface Document {
  id: string;
  workflow_id: string;
  template_id?: string;
  document_type: DocumentType;
  title: string;
  status: DocumentStatus;
  content?: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentTemplate {
  id: string;
  document_type: DocumentType;
  name: string;
  description?: string;
  content_template: string;
  schema_definition: Record<string, unknown>;
  is_active: boolean;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// REQUIREMENTS & SUBMISSIONS
// =============================================================================

export interface RequirementSubmission {
  id: string;
  requirement_id: string;
  workflow_id: string;
  value: string;
  source: SubmissionSource;
  confidence_score?: number;
  reasoning?: string;
  citations: Citation[];
  submitted_by?: string;
  reviewed_by?: string;
  review_status?: ReviewStatus;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  id: string;
  submission_id: string;
  source_type: CitationSourceType;
  source_title: string;
  source_url?: string;
  excerpt?: string;
  relevance_score?: number;
  created_at: string;
}

// =============================================================================
// FEEDBACK
// =============================================================================

export interface AIFeedback {
  id: string;
  submission_id?: string;
  conversation_turn_id?: string;
  user_id: string;
  rating: 1 | 2 | 3 | 4 | 5;
  feedback_type?: FeedbackType;
  comment?: string;
  page?: string;
  session_id?: string;
  created_at: string;
}

// =============================================================================
// ACQUISITION DATA (canonical definition — used by chat, session, checklist)
// =============================================================================

export interface AcquisitionData {
  requirement?: string;
  estimatedValue?: string;
  estimatedCost?: string;
  timeline?: string;
  urgency?: string;
  funding?: string;
  equipmentType?: string;
  acquisitionType?: string;
}
