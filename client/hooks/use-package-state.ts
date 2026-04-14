'use client';

import { useState, useCallback } from 'react';

/** Single rich checklist item (one per required slug). */
export interface ChecklistItem {
  slug: string;
  label: string;
  status: 'pending' | 'completed';
  document_id?: string;
  version?: number;
  updated_at?: string;
  doc_status?: string;
}

/** Checklist state pushed by the update_state tool via SSE metadata. */
export interface PackageChecklist {
  required: string[];
  completed: string[];
  missing: string[];
  complete: boolean;
  /** Rich items[] derived from DOCUMENT# (Phase B). */
  items?: ChecklistItem[];
  /** Off-script docs that exist in DOCUMENT# but are NOT in required[]. */
  extra?: ChecklistItem[];
  /** Acquisition pathway slug. */
  pathway?: string | null;
  /** Package title — comes through on every checklist update. */
  title?: string | null;
  /** True when the user has curated the required-doc list (Option D). */
  custom?: boolean;
  /** Soft warnings from a PATCH /required-docs response. */
  warnings?: string[];
  /** Checklist provenance (null for legacy packages). */
  pmr_checklist_name?: string | null;
  pmr_checklist_s3_key?: string | null;
  nih_oag_section?: string | null;
}

/** A single compliance finding item. */
export interface ComplianceItem {
  name: string;
  note: string;
}

/** All state types that can be pushed from the backend. */
export interface PackageState {
  /** Current package ID (if in package mode). */
  packageId: string | null;
  /** Human-readable package title (falls back to packageId if null). */
  packageTitle: string | null;
  /** Current acquisition workflow phase. */
  phase: string | null;
  /** Previous phase (set on phase_change events). */
  previousPhase: string | null;
  /** Live checklist state — updated after every state push. */
  checklist: PackageChecklist | null;
  /** Overall progress percentage (0-100). */
  progressPct: number;
  /** Most recently completed document type. */
  lastDocumentType: string | null;
  /** Active compliance alerts. */
  complianceAlerts: Array<{
    severity: 'info' | 'warning' | 'critical';
    items: ComplianceItem[];
    timestamp: Date;
  }>;
}

const INITIAL_STATE: PackageState = {
  packageId: null,
  packageTitle: null,
  phase: null,
  previousPhase: null,
  checklist: null,
  progressPct: 0,
  lastDocumentType: null,
  complianceAlerts: [],
};

/**
 * Hook that maintains live acquisition package state from SSE metadata events.
 *
 * Usage:
 *   const { state, handleMetadata, reset } = usePackageState();
 *   // Pass handleMetadata as onMetadata to useAgentStream
 */
export function usePackageState() {
  const [state, setState] = useState<PackageState>(INITIAL_STATE);

  const handleMetadata = useCallback((metadata: Record<string, unknown>) => {
    const stateType = metadata.state_type as string;
    if (!stateType) return;

    setState((prev) => {
      const next = { ...prev };

      // Always update package ID if present
      if (metadata.package_id) {
        next.packageId = metadata.package_id as string;
      }

      // Pick up human-readable title from any state event that includes it.
      // Backend now emits `title` on checklist_update / document_ready /
      // end-of-turn refresh — use it everywhere, not just package_update.
      if (typeof metadata.title === 'string' && metadata.title.trim()) {
        next.packageTitle = metadata.title as string;
      }

      // Always update checklist if present in the payload
      if (metadata.checklist && typeof metadata.checklist === 'object') {
        next.checklist = metadata.checklist as PackageChecklist;
      }

      // Progress percentage
      if (typeof metadata.progress_pct === 'number') {
        next.progressPct = metadata.progress_pct as number;
      }

      switch (stateType) {
        case 'checklist_update':
          // Checklist + progress already handled above.
          // Also pick up phase/title if present (end-of-turn refresh).
          if (metadata.phase) {
            next.phase = metadata.phase as string;
          }
          break;

        case 'phase_change':
          next.previousPhase = (metadata.previous as string) || prev.phase;
          next.phase = (metadata.phase as string) || prev.phase;
          break;

        case 'document_ready':
          next.lastDocumentType = (metadata.doc_type as string) || null;
          break;

        case 'compliance_alert':
          next.complianceAlerts = [
            ...prev.complianceAlerts,
            {
              severity: (metadata.severity as 'info' | 'warning' | 'critical') || 'info',
              items: (metadata.items as ComplianceItem[]) || [],
              timestamp: new Date(),
            },
          ];
          break;

        case 'package_update':
          // Session restore path — /api/sessions/{id}/context sends this
          if (metadata.phase) next.phase = metadata.phase as string;
          break;
      }

      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  return { state, handleMetadata, reset };
}
