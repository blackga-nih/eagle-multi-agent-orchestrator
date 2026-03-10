'use client';

import { useState, useCallback } from 'react';

interface IntakeQuestion {
    id: string;
    label: string;
    options?: string[];
}

const INTAKE_QUESTIONS: IntakeQuestion[] = [
    {
        id: 'acquisition_type',
        label: '1. Is this new, follow-on, or recompete?',
        options: ['New acquisition', 'Follow-on to existing contract', 'Recompete'],
    },
    {
        id: 'baseline_documents',
        label: '2. Do you have baseline documents?',
        options: ['Yes — I can upload them', 'No — starting from scratch', 'Some but not all'],
    },
    {
        id: 'user_role',
        label: '3. What is your role?',
        options: ['Requestor', 'Purchase card holder', 'COR', 'Contracting Officer'],
    },
    {
        id: 'budget_range',
        label: '4. Budget range',
        options: ['Under $15K', '$15K–$350K', '$350K–$2.5M', 'Over $2.5M', 'Not sure'],
    },
    {
        id: 'it_involved',
        label: '5. IT systems or services involved?',
        options: ['Yes', 'No'],
    },
    {
        id: 'timeline',
        label: '6. Timeline constraints?',
    },
];

interface IntakeFormCardProps {
    onSubmit: (payload: Record<string, unknown>) => void;
    disabled?: boolean;
}

export default function IntakeFormCard({ onSubmit, disabled = false }: IntakeFormCardProps) {
    const [answers, setAnswers] = useState<Record<string, { radio: string | null; text: string }>>(
        () => Object.fromEntries(INTAKE_QUESTIONS.map((q) => [q.id, { radio: null, text: '' }]))
    );
    const [notes, setNotes] = useState('');
    const [submitted, setSubmitted] = useState(false);

    const isDisabled = disabled || submitted;

    const handleRadioClick = useCallback((questionId: string, option: string) => {
        if (isDisabled) return;
        setAnswers((prev) => ({
            ...prev,
            [questionId]: {
                ...prev[questionId],
                radio: prev[questionId].radio === option ? null : option,
            },
        }));
    }, [isDisabled]);

    const handleTextChange = useCallback((questionId: string, text: string) => {
        if (isDisabled) return;
        setAnswers((prev) => ({
            ...prev,
            [questionId]: { ...prev[questionId], text },
        }));
    }, [isDisabled]);

    const handleSubmit = useCallback(() => {
        if (isDisabled) return;
        const payload = {
            form_type: 'baseline_intake',
            answers: Object.fromEntries(
                Object.entries(answers).map(([key, val]) => [
                    key,
                    { selected: val.radio, detail: val.text || undefined },
                ])
            ),
            notes: notes || undefined,
            submitted_at: new Date().toISOString(),
        };
        setSubmitted(true);
        onSubmit(payload);
    }, [isDisabled, answers, notes, onSubmit]);

    return (
        <div className={`rounded-xl border ${isDisabled ? 'border-gray-200 bg-gray-50 opacity-75' : 'border-[#D8DEE6] bg-white'} shadow-sm max-w-2xl mx-auto my-3 overflow-hidden`}>
            {/* Header */}
            <div className={`px-5 py-3 border-b ${isDisabled ? 'border-gray-200 bg-gray-100' : 'border-[#D8DEE6] bg-[#EEF2F7]'} flex items-center justify-between`}>
                <h3 className="text-sm font-semibold text-[#003366]">Quick Intake Questions</h3>
                {submitted && (
                    <span className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-green-100 text-green-700 rounded-full">
                        Submitted
                    </span>
                )}
            </div>

            {/* Questions */}
            <div className="px-5 py-4 space-y-5">
                {INTAKE_QUESTIONS.map((q) => (
                    <div key={q.id}>
                        <p className="text-xs font-medium text-[#2C3E50] mb-2">{q.label}</p>

                        {/* Radio options */}
                        {q.options && (
                            <div className="flex flex-wrap gap-1.5 mb-2">
                                {q.options.map((opt) => {
                                    const isSelected = answers[q.id]?.radio === opt;
                                    return (
                                        <button
                                            key={opt}
                                            type="button"
                                            disabled={isDisabled}
                                            onClick={() => handleRadioClick(q.id, opt)}
                                            className={`px-3 py-1.5 text-[11px] rounded-lg border transition-all ${
                                                isSelected
                                                    ? 'bg-[#003366] text-white border-[#003366]'
                                                    : isDisabled
                                                      ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                                                      : 'bg-white text-[#2C3E50] border-[#D8DEE6] hover:border-[#003366] hover:bg-[#EEF2F7]'
                                            }`}
                                        >
                                            {opt}
                                        </button>
                                    );
                                })}
                            </div>
                        )}

                        {/* Text input */}
                        <input
                            type="text"
                            disabled={isDisabled}
                            value={answers[q.id]?.text || ''}
                            onChange={(e) => handleTextChange(q.id, e.target.value)}
                            placeholder={q.options ? 'Additional detail (optional)' : 'Type your answer...'}
                            className={`w-full px-3 py-1.5 text-xs border rounded-lg transition-all ${
                                isDisabled
                                    ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                                    : 'bg-white text-[#2C3E50] border-[#D8DEE6] focus:outline-none focus:ring-1 focus:ring-[#2196F3]/30 focus:border-[#2196F3]'
                            }`}
                        />
                    </div>
                ))}

                {/* Notes */}
                <div>
                    <p className="text-xs font-medium text-[#2C3E50] mb-2">Additional notes</p>
                    <textarea
                        disabled={isDisabled}
                        value={notes}
                        onChange={(e) => !isDisabled && setNotes(e.target.value)}
                        placeholder="Any other context, constraints, or details..."
                        rows={3}
                        className={`w-full px-3 py-2 text-xs border rounded-lg resize-none transition-all ${
                            isDisabled
                                ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
                                : 'bg-white text-[#2C3E50] border-[#D8DEE6] focus:outline-none focus:ring-1 focus:ring-[#2196F3]/30 focus:border-[#2196F3]'
                        }`}
                    />
                </div>
            </div>

            {/* Submit button */}
            {!submitted && (
                <div className="px-5 py-3 border-t border-[#D8DEE6] bg-[#FAFBFC]">
                    <button
                        type="button"
                        disabled={isDisabled}
                        onClick={handleSubmit}
                        className="w-full py-2 text-sm font-semibold text-white bg-[#003366] rounded-lg hover:bg-[#004488] disabled:opacity-40 transition-all"
                    >
                        Submit Intake Form
                    </button>
                </div>
            )}
        </div>
    );
}
