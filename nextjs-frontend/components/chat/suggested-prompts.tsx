'use client';

import { Package, Search, FileText, HelpCircle } from 'lucide-react';

interface SuggestedPromptsProps {
    onSelect: (prompt: string) => void;
    compact?: boolean;
}

const suggestions = [
    {
        id: 'acquisition',
        label: 'Acquisition Package',
        description: 'Start a new procurement request',
        icon: Package,
        color: 'blue',
        prompt: '/acquisition-package',
    },
    {
        id: 'research',
        label: 'Research',
        description: 'Search regulations & policies',
        icon: Search,
        color: 'green',
        prompt: '/research',
    },
    {
        id: 'document',
        label: 'Document Generation',
        description: 'Generate procurement documents',
        icon: FileText,
        color: 'purple',
        prompt: '/document',
    },
    {
        id: 'help',
        label: 'Help',
        description: 'Learn what I can do',
        icon: HelpCircle,
        color: 'gray',
        prompt: '/help',
    },
];

const colorClasses: Record<string, { bg: string; hover: string; icon: string; border: string }> = {
    blue: {
        bg: 'bg-blue-50',
        hover: 'hover:bg-blue-100 hover:border-blue-300',
        icon: 'text-blue-600',
        border: 'border-blue-200',
    },
    green: {
        bg: 'bg-green-50',
        hover: 'hover:bg-green-100 hover:border-green-300',
        icon: 'text-green-600',
        border: 'border-green-200',
    },
    purple: {
        bg: 'bg-purple-50',
        hover: 'hover:bg-purple-100 hover:border-purple-300',
        icon: 'text-purple-600',
        border: 'border-purple-200',
    },
    gray: {
        bg: 'bg-gray-50',
        hover: 'hover:bg-gray-100 hover:border-gray-300',
        icon: 'text-gray-600',
        border: 'border-gray-200',
    },
};

export default function SuggestedPrompts({ onSelect, compact = false }: SuggestedPromptsProps) {
    if (compact) {
        // Compact version: small icons near chat input
        return (
            <div className="flex items-center gap-2">
                {suggestions.map((suggestion) => {
                    const Icon = suggestion.icon;
                    const colors = colorClasses[suggestion.color];
                    return (
                        <button
                            key={suggestion.id}
                            onClick={() => onSelect(suggestion.prompt)}
                            className={`p-2 rounded-lg border transition-all ${colors.bg} ${colors.border} ${colors.hover}`}
                            title={suggestion.label}
                        >
                            <Icon className={`w-4 h-4 ${colors.icon}`} />
                        </button>
                    );
                })}
            </div>
        );
    }

    // Full version: large bubbles in welcome area
    return (
        <div className="flex flex-wrap justify-center gap-3 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-200">
            {suggestions.map((suggestion) => {
                const Icon = suggestion.icon;
                const colors = colorClasses[suggestion.color];
                return (
                    <button
                        key={suggestion.id}
                        onClick={() => onSelect(suggestion.prompt)}
                        className={`flex items-center gap-3 px-5 py-3 rounded-2xl border-2 transition-all shadow-sm hover:shadow-md ${colors.bg} ${colors.border} ${colors.hover}`}
                    >
                        <Icon className={`w-6 h-6 ${colors.icon}`} />
                        <div className="text-left">
                            <p className="font-semibold text-gray-900 text-sm">{suggestion.label}</p>
                            <p className="text-xs text-gray-500">{suggestion.description}</p>
                        </div>
                    </button>
                );
            })}
        </div>
    );
}
