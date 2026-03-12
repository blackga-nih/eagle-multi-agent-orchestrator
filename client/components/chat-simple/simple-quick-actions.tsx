'use client';

const quickActions = [
    { emoji: '🆕', label: 'New Intake', command: '__INTAKE_FORM__' },
    { emoji: '📄', label: 'Generate SOW', command: 'Generate a Statement of Work for a new IT services contract at NCI.' },
    { emoji: '📚', label: 'Search FAR', command: 'Search FAR/DFARS for simplified acquisition procedures and thresholds.' },
    { emoji: '💰', label: 'Cost Estimate', command: 'Create a cost estimate for procuring medical imaging equipment for NCI.' },
    { emoji: '🏢', label: 'Small Business', command: 'What are the small business set-aside requirements for a $500K procurement?' },
];

interface SimpleQuickActionsProps {
    onAction: (text: string) => void;
}

export default function SimpleQuickActions({ onAction }: SimpleQuickActionsProps) {
    return (
        <div className="flex items-center gap-1.5 mb-2 flex-wrap">
            {quickActions.map((action) => (
                <button
                    key={action.label}
                    onClick={() => onAction(action.command)}
                    className="px-3 py-1 text-[11px] font-medium text-[#003366] bg-[#EEF2F7] border border-[#D8DEE6] rounded-full whitespace-nowrap transition-all hover:bg-[#003366] hover:text-white hover:border-[#003366]"
                >
                    {action.emoji} {action.label}
                </button>
            ))}
        </div>
    );
}
