'use client';

import type { ContractTypeFactor } from './matrix-types';

interface FactorInputProps {
  factor: ContractTypeFactor;
  selectedOptionId: string | null;
  index: number;
  onSelect: (optionId: string) => void;
}

export default function FactorInput({ factor, selectedOptionId, index, onSelect }: FactorInputProps) {
  const answered = selectedOptionId !== null;

  return (
    <div className={`rounded-lg border transition-all ${
      answered ? 'border-blue-200 bg-blue-50/30' : 'border-gray-200 bg-white'
    }`}>
      <div className="flex items-center gap-3 px-4 py-3">
        <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
          answered ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-500'
        }`}>
          {answered ? '\u2713' : index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-gray-800">{factor.name}</div>
          <div className="text-[10px] text-gray-400">{factor.farRef}</div>
        </div>
      </div>
      <div className="px-4 pb-3 space-y-1">
        {factor.options.map(opt => (
          <button
            key={opt.id}
            onClick={() => onSelect(opt.id)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md border text-left transition-all ${
              selectedOptionId === opt.id
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-100 bg-white hover:border-blue-300 hover:bg-blue-50/50'
            }`}
          >
            <div className={`w-3 h-3 rounded-full border-2 flex-shrink-0 relative ${
              selectedOptionId === opt.id ? 'border-blue-500' : 'border-gray-300'
            }`}>
              {selectedOptionId === opt.id && (
                <div className="absolute inset-[2px] bg-blue-500 rounded-full" />
              )}
            </div>
            <div>
              <div className="text-xs font-medium text-gray-700">{opt.label}</div>
              {opt.description && <div className="text-[10px] text-gray-400">{opt.description}</div>}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
