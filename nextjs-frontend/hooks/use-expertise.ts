'use client';

import { useState, useCallback, useEffect } from 'react';
import type {
  Expertise,
  ExpertiseSection,
  ExpertiseLogEntry,
  TrackActionPayload,
} from '@/types/expertise';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Default user ID (in production, get from auth)
const DEFAULT_USER_ID = 'user-1';

interface UseExpertiseOptions {
  userId?: string;
  autoFetch?: boolean;
}

interface UseExpertiseReturn {
  expertise: Expertise | null;
  loading: boolean;
  error: string | null;
  logs: ExpertiseLogEntry[];
  // Actions
  trackCompleteIntake: (intakeId: string, acquisitionType: string, costCategory: string) => Promise<void>;
  trackSaveDraft: (intakeId: string, acquisitionType: string, costCategory: string) => Promise<void>;
  trackViewWorkflow: (workflowId: string, workflowType: string, status: string) => Promise<void>;
  trackDocumentAction: (documentId: string, documentType: string, action: string) => Promise<void>;
  // Management
  clearAll: () => Promise<void>;
  clearSection: (section: ExpertiseSection) => Promise<void>;
  removeEntry: (section: ExpertiseSection, entryId: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useExpertise(options: UseExpertiseOptions = {}): UseExpertiseReturn {
  const { userId = DEFAULT_USER_ID, autoFetch = true } = options;

  const [expertise, setExpertise] = useState<Expertise | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<ExpertiseLogEntry[]>([]);

  // Add log entry
  const addLog = useCallback((phase: 'ACT' | 'LEARN' | 'REUSE', action: string, details: string) => {
    const entry: ExpertiseLogEntry = {
      timestamp: new Date().toISOString(),
      phase,
      action,
      details,
    };
    setLogs(prev => [entry, ...prev].slice(0, 50)); // Keep last 50 logs
    console.log(`[Expertise ${phase}] ${action}: ${details}`);
  }, []);

  // Fetch expertise
  const fetchExpertise = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}`);
      if (!response.ok) {
        throw new Error(`Failed to fetch expertise: ${response.statusText}`);
      }
      const data = await response.json();
      setExpertise(data);
      addLog('REUSE', 'expertise_loaded', `Loaded ${data.total_improvements} improvements`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      // Create empty expertise on error (new user)
      setExpertise({
        user_id: userId,
        total_improvements: 0,
        last_improvement_at: null,
        expertise_data: {
          completed_intakes: [],
          draft_intakes: [],
          viewed_workflows: [],
          document_actions: [],
        },
      });
    } finally {
      setLoading(false);
    }
  }, [userId, addLog]);

  // Auto-fetch on mount
  useEffect(() => {
    if (autoFetch) {
      fetchExpertise();
    }
  }, [autoFetch, fetchExpertise]);

  // Track completed intake
  const trackCompleteIntake = useCallback(async (
    intakeId: string,
    acquisitionType: string,
    costCategory: string
  ) => {
    addLog('ACT', 'complete_intake', `Intake ${intakeId} (${acquisitionType}, ${costCategory})`);

    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_type: 'complete_intake',
          intake_id: intakeId,
          acquisition_type: acquisitionType,
          cost_category: costCategory,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to track action: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'expertise_updated', `Total improvements: ${updated.total_improvements}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  // Track save draft
  const trackSaveDraft = useCallback(async (
    intakeId: string,
    acquisitionType: string,
    costCategory: string
  ) => {
    addLog('ACT', 'save_draft', `Draft ${intakeId} (${acquisitionType}, ${costCategory})`);

    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_type: 'save_draft',
          intake_id: intakeId,
          acquisition_type: acquisitionType,
          cost_category: costCategory,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to track action: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'expertise_updated', `Total improvements: ${updated.total_improvements}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  // Track view workflow
  const trackViewWorkflow = useCallback(async (
    workflowId: string,
    workflowType: string,
    status: string
  ) => {
    addLog('ACT', 'view_workflow', `Workflow ${workflowId} (${workflowType}, ${status})`);

    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_type: 'view_workflow',
          workflow_id: workflowId,
          workflow_type: workflowType,
          status,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to track action: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'expertise_updated', `Total improvements: ${updated.total_improvements}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  // Track document action
  const trackDocumentAction = useCallback(async (
    documentId: string,
    documentType: string,
    action: string
  ) => {
    addLog('ACT', 'document_action', `Document ${documentId} (${documentType}) - ${action}`);

    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_type: 'document_action',
          document_id: documentId,
          document_type: documentType,
          document_action: action,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to track action: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'expertise_updated', `Total improvements: ${updated.total_improvements}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  // Clear all expertise
  const clearAll = useCallback(async () => {
    addLog('ACT', 'clear_all', 'Clearing all expertise');

    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(`Failed to clear expertise: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'expertise_cleared', 'All expertise data cleared');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  // Clear specific section
  const clearSection = useCallback(async (section: ExpertiseSection) => {
    addLog('ACT', 'clear_section', `Clearing section: ${section}`);

    try {
      const response = await fetch(`${API_BASE}/api/expertise/${userId}/section/${section}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(`Failed to clear section: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'section_cleared', `Section ${section} cleared`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  // Remove specific entry
  const removeEntry = useCallback(async (section: ExpertiseSection, entryId: string) => {
    addLog('ACT', 'remove_entry', `Removing ${entryId} from ${section}`);

    try {
      const response = await fetch(
        `${API_BASE}/api/expertise/${userId}/section/${section}/entry/${entryId}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        throw new Error(`Failed to remove entry: ${response.statusText}`);
      }

      const updated = await response.json();
      setExpertise(updated);
      addLog('LEARN', 'entry_removed', `Removed ${entryId} from ${section}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      addLog('LEARN', 'error', message);
    }
  }, [userId, addLog]);

  return {
    expertise,
    loading,
    error,
    logs,
    trackCompleteIntake,
    trackSaveDraft,
    trackViewWorkflow,
    trackDocumentAction,
    clearAll,
    clearSection,
    removeEntry,
    refresh: fetchExpertise,
  };
}
