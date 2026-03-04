/**
 * Typed async API client for admin entity CRUD.
 *
 * All calls go through Next.js proxy routes which forward to FastAPI.
 * Pattern follows client/app/admin/costs/page.tsx fetch pattern.
 */

import type {
  PluginEntity,
  Workspace,
  WorkspaceOverride,
  PromptOverride,
  CustomSkill,
  TemplateEntity,
  CreateWorkspaceBody,
  SetPromptBody,
  CreateSkillBody,
  SetOverrideBody,
  CreateTemplateBody,
} from '@/types/admin';

type GetToken = () => Promise<string>;

// ---------------------------------------------------------------------------
// Core fetch helpers
// ---------------------------------------------------------------------------

async function apiGet<T>(getToken: GetToken, url: string): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function apiPost<T>(getToken: GetToken, url: string, body: unknown): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function apiPut<T>(getToken: GetToken, url: string, body?: unknown): Promise<T> {
  const token = await getToken();
  const res = await fetch(url, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function apiDelete(getToken: GetToken, url: string): Promise<void> {
  const token = await getToken();
  const res = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
}

// ---------------------------------------------------------------------------
// Plugin API (PLUGIN# entities — agents, skills, templates)
// ---------------------------------------------------------------------------

export const pluginApi = {
  list: (getToken: GetToken, entityType: string) =>
    apiGet<PluginEntity[]>(getToken, `/api/admin/plugin/${entityType}`),

  get: (getToken: GetToken, entityType: string, name: string) =>
    apiGet<PluginEntity>(getToken, `/api/admin/plugin/${entityType}/${name}`),

  update: (getToken: GetToken, entityType: string, name: string, body: Record<string, unknown>) =>
    apiPut<PluginEntity>(getToken, `/api/admin/plugin/${entityType}/${name}`, body),
};

// ---------------------------------------------------------------------------
// Workspace API (WORKSPACE# entities)
// ---------------------------------------------------------------------------

export const workspaceApi = {
  list: (getToken: GetToken) =>
    apiGet<Workspace[]>(getToken, '/api/workspace'),

  create: (getToken: GetToken, body: CreateWorkspaceBody) =>
    apiPost<Workspace>(getToken, '/api/workspace', body),

  get: (getToken: GetToken, id: string) =>
    apiGet<Workspace>(getToken, `/api/workspace/${id}`),

  getActive: (getToken: GetToken) =>
    apiGet<Workspace>(getToken, '/api/workspace/active'),

  activate: (getToken: GetToken, id: string) =>
    apiPut<Workspace>(getToken, `/api/workspace/${id}/activate`),

  delete: (getToken: GetToken, id: string) =>
    apiDelete(getToken, `/api/workspace/${id}`),

  listOverrides: (getToken: GetToken, id: string) =>
    apiGet<WorkspaceOverride[]>(getToken, `/api/workspace/${id}/overrides`),

  setOverride: (getToken: GetToken, id: string, entityType: string, name: string, body: SetOverrideBody) =>
    apiPut<WorkspaceOverride>(getToken, `/api/workspace/${id}/overrides/${entityType}/${name}`, body),

  deleteOverride: (getToken: GetToken, id: string, entityType: string, name: string) =>
    apiDelete(getToken, `/api/workspace/${id}/overrides/${entityType}/${name}`),

  resetOverrides: (getToken: GetToken, id: string) =>
    apiDelete(getToken, `/api/workspace/${id}/overrides`),
};

// ---------------------------------------------------------------------------
// Prompt API (PROMPT# overrides)
// ---------------------------------------------------------------------------

export const promptApi = {
  list: (getToken: GetToken) =>
    apiGet<PromptOverride[]>(getToken, '/api/admin/prompts'),

  set: (getToken: GetToken, agentName: string, body: SetPromptBody) =>
    apiPut<PromptOverride>(getToken, `/api/admin/prompts/${agentName}`, body),

  delete: (getToken: GetToken, agentName: string) =>
    apiDelete(getToken, `/api/admin/prompts/${agentName}`),
};

// ---------------------------------------------------------------------------
// Skills API (SKILL# custom skills)
// ---------------------------------------------------------------------------

export const skillApi = {
  list: (getToken: GetToken, status?: string) =>
    apiGet<CustomSkill[]>(getToken, `/api/skills${status ? `?status=${status}` : ''}`),

  create: (getToken: GetToken, body: CreateSkillBody) =>
    apiPost<CustomSkill>(getToken, '/api/skills', body),

  get: (getToken: GetToken, id: string) =>
    apiGet<CustomSkill>(getToken, `/api/skills/${id}`),

  update: (getToken: GetToken, id: string, body: Partial<CreateSkillBody>) =>
    apiPut<CustomSkill>(getToken, `/api/skills/${id}`, body),

  submit: (getToken: GetToken, id: string) =>
    apiPost<CustomSkill>(getToken, `/api/skills/${id}/submit`, {}),

  publish: (getToken: GetToken, id: string) =>
    apiPost<CustomSkill>(getToken, `/api/skills/${id}/publish`, {}),

  delete: (getToken: GetToken, id: string) =>
    apiDelete(getToken, `/api/skills/${id}`),
};

// ---------------------------------------------------------------------------
// Templates API (TEMPLATE# + PLUGIN# templates)
// ---------------------------------------------------------------------------

export const templateApi = {
  list: (getToken: GetToken, docType?: string) =>
    apiGet<TemplateEntity[]>(getToken, `/api/templates${docType ? `?doc_type=${docType}` : ''}`),

  get: (getToken: GetToken, docType: string) =>
    apiGet<TemplateEntity>(getToken, `/api/templates/${docType}`),

  create: (getToken: GetToken, docType: string, body: CreateTemplateBody) =>
    apiPost<TemplateEntity>(getToken, `/api/templates/${docType}`, body),

  delete: (getToken: GetToken, docType: string) =>
    apiDelete(getToken, `/api/templates/${docType}`),
};
