'use client';

import { RotateCcw } from 'lucide-react';
import type { FactorAnswer, RankedRecommendation } from './matrix-types';
import { CONTRACT_TYPE_FACTORS } from './matrix-data';
import FactorInput from './factor-input';

interface ContractTypeSelectorTabProps {
  factorAnswers: FactorAnswer[];
  recommendations: RankedRecommendation[];
  onSetFactorAnswer: (factorId: string, optionId: string) => void;
  onClearAnswers: () => void;
  onUseType: (typeId: string) => void;
}

export default function ContractTypeSelectorTab({
  factorAnswers,
  recommendations,
  onSetFactorAnswer,
  onClearAnswers,
  onUseType,
}: ContractTypeSelectorTabProps) {
  const answered = factorAnswers.length;
  const total = CONTRACT_TYPE_FACTORS.length;
  const progressPct = (answered / total) * 100;

  function getSelectedOption(factorId: string): string | null {
    const a = factorAnswers.find((x) => x.factorId === factorId);
    return a ? a.optionId : null;
  }

  return (
    <div className="flex h-full">
      {/* Left: Factor Cards */}
      <div className="w-[400px] min-w-[400px] border-r border-gray-200 flex flex-col bg-gray-50">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
              13 FAR 16.104 Factors &mdash; Use to Guide Type Selection
            </div>
            {answered > 0 && (
              <button
                onClick={onClearAnswers}
                className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-red-500 transition-colors"
              >
                <RotateCcw className="w-3 h-3" />
                Reset All
              </button>
            )}
          </div>
          {/* Progress bar */}
          <div className="flex items-center gap-2">
            <div className="text-[10px] text-gray-400">Factors answered</div>
            <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            <div className="text-[10px] font-mono font-semibold text-gray-500">
              {answered} / {total}
            </div>
          </div>
        </div>

        {/* Scrollable factor list */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {CONTRACT_TYPE_FACTORS.map((factor, i) => (
            <FactorInput
              key={factor.id}
              factor={factor}
              index={i}
              selectedOptionId={getSelectedOption(factor.id)}
              onSelect={(optionId) => onSetFactorAnswer(factor.id, optionId)}
            />
          ))}
        </div>
      </div>

      {/* Right: Live Recommendation */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">
          Decision Tree &mdash; Click Through to Get a Recommendation
        </div>

        {answered < 3 ? (
          <div className="flex items-center justify-center h-64 text-gray-400 text-sm">
            <div className="text-center">
              <div className="text-4xl mb-3">&larr;</div>
              <div>Answer factors on the left to get a live recommendation.</div>
              <div className="text-xs mt-1">Each answer immediately updates the ranking here.</div>
            </div>
          </div>
        ) : (
          <div className="space-y-3 mt-4">
            {recommendations.map((rec, i) => {
              const isTop = i === 0 && !rec.blocked;
              return (
                <div
                  key={rec.typeId}
                  className={`rounded-lg border p-4 transition-all ${
                    rec.blocked
                      ? 'border-red-200 bg-red-50/30 opacity-60'
                      : isTop
                        ? 'border-blue-400 bg-blue-50 ring-1 ring-blue-200'
                        : 'border-gray-200 bg-white'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span
                        className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                          isTop ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-500'
                        }`}
                      >
                        #{i + 1}
                      </span>
                      <span
                        className={`text-sm font-semibold ${isTop ? 'text-blue-700' : 'text-gray-800'}`}
                      >
                        {rec.label}
                      </span>
                      {rec.blocked && (
                        <span className="text-[10px] px-2 py-0.5 rounded bg-red-200 text-red-700 font-bold">
                          BLOCKED
                        </span>
                      )}
                    </div>
                    {isTop && (
                      <button
                        onClick={() => onUseType(rec.typeId)}
                        className="text-[11px] font-medium text-white bg-blue-600 px-3 py-1 rounded hover:bg-blue-700 transition-colors"
                      >
                        Use this type
                      </button>
                    )}
                    {!isTop && !rec.blocked && (
                      <button
                        onClick={() => onUseType(rec.typeId)}
                        className="text-[11px] font-medium text-blue-600 bg-blue-50 px-3 py-1 rounded hover:bg-blue-100 transition-colors"
                      >
                        Use this type
                      </button>
                    )}
                  </div>

                  {/* Score bar */}
                  <div className="flex items-center gap-2 mb-1">
                    <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-300 ${
                          rec.blocked ? 'bg-red-400' : isTop ? 'bg-blue-500' : 'bg-gray-400'
                        }`}
                        style={{ width: `${rec.score}%` }}
                      />
                    </div>
                    <span className="text-xs font-mono font-semibold text-gray-500 w-8 text-right">
                      {rec.score}
                    </span>
                  </div>

                  {/* Reasoning */}
                  {rec.reasoning.length > 0 && (
                    <div className="text-[10px] text-gray-400 mt-1">
                      {rec.reasoning.slice(0, 3).join(' \u00b7 ')}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
