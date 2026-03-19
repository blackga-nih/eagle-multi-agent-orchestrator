'use client';

import { useState, useCallback } from 'react';

/** Checklist state pushed by the update_state tool via SSE metadata. */
export interface PackageChecklist {
  required: string[];
  completed: string[];
  missing: string[];
  complete: boolean;
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
      }

      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  return { state, handleMetadata, reset };
}
