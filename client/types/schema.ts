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
  | 'cancelled'
  | 'review';

export type AcquisitionType = 'micro_purchase' | 'simplified' | 'negotiated';

export type UrgencyLevel = 'standard' | 'urgent' | 'critical';

export type DocumentStatus = 'not_started' | 'in_progress' | 'draft' | 'final' | 'approved';

/**
 * All document types supported by the backend create_document tool.
 * Aligned with canonical schema in server/app/ai_document_schema.py (Phase 5)
 */
export type DocumentType =
  // Core document types (create_document supported)
  | 'sow'
  | 'igce'
  | 'market_research'
  | 'acquisition_plan'
  | 'justification'
  | 'eval_criteria'
  | 'security_checklist'
  | 'section_508'
  | 'cor_certification'
  | 'contract_type_justification'
  | 'son_products'
  | 'son_services'
  | 'purchase_request'
  | 'price_reasonableness'
  | 'required_sources'
  // Template/form types
  | 'subk_plan'
  | 'subk_review'
  | 'buy_american'
  | 'conference_request'
  | 'conference_waiver'
  | 'bpa_call_order'
  // Frontend-only types (kept for compatibility, pending backend support)
  | 'funding_doc'
  | 'd_f'
  | 'qasp'
  | 'source_selection_plan'
  | 'sb_review'
  | 'human_subjects';

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

export type FeedbackArea =
  | 'network'
  | 'documents'
  | 'knowledge_base'
  | 'auth'
  | 'streaming'
  | 'ui'
  | 'performance'
  | 'tools';

// =============================================================================
// DOCUMENT TYPE MAPS (shared across components)
// =============================================================================

/** Human-readable labels for each document type. */
export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  // Core document types
  sow: 'Statement of Work',
  igce: 'Cost Estimate (IGCE)',
  market_research: 'Market Research',
  acquisition_plan: 'Acquisition Plan',
  justification: 'Justification & Approval',
  eval_criteria: 'Evaluation Criteria',
  security_checklist: 'Security Checklist',
  section_508: 'Section 508 Compliance',
  cor_certification: 'COR Certification',
  contract_type_justification: 'Contract Type Justification',
  son_products: 'Statement of Need — Products',
  son_services: 'Statement of Need — Services',
  purchase_request: 'Purchase Request',
  price_reasonableness: 'Price Reasonableness Determination',
  required_sources: 'Required Sources Checklist',
  // Template/form types
  subk_plan: 'Subcontracting Plan',
  subk_review: 'Subcontracting Review',
  buy_american: 'Buy American Determination',
  conference_request: 'Conference Request',
  conference_waiver: 'Conference Waiver',
  bpa_call_order: 'BPA Call Order',
  // Frontend-only types
  funding_doc: 'Funding Documentation',
  d_f: 'Determination & Findings (D&F)',
  qasp: 'Quality Assurance Surveillance Plan',
  source_selection_plan: 'Source Selection Plan',
  sb_review: 'Small Business Review (HHS-653)',
  human_subjects: 'Human Subjects Provisions',
};

/** Emoji icons for each document type (used in activity panel, doc cards). */
export const DOCUMENT_TYPE_ICONS: Record<DocumentType, string> = {
  // Core document types
  sow: '\u{1F4DD}', // memo
  igce: '\u{1F4B0}', // money bag
  market_research: '\u{1F50D}', // magnifying glass
  acquisition_plan: '\u{1F4CB}', // clipboard
  justification: '\u{2696}', // scales
  eval_criteria: '\u{2705}', // check mark
  security_checklist: '\u{1F512}', // lock
  section_508: '\u{267F}', // wheelchair
  cor_certification: '\u{1F3C5}', // medal
  contract_type_justification: '\u{1F4C3}', // page with curl
  son_products: '\u{1F4E6}', // package
  son_services: '\u{1F6E0}', // tools
  purchase_request: '\u{1F4E5}', // inbox tray
  price_reasonableness: '\u{1F4B2}', // dollar sign
  required_sources: '\u{2611}', // checkbox
  // Template/form types
  subk_plan: '\u{1F91D}', // handshake
  subk_review: '\u{1F50E}', // magnifying glass right
  buy_american: '\u{1F1FA}\u{1F1F8}', // US flag
  conference_request: '\u{1F4C5}', // calendar
  conference_waiver: '\u{1F4DD}', // memo
  bpa_call_order: '\u{1F4DE}', // telephone
  // Frontend-only types
  funding_doc: '\u{1F4B5}', // dollar
  d_f: '\u{1F4DC}', // scroll
  qasp: '\u{1F50E}', // magnifying glass right
  source_selection_plan: '\u{1F3AF}', // target
  sb_review: '\u{1F3E2}', // office building
  human_subjects: '\u{1F9EC}', // dna
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
