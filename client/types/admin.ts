/**
 * Admin types matching real DynamoDB item shapes from backend stores.
 *
 * These types represent the actual API responses from:
 * - plugin_store.py (PLUGIN# entities)
 * - workspace_store.py (WORKSPACE# entities)
 * - skill_store.py (SKILL# entities)
 * - prompt_store.py (PROMPT# entities)
 * - template_store.py (TEMPLATE# entities)
 */

// ---------------------------------------------------------------------------
// Plugin entities (PLUGIN# items — agents, skills, templates, refdata, tools)
// ---------------------------------------------------------------------------

export interface PluginEntity {
  entity_type: string;
  name: string;
  content: string;
  content_type: string;
  metadata: Record<string, unknown>;
  version: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Workspaces (WORKSPACE# items)
// ---------------------------------------------------------------------------

export interface Workspace {
  workspace_id: string;
  tenant_id: string;
  user_id: string;
  name: string;
  description: string;
  is_active: boolean;
  is_default: boolean;
  visibility: string;
  override_count: number;
  created_at: string;
  updated_at: string;
  base_workspace_id?: string;
}

// ---------------------------------------------------------------------------
// Workspace overrides (returned by /api/workspace/{id}/overrides)
// ---------------------------------------------------------------------------

export interface WorkspaceOverride {
  entity_type: string;
  name: string;
  content: string;
  is_append: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Prompt overrides (PROMPT# items)
// ---------------------------------------------------------------------------

export interface PromptOverride {
  tenant_id: string;
  agent_name: string;
  prompt_body: string;
  is_append: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Custom skills (SKILL# items with lifecycle)
// ---------------------------------------------------------------------------

export type SkillStatus = 'draft' | 'review' | 'active' | 'disabled';

export interface CustomSkill {
  skill_id: string;
  tenant_id: string;
  owner_user_id: string;
  name: string;
  display_name: string;
  description: string;
  prompt_body: string;
  triggers: string[];
  tools: string[];
  model?: string;
  status: SkillStatus;
  visibility: string;
  version: number;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

// ---------------------------------------------------------------------------
// Template overrides (TEMPLATE# items)
// ---------------------------------------------------------------------------

export interface TemplateEntity {
  doc_type: string;
  display_name?: string;
  template_body: string;
  tenant_id: string;
  user_id: string;
  version: number;
  source: string;
  created_at: string;
  updated_at: string;
  far_clause_refs?: FarClauseRef[];
}

// ---------------------------------------------------------------------------
// Request body types
// ---------------------------------------------------------------------------

export interface CreateWorkspaceBody {
  name: string;
  description?: string;
  visibility?: string;
  is_active?: boolean;
}

export interface SetPromptBody {
  prompt_body: string;
  is_append?: boolean;
}

export interface CreateSkillBody {
  name: string;
  display_name: string;
  description: string;
  prompt_body: string;
  triggers?: string[];
  tools?: string[];
  model?: string;
  visibility?: string;
}

export interface SetOverrideBody {
  content: string;
  is_append?: boolean;
}

export interface CreateTemplateBody {
  display_name?: string;
  template_body: string;
}

// ---------------------------------------------------------------------------
// S3 Template Library
// ---------------------------------------------------------------------------

export interface TemplateCategory {
  phase: string;
  use_case: string;
  group: string;
}

export interface FarClauseRef {
  clause_number: string;
  clause_title: string;
  section?: string | null;
  applicability: 'required' | 'conditional' | 'recommended';
  condition?: string | null;
  note?: string | null;
}

export interface S3Template {
  s3_key: string;
  filename: string;
  file_type: string;
  size_bytes: number;
  last_modified: string | null;
  doc_type: string | null;
  category: TemplateCategory | null;
  display_name: string;
  registered: boolean;
  far_clause_refs?: FarClauseRef[];
  clause_count?: number;
  far_parts_covered?: string[];
}

export interface S3TemplateListResponse {
  templates: S3Template[];
  total: number;
  phases: Record<string, string>;
  phase_counts: Record<string, number>;
}

export interface CopyTemplateBody {
  s3_key: string;
  package_id: string;
}

export interface CopyTemplateResponse {
  document_id: string;
  doc_type: string;
  filename: string;
  package_id: string;
  source: string;
}

export interface S3TemplatePreviewResponse {
  type: 'pdf' | 'markdown' | 'xlsx';
  url?: string; // when type === 'pdf'
  content?: string; // when type === 'markdown' or 'xlsx'
  preview_mode?: string; // when type === 'xlsx'
  preview_sheets?: XlsxPreviewSheet[]; // when type === 'xlsx'
  filename: string;
}

export interface XlsxPreviewSheet {
  sheet_id: string;
  title: string;
  max_row: number;
  max_col: number;
  truncated: boolean;
  rows: XlsxPreviewRow[];
}

export interface XlsxPreviewRow {
  row_index: number;
  cells: XlsxPreviewCell[];
}

export interface XlsxPreviewCell {
  cell_ref: string;
  row: number;
  col: number;
  value: string;
  display_value: string;
  editable: boolean;
  is_formula: boolean;
}

export interface S3TemplateDownloadResponse {
  download_url: string;
  filename: string;
  expires_in: number;
}
