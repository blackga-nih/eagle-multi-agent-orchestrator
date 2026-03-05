'use client';

import { useEffect, useRef, useState } from 'react';
import { SlashCommand, slashCommands, commandColorClasses, filterCommands } from '@/lib/slash-commands';
import { Command, X, Search } from 'lucide-react';

interface CommandPaletteProps {
    isOpen: boolean;
    onClose: () => void;
    onSelect: (command: SlashCommand) => void;
}

export default function CommandPalette({ isOpen, onClose, onSelect }: CommandPaletteProps) {
    const [query, setQuery] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);
    const overlayRef = useRef<HTMLDivElement>(null);

    const filtered = query ? filterCommands(query) : slashCommands;

    // Group by category (ordered)
    const categoryOrder = ['Documents', 'Compliance', 'Research', 'Workflow', 'Admin', 'Info'];
    const grouped = categoryOrder
        .map(cat => ({ label: cat, commands: filtered.filter(c => c.category === cat) }))
        .filter(g => g.commands.length > 0);

    // Focus search input on open
    useEffect(() => {
        if (isOpen) {
            setQuery('');
            setTimeout(() => inputRef.current?.focus(), 50);
        }
    }, [isOpen]);

    // Close on Escape
    useEffect(() => {
        if (!isOpen) return;
        const handleKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                onClose();
            }
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const handleSelect = (cmd: SlashCommand) => {
        onSelect(cmd);
        onClose();
    };

    const handleOverlayClick = (e: React.MouseEvent) => {
        if (e.target === overlayRef.current) {
            onClose();
        }
    };

    const renderGroup = (label: string, commands: SlashCommand[]) => {
        if (commands.length === 0) return null;
        return (
            <div key={label}>
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                    {label}
                </p>
                <div className="flex flex-wrap gap-2">
                    {commands.map((cmd) => {
                        const Icon = cmd.icon;
                        const colors = commandColorClasses[cmd.color];
                        return (
                            <div key={cmd.id} className="group relative">
                                <button
                                    onClick={() => handleSelect(cmd)}
                                    className={`flex items-center gap-2 px-3.5 py-2 rounded-full border transition-all
                                        ${colors.border} ${colors.bg} hover:shadow-md hover:scale-[1.03] active:scale-[0.97]`}
                                >
                                    <Icon className={`w-3.5 h-3.5 ${colors.text}`} />
                                    <span className={`text-xs font-medium ${colors.text}`}>
                                        {cmd.name}
                                    </span>
                                </button>
                                <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1.5
                                    px-3 py-1.5 bg-gray-800 text-white text-[11px] rounded-lg
                                    whitespace-nowrap opacity-0 group-hover:opacity-100
                                    pointer-events-none transition-opacity z-10 shadow-lg">
                                    {cmd.description}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        );
    };

    return (
        <div
            ref={overlayRef}
            onClick={handleOverlayClick}
            className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] bg-black/30 backdrop-blur-sm animate-in fade-in duration-150"
        >
            <div className="w-full max-w-4xl bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden animate-in zoom-in-95 slide-in-from-bottom-4 duration-200">
                {/* Header */}
                <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
                    <Command className="w-4 h-4 text-gray-400 shrink-0" />
                    <div className="flex-1 flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5">
                        <Search className="w-3.5 h-3.5 text-gray-400" />
                        <input
                            ref={inputRef}
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="Search commands..."
                            className="bg-transparent text-sm text-gray-700 placeholder-gray-400 outline-none flex-1"
                        />
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* Body — command pills */}
                <div className="px-6 py-5 space-y-5 max-h-[60vh] overflow-y-auto">
                    {filtered.length === 0 ? (
                        <p className="text-sm text-gray-400 text-center py-6">
                            No commands match &ldquo;{query}&rdquo;
                        </p>
                    ) : (
                        <>
                            {grouped.map(({ label, commands }) => renderGroup(label, commands))}
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="px-4 py-2.5 border-t border-gray-100 bg-gray-50 flex items-center justify-between">
                    <span className="text-[10px] text-gray-400">
                        Click a command to insert it into the chat
                    </span>
                    <span className="text-[10px] text-gray-400">
                        <kbd className="px-1.5 py-0.5 bg-white rounded border border-gray-200 font-mono">Esc</kbd>
                        {' '}to close
                    </span>
                </div>
            </div>
        </div>
    );
}
