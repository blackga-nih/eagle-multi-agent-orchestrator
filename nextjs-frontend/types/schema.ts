/**
 * EAGLE Intake MVP - Backend Schema Types
 *
 * TypeScript interfaces matching the PostgreSQL schema defined in
 * .claude/commands/experts/backend/expertise.yaml
 *
 * These types enable type-safe communication with the backend API.
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

export type DocumentType =
  | 'sow'
  | 'igce'
  | 'market_research'
  | 'acquisition_plan'
  | 'justification'
  | 'funding_doc';

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
// UI COLORS (from backend schema)
// =============================================================================

export const SUBMISSION_SOURCE_COLORS: Record<SubmissionSource, string> = {
  user: '#3B82F6',        // blue
  ai_generated: '#8B5CF6', // violet
  imported: '#6B7280',     // gray
};

export const REVIEW_STATUS_COLORS: Record<ReviewStatus, string> = {
  pending: '#F59E0B',   // amber
  approved: '#10B981',  // emerald
  rejected: '#EF4444',  // red
  modified: '#6366F1',  // indigo
};

// Tailwind class versions
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
// USERS, GROUPS & PROFILES
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

export interface UserGroup {
  id: string;
  name: string;
  description?: string;
  permissions: string[]; // ['approve_workflow', 'manage_templates']
  created_at: string;
}

export interface UserGroupMember {
  id: string;
  user_id: string;
  group_id: string;
  role_in_group: GroupRoleType;
  added_at: string;
}

export interface UserExpertise {
  id: string;
  user_id: string;
  total_improvements: number;
  last_improvement_at?: string;
  expertise_data: {
    acquisition_history?: string[];
    preferred_vendors?: string[];
    common_requirements?: string[];
  };
  behavioral_signals: {
    avg_session_duration?: number;
    peak_hours?: number[];
    device_preferences?: string[];
  };
  created_at: string;
  updated_at: string;
}

export interface UserMetrics {
  id: string;
  user_id: string;
  period_start: string;
  period_end: string;
  input_tokens: number;
  output_tokens: number;
  total_cost_usd: number;
  api_calls: number;
  workflows_completed: number;
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

export interface WorkflowTemplate {
  id: string;
  name: string;
  description?: string;
  acquisition_type?: AcquisitionType;
  checklist_config: ChecklistConfigItem[];
  document_requirements: DocumentRequirement[];
  created_by: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ChecklistConfigItem {
  step_id: string;
  step_name: string;
  required: boolean;
}

export interface DocumentRequirement {
  doc_type: DocumentType;
  template_id?: string;
}

export interface WorkflowChecklist {
  id: string;
  workflow_id: string;
  step_order: number;
  step_id: string;
  step_name: string;
  description?: string;
  status: ChecklistStepStatus;
  completed_by?: string;
  completed_at?: string;
  metadata?: Record<string, unknown>;
}

export interface WorkflowMetrics {
  id: string;
  workflow_id: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  conversation_turns: number;
  documents_generated: number;
  ai_suggestions_accepted: number;
  ai_suggestions_rejected: number;
  time_to_complete_hours?: number;
}

// =============================================================================
// DOCUMENTS & VERSIONS
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

export interface DocumentVersion {
  id: string;
  document_id: string;
  version: number;
  content: string;
  change_summary?: string;
  changed_by?: string;
  change_source: ChangeSource;
  diff_from_previous?: string;
  created_at: string;
}

export interface DocumentTemplate {
  id: string;
  document_type: DocumentType;
  name: string;
  description?: string;
  content_template: string; // markdown with {{placeholders}}
  schema_definition: Record<string, unknown>;
  is_active: boolean;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface TemplateVersion {
  id: string;
  template_id: string;
  version: number;
  content_template: string;
  schema_definition?: Record<string, unknown>;
  change_summary?: string;
  changed_by?: string;
  created_at: string;
}

export interface DocumentComment {
  id: string;
  document_id: string;
  user_id: string;
  content: string;
  selection_start?: number;
  selection_end?: number;
  resolved: boolean;
  resolved_by?: string;
  created_at: string;
}

// =============================================================================
// REQUIREMENTS & SUBMISSIONS
// =============================================================================

export interface Requirement {
  id: string;
  document_id: string;
  requirement_key: string;
  label: string;
  field_type: FieldType;
  required: boolean;
  options?: string[];
  validation_rules?: Record<string, unknown>;
  display_order: number;
}

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
// AGENT SYSTEM
// =============================================================================

export interface AgentSkill {
  id: string;
  skill_name: string;
  description?: string;
  skill_type: SkillType;
  config: {
    model?: string;
    temperature?: number;
    tools_enabled?: string[];
  };
  prompt_template?: string;
  is_active: boolean;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface AgentSkillVersion {
  id: string;
  skill_id: string;
  version: number;
  config?: Record<string, unknown>;
  prompt_template?: string;
  change_summary?: string;
  changed_by?: string;
  created_at: string;
}

export interface SystemPrompt {
  id: string;
  prompt_name: string;
  agent_role: AgentRole;
  content: string;
  version: number;
  is_active: boolean;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface SystemPromptVersion {
  id: string;
  prompt_id: string;
  version: number;
  content: string;
  change_summary?: string;
  changed_by?: string;
  performance_notes?: string;
  created_at: string;
}

// =============================================================================
// CONVERSATIONS & AUDIT
// =============================================================================

export interface Conversation {
  id: string;
  workflow_id: string;
  user_id: string;
  context?: string;
  status: 'active' | 'completed' | 'archived';
  created_at: string;
  updated_at: string;
}

export interface ConversationTurn {
  id: string;
  conversation_id: string;
  turn_index: number;
  role: ConversationRole;
  agent_id?: string;
  agent_name?: string;
  content: string;
  reasoning?: string;
  tool_calls: ToolCall[];
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number;
  timestamp: string;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  result?: unknown;
}

export interface AuditLog {
  id: string;
  trace_id?: string;
  span_id?: string;
  parent_span_id?: string;
  workflow_id?: string;
  user_id?: string;
  action: string;
  resource_type?: string;
  resource_id?: string;
  old_value?: Record<string, unknown>;
  new_value?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

export interface AIFeedback {
  id: string;
  submission_id?: string;
  conversation_turn_id?: string;
  user_id: string;
  rating: 1 | 2 | 3 | 4 | 5;
  feedback_type?: FeedbackType;
  comment?: string;
  created_at: string;
}

// =============================================================================
// FILE ATTACHMENTS
// =============================================================================

export interface FileAttachment {
  id: string;
  workflow_id: string;
  document_id?: string;
  filename: string;
  file_type?: string;
  file_size_bytes?: number;
  storage_path: string; // S3 key
  uploaded_by?: string;
  created_at: string;
}

// =============================================================================
// INFRASTRUCTURE
// =============================================================================

export interface DeploymentHistory {
  id: string;
  stack_name: string;
  environment: 'dev' | 'staging' | 'prod';
  version?: string;
  git_commit?: string;
  change_summary?: string;
  resources_added: string[];
  resources_modified: string[];
  resources_removed: string[];
  deployed_by?: string;
  deployment_status: 'pending' | 'in_progress' | 'success' | 'failed' | 'rolled_back';
  started_at: string;
  completed_at?: string;
  error_log?: string;
}

// =============================================================================
// API REQUEST/RESPONSE TYPES
// =============================================================================

export interface CreateWorkflowRequest {
  title: string;
  description?: string;
  template_id?: string;
  acquisition_type?: AcquisitionType;
  estimated_value?: number;
  timeline_deadline?: string;
  urgency_level?: UrgencyLevel;
}

export interface UpdateWorkflowRequest {
  title?: string;
  description?: string;
  status?: WorkflowStatus;
  acquisition_type?: AcquisitionType;
  estimated_value?: number;
  timeline_deadline?: string;
  urgency_level?: UrgencyLevel;
  current_step?: string;
  metadata?: Record<string, unknown>;
}

export interface CreateDocumentRequest {
  workflow_id: string;
  template_id?: string;
  document_type: DocumentType;
  title: string;
  content?: string;
}

export interface SubmitRequirementRequest {
  requirement_id: string;
  workflow_id: string;
  value: string;
  source?: SubmissionSource;
  reasoning?: string;
}

export interface SendMessageRequest {
  conversation_id: string;
  content: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface ApiError {
  error: string;
  message: string;
  details?: Record<string, unknown>;
}

// =============================================================================
// FRONTEND-SPECIFIC TYPES
// =============================================================================

/**
 * Extended workflow with related data for display
 */
export interface WorkflowWithDetails extends Workflow {
  user?: User;
  template?: WorkflowTemplate;
  documents?: Document[];
  checklist?: WorkflowChecklist[];
  metrics?: WorkflowMetrics;
}

/**
 * Simplified acquisition data for the intake form flow
 * Maps to the existing AcquisitionData interface in chat-interface.tsx
 */
export interface AcquisitionFormData {
  requirement?: string;
  estimated_value?: string;
  estimated_cost?: string;
  timeline?: string;
  urgency?: UrgencyLevel;
  funding?: string;
  equipment_type?: string;
  acquisition_type?: AcquisitionType;
}

/**
 * Map AcquisitionFormData to CreateWorkflowRequest
 */
export function acquisitionFormToWorkflow(data: AcquisitionFormData): CreateWorkflowRequest {
  return {
    title: data.requirement || 'New Acquisition',
    description: data.requirement,
    acquisition_type: data.acquisition_type,
    estimated_value: data.estimated_value ? parseFloat(data.estimated_value.replace(/[^0-9.]/g, '')) : undefined,
    timeline_deadline: data.timeline,
    urgency_level: data.urgency,
  };
}
