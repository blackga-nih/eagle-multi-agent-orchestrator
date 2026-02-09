/**
 * Expertise System Types
 *
 * Per-user behavioral tracking that learns from actions to personalize agent responses.
 * Follows ACT -> LEARN -> REUSE cycle.
 */

export interface CompletedIntake {
  intake_id: string;
  acquisition_type: string;  // "equipment", "service", "supply", "it", "construction"
  cost_category: string;     // "micro-purchase", "simplified", "negotiated"
  completed_at: string;
  completion_count: number;
}

export interface DraftIntake {
  intake_id: string;
  acquisition_type: string;
  cost_category: string;
  saved_at: string;
  save_count: number;
}

export interface ViewedWorkflow {
  workflow_id: string;
  workflow_type: string;
  status: string;  // "in_progress", "pending_review", "approved", "completed"
  viewed_at: string;
  view_count: number;
}

export interface DocumentAction {
  document_id: string;
  document_type: string;  // "SOW", "IGCE", "J&A", "Market Research", "Quote", etc.
  action: string;         // "upload", "download", "view", "edit"
  acted_at: string;
  action_count: number;
}

export interface ExpertiseData {
  completed_intakes: CompletedIntake[];
  draft_intakes: DraftIntake[];
  viewed_workflows: ViewedWorkflow[];
  document_actions: DocumentAction[];
}

export interface Expertise {
  user_id: string;
  total_improvements: number;
  last_improvement_at: string | null;
  expertise_data: ExpertiseData;
}

// Action types for tracking
export type ExpertiseActionType =
  | 'complete_intake'
  | 'save_draft'
  | 'view_workflow'
  | 'document_action';

export interface TrackActionPayload {
  action_type: ExpertiseActionType;
  // For intake actions
  intake_id?: string;
  acquisition_type?: string;
  cost_category?: string;
  // For workflow actions
  workflow_id?: string;
  workflow_type?: string;
  status?: string;
  // For document actions
  document_id?: string;
  document_type?: string;
  document_action?: string;
}

// Section names for management
export type ExpertiseSection =
  | 'completed_intakes'
  | 'draft_intakes'
  | 'viewed_workflows'
  | 'document_actions';

// Log entry for ACT -> LEARN -> REUSE visibility
export interface ExpertiseLogEntry {
  timestamp: string;
  phase: 'ACT' | 'LEARN' | 'REUSE';
  action: string;
  details: string;
}
