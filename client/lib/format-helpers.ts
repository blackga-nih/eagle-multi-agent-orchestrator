/**
 * Pure utility functions for formatting and styling.
 * Extracted from mock-data.ts — no mock data here.
 */

import type {
  WorkflowStatus,
  AcquisitionType,
  DocumentStatus,
  SkillType,
  UserRole,
} from '@/types/schema';

export function getWorkflowStatusColor(status: WorkflowStatus): string {
  const colors: Record<WorkflowStatus, string> = {
    draft: 'bg-gray-100 text-gray-700',
    in_progress: 'bg-blue-100 text-blue-700',
    pending_review: 'bg-amber-100 text-amber-700',
    approved: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-red-100 text-red-700',
    completed: 'bg-green-100 text-green-700',
    cancelled: 'bg-gray-200 text-gray-500',
    review: 'bg-amber-100 text-amber-700',
  };
  return colors[status] || colors.draft;
}

export function getAcquisitionTypeLabel(type: AcquisitionType): string {
  const labels: Record<AcquisitionType, string> = {
    micro_purchase: 'Micro-Purchase (<$10K)',
    simplified: 'Simplified ($10K-$250K)',
    negotiated: 'Negotiated (>$250K)',
  };
  return labels[type] || type;
}

export function getDocumentStatusColor(status: DocumentStatus): string {
  const colors: Record<DocumentStatus, string> = {
    not_started: 'bg-gray-100 text-gray-600',
    in_progress: 'bg-blue-100 text-blue-700',
    draft: 'bg-amber-100 text-amber-700',
    final: 'bg-purple-100 text-purple-700',
    approved: 'bg-green-100 text-green-700',
  };
  return colors[status] || colors.not_started;
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatTime(dateString: string): string {
  return new Date(dateString).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function getRelativeTime(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateString);
}

export function getSkillTypeColor(type: SkillType): string {
  const colors: Record<SkillType, string> = {
    document_gen: 'bg-purple-100 text-purple-700',
    data_extraction: 'bg-blue-100 text-blue-700',
    validation: 'bg-green-100 text-green-700',
    search: 'bg-amber-100 text-amber-700',
  };
  return colors[type] || 'bg-gray-100 text-gray-700';
}

export function getUserRoleColor(role: UserRole): string {
  const colors: Record<UserRole, string> = {
    co: 'bg-purple-100 text-purple-700',
    cor: 'bg-green-100 text-green-700',
    developer: 'bg-indigo-100 text-indigo-700',
    admin: 'bg-red-100 text-red-700',
    analyst: 'bg-amber-100 text-amber-700',
  };
  return colors[role] || 'bg-gray-100 text-gray-700';
}

export function getUserRoleLabel(role: UserRole): string {
  const labels: Record<UserRole, string> = {
    co: 'Contract Officer',
    cor: 'COR',
    developer: 'Developer',
    admin: 'Administrator',
    analyst: 'Analyst',
  };
  return labels[role] || role;
}

/** Map Cognito group roles to app UserRole. */
export function mapAuthRoleToUserRole(roles: string[]): UserRole {
  const roleMap: Record<string, UserRole> = {
    admin: 'admin',
    co: 'co',
    cor: 'cor',
    analyst: 'analyst',
    developer: 'developer',
  };
  for (const r of roles) {
    const mapped = roleMap[r.toLowerCase()];
    if (mapped) return mapped;
  }
  return 'developer';
}
