'use client';

const STAGES = ['Requirements', 'Compliance', 'Documents', 'Review'] as const;

interface WorkflowData {
  stage?: string;
  current_stage?: string;
  status?: string;
  message?: string;
  completed_stages?: string[];
}

function matchStageIndex(stage: string): number {
  const lower = stage.toLowerCase();
  if (lower.includes('requirement') || lower.includes('intake')) return 0;
  if (lower.includes('compliance') || lower.includes('check')) return 1;
  if (lower.includes('document') || lower.includes('draft')) return 2;
  if (lower.includes('review') || lower.includes('final') || lower.includes('approve')) return 3;
  return -1;
}

export default function IntakeWorkflowPanel({ text }: { text: string }) {
  let data: WorkflowData = {};
  try {
    const parsed = JSON.parse(text);
    data = typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return (
      <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">
          {text}
        </pre>
      </div>
    );
  }

  const currentStage = data.stage || data.current_stage || '';
  const currentIdx = matchStageIndex(currentStage);
  const completedSet = new Set(
    (data.completed_stages || []).map((s: string) => matchStageIndex(s)),
  );

  return (
    <div className="border-t border-[#E5E9F0] bg-white px-3 py-3">
      <div className="text-[9px] font-bold uppercase text-blue-600 tracking-wider mb-2">
        Intake Progress
      </div>

      {/* Horizontal step indicator */}
      <div className="flex items-center gap-1 mb-2">
        {STAGES.map((stage, idx) => {
          const isComplete = completedSet.has(idx) || idx < currentIdx;
          const isCurrent = idx === currentIdx;
          return (
            <div key={stage} className="flex items-center gap-1 flex-1">
              <div
                className={`flex items-center justify-center w-5 h-5 rounded-full text-[9px] font-bold shrink-0
                ${isComplete ? 'bg-green-500 text-white' : isCurrent ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-500'}`}
              >
                {isComplete ? '✓' : idx + 1}
              </div>
              <span
                className={`text-[9px] truncate ${isCurrent ? 'font-bold text-gray-800' : 'text-gray-500'}`}
              >
                {stage}
              </span>
              {idx < STAGES.length - 1 && (
                <div className={`flex-1 h-px ${isComplete ? 'bg-green-400' : 'bg-gray-200'}`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Status text */}
      {(data.status || data.message) && (
        <p className="text-[10px] text-gray-600">{data.message || data.status}</p>
      )}
    </div>
  );
}
