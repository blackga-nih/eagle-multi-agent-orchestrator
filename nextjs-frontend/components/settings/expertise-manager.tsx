'use client';

import { useState } from 'react';
import {
  Trash2,
  RefreshCw,
  ChevronRight,
  FileCheck,
  FilePen,
  Eye,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  X,
} from 'lucide-react';
import { useExpertise } from '@/hooks/use-expertise';
import type { ExpertiseSection } from '@/types/expertise';

interface ExpertiseManagerProps {
  userId?: string;
}

export default function ExpertiseManager({ userId }: ExpertiseManagerProps) {
  const {
    expertise,
    loading,
    error,
    logs,
    clearAll,
    clearSection,
    removeEntry,
    refresh,
  } = useExpertise({ userId });

  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    completed_intakes: true,
    draft_intakes: true,
    viewed_workflows: false,
    document_actions: false,
  });

  const [showLogs, setShowLogs] = useState(false);
  const [confirmClear, setConfirmClear] = useState<string | null>(null);

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handleClearSection = async (section: ExpertiseSection) => {
    if (confirmClear === section) {
      await clearSection(section);
      setConfirmClear(null);
    } else {
      setConfirmClear(section);
      setTimeout(() => setConfirmClear(null), 3000);
    }
  };

  const handleClearAll = async () => {
    if (confirmClear === 'all') {
      await clearAll();
      setConfirmClear(null);
    } else {
      setConfirmClear('all');
      setTimeout(() => setConfirmClear(null), 3000);
    }
  };

  if (loading && !expertise) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin text-blue-600" />
          <span className="text-gray-600">Loading expertise data...</span>
        </div>
      </div>
    );
  }

  const data = expertise?.expertise_data;
  const totalImprovements = expertise?.total_improvements || 0;
  const lastImprovement = expertise?.last_improvement_at
    ? new Date(expertise.last_improvement_at).toLocaleString()
    : 'Never';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Your Expertise Profile</h2>
            <p className="text-sm text-gray-500 mt-1">
              The system learns from your actions to provide personalized assistance.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            >
              {showLogs ? 'Hide Logs' : 'Show Logs'}
            </button>
            <button
              onClick={refresh}
              disabled={loading}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2 text-sm text-amber-700">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-gray-50 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-blue-600">{totalImprovements}</div>
            <div className="text-xs text-gray-500 mt-1">Total Interactions</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-emerald-600">
              {(data?.completed_intakes.length || 0) + (data?.draft_intakes.length || 0)}
            </div>
            <div className="text-xs text-gray-500 mt-1">Intakes Tracked</div>
          </div>
          <div className="bg-gray-50 rounded-lg p-4 text-center">
            <div className="text-2xl font-bold text-purple-600">
              {data?.document_actions.length || 0}
            </div>
            <div className="text-xs text-gray-500 mt-1">Document Actions</div>
          </div>
        </div>

        <div className="mt-4 flex items-center justify-between text-sm">
          <span className="text-gray-500">
            <Clock className="w-4 h-4 inline mr-1" />
            Last activity: {lastImprovement}
          </span>
          <button
            onClick={handleClearAll}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              confirmClear === 'all'
                ? 'bg-red-600 text-white'
                : 'text-red-600 bg-red-50 hover:bg-red-100'
            }`}
          >
            {confirmClear === 'all' ? 'Click again to confirm' : 'Clear All Expertise'}
          </button>
        </div>
      </div>

      {/* ACT -> LEARN -> REUSE Indicator */}
      <div className="bg-gradient-to-r from-amber-50 via-emerald-50 to-indigo-50 rounded-lg border border-gray-200 p-4">
        <div className="flex items-center justify-center gap-6">
          <div className="text-center">
            <div className="px-3 py-1 bg-amber-100 text-amber-700 text-xs font-bold rounded-full">ACT</div>
            <div className="text-[10px] text-gray-500 mt-1">You take action</div>
          </div>
          <ChevronRight className="w-4 h-4 text-gray-400" />
          <div className="text-center">
            <div className="px-3 py-1 bg-emerald-100 text-emerald-700 text-xs font-bold rounded-full">LEARN</div>
            <div className="text-[10px] text-gray-500 mt-1">System learns</div>
          </div>
          <ChevronRight className="w-4 h-4 text-gray-400" />
          <div className="text-center">
            <div className="px-3 py-1 bg-indigo-100 text-indigo-700 text-xs font-bold rounded-full">REUSE</div>
            <div className="text-[10px] text-gray-500 mt-1">Better answers</div>
          </div>
        </div>
      </div>

      {/* Activity Logs */}
      {showLogs && logs.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Recent Activity Log</h3>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {logs.map((log, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className={`px-1.5 py-0.5 rounded font-medium ${
                  log.phase === 'ACT' ? 'bg-amber-100 text-amber-700' :
                  log.phase === 'LEARN' ? 'bg-emerald-100 text-emerald-700' :
                  'bg-indigo-100 text-indigo-700'
                }`}>
                  {log.phase}
                </span>
                <span className="text-gray-500">{log.action}:</span>
                <span className="text-gray-700 flex-1">{log.details}</span>
                <span className="text-gray-400 text-[10px]">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Completed Intakes Section */}
      <Section
        title="Completed Intakes"
        subtitle="Acquisitions you've submitted (strongest signal)"
        icon={FileCheck}
        iconColor="text-emerald-600"
        count={data?.completed_intakes.length || 0}
        expanded={expandedSections.completed_intakes}
        onToggle={() => toggleSection('completed_intakes')}
        onClear={() => handleClearSection('completed_intakes')}
        confirmClear={confirmClear === 'completed_intakes'}
      >
        {data?.completed_intakes.map((intake) => (
          <EntryCard
            key={intake.intake_id}
            id={intake.intake_id}
            title={`${intake.acquisition_type} Acquisition`}
            subtitle={intake.cost_category}
            timestamp={intake.completed_at}
            count={intake.completion_count}
            onRemove={() => removeEntry('completed_intakes', intake.intake_id)}
          />
        ))}
        {(!data?.completed_intakes || data.completed_intakes.length === 0) && (
          <EmptyState message="No completed intakes yet. Submit an acquisition request to start building your expertise." />
        )}
      </Section>

      {/* Draft Intakes Section */}
      <Section
        title="Draft Intakes"
        subtitle="Saved drafts you haven't submitted yet"
        icon={FilePen}
        iconColor="text-amber-600"
        count={data?.draft_intakes.length || 0}
        expanded={expandedSections.draft_intakes}
        onToggle={() => toggleSection('draft_intakes')}
        onClear={() => handleClearSection('draft_intakes')}
        confirmClear={confirmClear === 'draft_intakes'}
      >
        {data?.draft_intakes.map((draft) => (
          <EntryCard
            key={draft.intake_id}
            id={draft.intake_id}
            title={`${draft.acquisition_type} Draft`}
            subtitle={draft.cost_category}
            timestamp={draft.saved_at}
            count={draft.save_count}
            onRemove={() => removeEntry('draft_intakes', draft.intake_id)}
          />
        ))}
        {(!data?.draft_intakes || data.draft_intakes.length === 0) && (
          <EmptyState message="No draft intakes. Saved drafts will appear here." />
        )}
      </Section>

      {/* Viewed Workflows Section */}
      <Section
        title="Viewed Workflows"
        subtitle="Workflows you've browsed (weakest signal)"
        icon={Eye}
        iconColor="text-blue-600"
        count={data?.viewed_workflows.length || 0}
        expanded={expandedSections.viewed_workflows}
        onToggle={() => toggleSection('viewed_workflows')}
        onClear={() => handleClearSection('viewed_workflows')}
        confirmClear={confirmClear === 'viewed_workflows'}
      >
        {data?.viewed_workflows.map((workflow) => (
          <EntryCard
            key={workflow.workflow_id}
            id={workflow.workflow_id}
            title={workflow.workflow_type}
            subtitle={workflow.status}
            timestamp={workflow.viewed_at}
            count={workflow.view_count}
            onRemove={() => removeEntry('viewed_workflows', workflow.workflow_id)}
          />
        ))}
        {(!data?.viewed_workflows || data.viewed_workflows.length === 0) && (
          <EmptyState message="No viewed workflows. Browse workflows to build context." />
        )}
      </Section>

      {/* Document Actions Section */}
      <Section
        title="Document Interactions"
        subtitle="Documents you've worked with"
        icon={FileText}
        iconColor="text-purple-600"
        count={data?.document_actions.length || 0}
        expanded={expandedSections.document_actions}
        onToggle={() => toggleSection('document_actions')}
        onClear={() => handleClearSection('document_actions')}
        confirmClear={confirmClear === 'document_actions'}
      >
        {data?.document_actions.map((action, i) => (
          <EntryCard
            key={`${action.document_id}-${action.action}-${i}`}
            id={action.document_id}
            title={action.document_type}
            subtitle={action.action}
            timestamp={action.acted_at}
            count={action.action_count}
            onRemove={() => removeEntry('document_actions', action.document_id)}
          />
        ))}
        {(!data?.document_actions || data.document_actions.length === 0) && (
          <EmptyState message="No document interactions. Upload or view documents to track familiarity." />
        )}
      </Section>
    </div>
  );
}

// Section component
interface SectionProps {
  title: string;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  iconColor: string;
  count: number;
  expanded: boolean;
  onToggle: () => void;
  onClear: () => void;
  confirmClear: boolean;
  children: React.ReactNode;
}

function Section({
  title,
  subtitle,
  icon: Icon,
  iconColor,
  count,
  expanded,
  onToggle,
  onClear,
  confirmClear,
  children,
}: SectionProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg bg-gray-100 ${iconColor}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-gray-900">{title}</span>
              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-full">
                {count}
              </span>
            </div>
            <span className="text-xs text-gray-500">{subtitle}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {count > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onClear();
              }}
              className={`p-1.5 rounded-lg transition-colors ${
                confirmClear
                  ? 'bg-red-100 text-red-600'
                  : 'text-gray-400 hover:text-red-600 hover:bg-red-50'
              }`}
              title={confirmClear ? 'Click again to confirm' : 'Clear section'}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <ChevronRight
            className={`w-5 h-5 text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
          />
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-100 p-4 space-y-2">
          {children}
        </div>
      )}
    </div>
  );
}

// Entry card component
interface EntryCardProps {
  id: string;
  title: string;
  subtitle: string;
  timestamp: string;
  count: number;
  onRemove: () => void;
}

function EntryCard({ id, title, subtitle, timestamp, count, onRemove }: EntryCardProps) {
  return (
    <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg group">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-900 text-sm capitalize">{title}</span>
          {count > 1 && (
            <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[10px] rounded">
              {count}x
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs text-gray-500 capitalize">{subtitle}</span>
          <span className="text-gray-300">•</span>
          <span className="text-xs text-gray-400">
            {new Date(timestamp).toLocaleDateString()}
          </span>
        </div>
      </div>
      <button
        onClick={onRemove}
        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded opacity-0 group-hover:opacity-100 transition-all"
        title="Remove entry"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

// Empty state component
function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-6 text-sm text-gray-500">
      <CheckCircle2 className="w-8 h-8 mx-auto text-gray-300 mb-2" />
      {message}
    </div>
  );
}
