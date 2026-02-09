'use client';

import { useState, useCallback, useEffect } from 'react';
import { filterCommands, SlashCommand } from '@/lib/slash-commands';

interface UseSlashCommandsOptions {
    onCommandSelect?: (command: SlashCommand) => void;
}

interface UseSlashCommandsReturn {
    isOpen: boolean;
    query: string;
    filteredCommands: SlashCommand[];
    selectedIndex: number;
    setIsOpen: (open: boolean) => void;
    handleInputChange: (value: string, cursorPosition: number) => void;
    handleKeyDown: (e: React.KeyboardEvent) => void;
    selectCommand: (command: SlashCommand) => void;
    closeCommandPicker: () => void;
}

export function useSlashCommands(options: UseSlashCommandsOptions = {}): UseSlashCommandsReturn {
    const { onCommandSelect } = options;

    const [isOpen, setIsOpen] = useState(false);
    const [query, setQuery] = useState('');
    const [selectedIndex, setSelectedIndex] = useState(0);
    const [filteredCommands, setFilteredCommands] = useState<SlashCommand[]>([]);

    // Update filtered commands when query changes
    useEffect(() => {
        const commands = filterCommands(query);
        setFilteredCommands(commands);
        setSelectedIndex(0);
    }, [query]);

    const handleInputChange = useCallback((value: string, cursorPosition: number) => {
        // Check if we should open the command picker
        // Look for "/" at the start or after a space
        const textBeforeCursor = value.slice(0, cursorPosition);
        const lastSlashIndex = textBeforeCursor.lastIndexOf('/');

        if (lastSlashIndex !== -1) {
            // Check if slash is at start or after whitespace
            const charBeforeSlash = lastSlashIndex > 0 ? value[lastSlashIndex - 1] : ' ';

            if (charBeforeSlash === ' ' || lastSlashIndex === 0) {
                const queryAfterSlash = textBeforeCursor.slice(lastSlashIndex + 1);

                // Only keep picker open if no space after the query
                if (!queryAfterSlash.includes(' ')) {
                    setIsOpen(true);
                    setQuery(queryAfterSlash);
                    return;
                }
            }
        }

        // Close picker if no valid slash command context
        setIsOpen(false);
        setQuery('');
    }, []);

    const selectCommand = useCallback((command: SlashCommand) => {
        onCommandSelect?.(command);
        setIsOpen(false);
        setQuery('');
        setSelectedIndex(0);
    }, [onCommandSelect]);

    const closeCommandPicker = useCallback(() => {
        setIsOpen(false);
        setQuery('');
        setSelectedIndex(0);
    }, []);

    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (!isOpen) return;

        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                setSelectedIndex((prev) =>
                    prev < filteredCommands.length - 1 ? prev + 1 : prev
                );
                break;
            case 'ArrowUp':
                e.preventDefault();
                setSelectedIndex((prev) => (prev > 0 ? prev - 1 : prev));
                break;
            case 'Enter':
                e.preventDefault();
                if (filteredCommands[selectedIndex]) {
                    selectCommand(filteredCommands[selectedIndex]);
                }
                break;
            case 'Escape':
                e.preventDefault();
                closeCommandPicker();
                break;
            case 'Tab':
                e.preventDefault();
                if (filteredCommands[selectedIndex]) {
                    selectCommand(filteredCommands[selectedIndex]);
                }
                break;
        }
    }, [isOpen, filteredCommands, selectedIndex, selectCommand, closeCommandPicker]);

    return {
        isOpen,
        query,
        filteredCommands,
        selectedIndex,
        setIsOpen,
        handleInputChange,
        handleKeyDown,
        selectCommand,
        closeCommandPicker,
    };
}
