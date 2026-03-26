import {
    Activity,
    ClipboardList,
    FileText,
    ShieldCheck,
    Search,
    Cpu,
    Upload,
    BarChart3,
    HelpCircle,
    Settings,
    Accessibility,
    MessageSquare,
    Grid3X3,
    ListChecks,
    Command,
    type LucideIcon,
} from 'lucide-react';

export interface SlashCommand {
    id: string;
    name: string;
    description: string;
    icon: LucideIcon;
    color: string;
    category: string;
    preview?: string;
    routesTo?: string | null;
    tier?: string;
    promptFile?: string | null;
}

/** Maps icon name strings (from command-registry.json) to Lucide components. */
export const iconMap: Record<string, LucideIcon> = {
    Activity,
    ClipboardList,
    FileText,
    ShieldCheck,
    Search,
    Cpu,
    Upload,
    BarChart3,
    HelpCircle,
    Settings,
    Accessibility,
    MessageSquare,
    Grid3X3,
    ListChecks,
    Command,
};

/** Fallback icon when the registry specifies an unknown icon name. */
const FALLBACK_ICON: LucideIcon = Command;

/**
 * Convert a raw command object from the backend API into a SlashCommand
 * with a resolved Lucide icon component.
 */
export function mapBackendCommand(raw: Record<string, unknown>): SlashCommand {
    return {
        id: raw.id as string,
        name: raw.command as string,
        description: raw.description as string,
        icon: iconMap[raw.icon as string] ?? FALLBACK_ICON,
        color: raw.color as string,
        category: raw.category as string,
        preview: (raw.preview as string) ?? undefined,
        routesTo: (raw.routesTo as string | null) ?? undefined,
        tier: (raw.tier as string) ?? 'basic',
        promptFile: (raw.promptFile as string | null) ?? undefined,
    };
}

/**
 * Minimal fallback commands shown when the backend is unreachable.
 * Covers the 4 core workflows so the picker is never empty.
 */
export const FALLBACK_COMMANDS: SlashCommand[] = [
    {
        id: 'intake',
        name: '/intake',
        description: 'Start acquisition intake process',
        icon: ClipboardList,
        color: 'blue',
        category: 'Workflow',
        preview: '/intake [description]\nExample: /intake I need to purchase a CT scanner for $500K',
    },
    {
        id: 'document:sow',
        name: '/document:SOW',
        description: 'Draft a Statement of Work',
        icon: FileText,
        color: 'purple',
        category: 'Documents',
        preview: '/document:SOW [title]\nExample: /document:SOW "CT Scanner Acquisition"',
    },
    {
        id: 'compliance:far',
        name: '/compliance:FAR',
        description: 'Search FAR clauses',
        icon: ShieldCheck,
        color: 'green',
        category: 'Compliance',
        preview: '/compliance:FAR <query>\nExample: /compliance:FAR sole source justification',
    },
    {
        id: 'status',
        name: '/status',
        description: 'Check acquisition package status',
        icon: BarChart3,
        color: 'amber',
        category: 'Info',
        preview: '/status [intake_id]\nExample: /status EAGLE-12345',
    },
];

export function filterCommands(commands: SlashCommand[], query: string): SlashCommand[] {
    const normalizedQuery = query.toLowerCase().replace(/^\//, '');

    if (!normalizedQuery) {
        return commands;
    }

    return commands.filter(
        (cmd) =>
            cmd.name.toLowerCase().includes(normalizedQuery) ||
            cmd.description.toLowerCase().includes(normalizedQuery) ||
            cmd.id.toLowerCase().includes(normalizedQuery)
    );
}

export function getCommandById(commands: SlashCommand[], id: string): SlashCommand | undefined {
    return commands.find((cmd) => cmd.id === id);
}

export function getCommandByName(commands: SlashCommand[], name: string): SlashCommand | undefined {
    const normalizedName = name.toLowerCase();
    return commands.find((cmd) => cmd.name.toLowerCase() === normalizedName);
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
    cyan: {
        bg: 'bg-cyan-50',
        text: 'text-cyan-600',
        border: 'border-cyan-200',
    },
    orange: {
        bg: 'bg-orange-50',
        text: 'text-orange-600',
        border: 'border-orange-200',
    },
    indigo: {
        bg: 'bg-indigo-50',
        text: 'text-indigo-600',
        border: 'border-indigo-200',
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
    rose: {
        bg: 'bg-rose-50',
        text: 'text-rose-600',
        border: 'border-rose-200',
    },
};
