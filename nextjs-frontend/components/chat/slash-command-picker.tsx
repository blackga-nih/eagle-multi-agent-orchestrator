'use client';

import { useEffect, useRef } from 'react';
import { SlashCommand, commandColorClasses } from '@/lib/slash-commands';
import { Command } from 'lucide-react';

interface SlashCommandPickerProps {
    commands: SlashCommand[];
    selectedIndex: number;
    onSelect: (command: SlashCommand) => void;
    onClose: () => void;
}

export default function SlashCommandPicker({
    commands,
    selectedIndex,
    onSelect,
    onClose,
}: SlashCommandPickerProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const selectedRef = useRef<HTMLButtonElement>(null);

    // Close on click outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                onClose();
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [onClose]);

    // Scroll selected item into view
    useEffect(() => {
        selectedRef.current?.scrollIntoView({ block: 'nearest' });
    }, [selectedIndex]);

    if (commands.length === 0) {
        return (
            <div
                ref={containerRef}
                className="absolute bottom-full left-0 mb-2 w-80 bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200"
            >
                <div className="p-4 text-center text-gray-500 text-sm">
                    No commands found
                </div>
            </div>
        );
    }

    // Group commands by category
    const actionCommands = commands.filter((c) => c.category === 'actions');
    const infoCommands = commands.filter((c) => c.category === 'info');

    const renderCommand = (command: SlashCommand, index: number) => {
        const Icon = command.icon;
        const colors = commandColorClasses[command.color];
        const isSelected = index === selectedIndex;

        return (
            <button
                key={command.id}
                ref={isSelected ? selectedRef : null}
                onClick={() => onSelect(command)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                    isSelected
                        ? 'bg-blue-50 border-l-2 border-blue-500'
                        : 'hover:bg-gray-50 border-l-2 border-transparent'
                }`}
            >
                <div className={`p-2 rounded-lg ${colors.bg}`}>
                    <Icon className={`w-4 h-4 ${colors.text}`} />
                </div>
                <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900 text-sm">{command.name}</p>
                    <p className="text-xs text-gray-500 truncate">{command.description}</p>
                </div>
                {isSelected && (
                    <span className="text-[10px] text-gray-400 font-medium px-2 py-0.5 bg-gray-100 rounded">
                        Enter
                    </span>
                )}
            </button>
        );
    };

    // Calculate the actual index for commands across groups
    let currentIndex = 0;

    return (
        <div
            ref={containerRef}
            className="absolute bottom-full left-0 mb-2 w-80 bg-white rounded-xl border border-gray-200 shadow-lg overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200 z-50"
        >
            {/* Header */}
            <div className="px-3 py-2 border-b border-gray-100 bg-gray-50 flex items-center gap-2">
                <Command className="w-4 h-4 text-gray-400" />
                <span className="text-xs font-medium text-gray-500">Commands</span>
                <span className="ml-auto text-[10px] text-gray-400">
                    <kbd className="px-1 py-0.5 bg-white rounded border border-gray-200">↑</kbd>
                    <kbd className="px-1 py-0.5 bg-white rounded border border-gray-200 ml-0.5">↓</kbd>
                    <span className="mx-1">to navigate</span>
                </span>
            </div>

            {/* Commands list */}
            <div className="max-h-64 overflow-y-auto">
                {actionCommands.length > 0 && (
                    <div>
                        <div className="px-3 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider bg-gray-50/50">
                            Actions
                        </div>
                        {actionCommands.map((command) => {
                            const element = renderCommand(command, currentIndex);
                            currentIndex++;
                            return element;
                        })}
                    </div>
                )}

                {infoCommands.length > 0 && (
                    <div>
                        <div className="px-3 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider bg-gray-50/50">
                            Info
                        </div>
                        {infoCommands.map((command) => {
                            const element = renderCommand(command, currentIndex);
                            currentIndex++;
                            return element;
                        })}
                    </div>
                )}
            </div>

            {/* Footer hint */}
            <div className="px-3 py-2 border-t border-gray-100 bg-gray-50 text-[10px] text-gray-400">
                Press <kbd className="px-1 py-0.5 bg-white rounded border border-gray-200 mx-0.5">Esc</kbd> to close
            </div>
        </div>
    );
}
