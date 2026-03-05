/**
 * EAGLE Schema Archive — Unused Types
 *
 * These interfaces were defined aspirationally but have no current consumers
 * in the frontend. Preserved here for reference if backend endpoints are
 * wired up in the future.
 */

import type {
  AcquisitionType,
  ChecklistStepStatus,
  DocumentType,
  UrgencyLevel,
  WorkflowStatus,
  ChangeSource,
  CitationSourceType,
  ConversationRole,
  FieldType,
  GroupRoleType,
  SubmissionSource,
  ReviewStatus,
  AgentRole,
  SkillType,
  FeedbackType,
} from './schema';

// =============================================================================
// USERS, GROUPS & PROFILES (unused)
// =============================================================================

export interface UserGroup {
  id: string;
  name: string;
  description?: string;
  permissions: string[];
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
// WORKFLOWS (unused)
// =============================================================================

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

export interface WorkflowWithDetails {
  user?: import('./schema').User;
  template?: WorkflowTemplate;
  documents?: import('./schema').Document[];
  checklist?: WorkflowChecklist[];
  metrics?: WorkflowMetrics;
}

// =============================================================================
// DOCUMENTS & VERSIONS (unused)
// =============================================================================

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
// REQUIREMENTS (unused — RequirementSubmission and Citation are used)
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

// =============================================================================
// AGENT SYSTEM (unused)
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
// CONVERSATIONS & AUDIT (unused)
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

export interface FileAttachment {
  id: string;
  workflow_id: string;
  document_id?: string;
  filename: string;
  file_type?: string;
  file_size_bytes?: number;
  storage_path: string;
  uploaded_by?: string;
  created_at: string;
}

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
// API REQUEST/RESPONSE (unused)
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
