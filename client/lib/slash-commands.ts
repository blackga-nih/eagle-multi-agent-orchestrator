import { Package, Search, FileText, HelpCircle, BarChart3, MessageSquare, type LucideIcon } from 'lucide-react';

export interface SlashCommand {
    id: string;
    name: string;
    description: string;
    icon: LucideIcon;
    color: string;
    category: 'actions' | 'info' | 'tools';
}

export const slashCommands: SlashCommand[] = [
    {
        id: 'acquisition-package',
        name: '/acquisition-package',
        description: 'Start a new acquisition package',
        icon: Package,
        color: 'blue',
        category: 'actions',
    },
    {
        id: 'research',
        name: '/research',
        description: 'Search regulations, policies, and knowledge base',
        icon: Search,
        color: 'green',
        category: 'actions',
    },
    {
        id: 'document',
        name: '/document',
        description: 'Generate procurement documents (SOW, IGCE, etc.)',
        icon: FileText,
        color: 'purple',
        category: 'actions',
    },
    {
        id: 'status',
        name: '/status',
        description: 'Check current acquisition package status',
        icon: BarChart3,
        color: 'amber',
        category: 'info',
    },
    {
        id: 'help',
        name: '/help',
        description: 'Show available commands and capabilities',
        icon: HelpCircle,
        color: 'gray',
        category: 'info',
    },
    {
        id: 'feedback',
        name: '/feedback',
        description: 'Send feedback — bug, suggestion, praise, or correction',
        icon: MessageSquare,
        color: 'red',
        category: 'info',
    },
];

export function filterCommands(query: string): SlashCommand[] {
    const normalizedQuery = query.toLowerCase().replace(/^\//, '');

    if (!normalizedQuery) {
        return slashCommands;
    }

    return slashCommands.filter(
        (cmd) =>
            cmd.name.toLowerCase().includes(normalizedQuery) ||
            cmd.description.toLowerCase().includes(normalizedQuery) ||
            cmd.id.toLowerCase().includes(normalizedQuery)
    );
}

export function getCommandById(id: string): SlashCommand | undefined {
    return slashCommands.find((cmd) => cmd.id === id);
}

export function getCommandByName(name: string): SlashCommand | undefined {
    const normalizedName = name.toLowerCase();
    return slashCommands.find((cmd) => cmd.name.toLowerCase() === normalizedName);
}

export const commandColorClasses: Record<string, { bg: string; text: string; border: string }> = {
    blue: {
        bg: 'bg-blue-50',
        text: 'text-blue-600',
        border: 'border-blue-200',
    },
    green: {
        bg: 'bg-green-50',
        text: 'text-green-600',
        border: 'border-green-200',
    },
    purple: {
        bg: 'bg-purple-50',
        text: 'text-purple-600',
        border: 'border-purple-200',
    },
    amber: {
        bg: 'bg-amber-50',
        text: 'text-amber-600',
        border: 'border-amber-200',
    },
    gray: {
        bg: 'bg-gray-50',
        text: 'text-gray-600',
        border: 'border-gray-200',
    },
    red: {
        bg: 'bg-red-50',
        text: 'text-red-600',
        border: 'border-red-200',
    },
};
