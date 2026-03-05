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
