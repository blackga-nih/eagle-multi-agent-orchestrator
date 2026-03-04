import {
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
    type LucideIcon,
} from 'lucide-react';

export interface SlashCommand {
    id: string;
    name: string;
    description: string;
    icon: LucideIcon;
    color: string;
    category: string;
}

export const slashCommands: SlashCommand[] = [
    // ── Documents ────────────────────────────────────────────────────
    {
        id: 'document:sow',
        name: '/document:SOW',
        description: 'Draft a Statement of Work',
        icon: FileText,
        color: 'purple',
        category: 'Documents',
    },
    {
        id: 'document:igce',
        name: '/document:IGCE',
        description: 'Draft an Independent Government Cost Estimate',
        icon: FileText,
        color: 'purple',
        category: 'Documents',
    },
    {
        id: 'document:ap',
        name: '/document:AP',
        description: 'Draft an Acquisition Plan',
        icon: FileText,
        color: 'purple',
        category: 'Documents',
    },
    {
        id: 'document:ja',
        name: '/document:J&A',
        description: 'Draft a Justification & Approval',
        icon: FileText,
        color: 'purple',
        category: 'Documents',
    },
    {
        id: 'document:mrr',
        name: '/document:MRR',
        description: 'Draft a Market Research Report',
        icon: FileText,
        color: 'purple',
        category: 'Documents',
    },

    // ── Compliance ───────────────────────────────────────────────────
    {
        id: 'compliance:far',
        name: '/compliance:FAR',
        description: 'Search FAR clauses',
        icon: ShieldCheck,
        color: 'green',
        category: 'Compliance',
    },
    {
        id: 'compliance:dfars',
        name: '/compliance:DFARS',
        description: 'Search DFARS clauses',
        icon: ShieldCheck,
        color: 'green',
        category: 'Compliance',
    },
    {
        id: 'compliance:clauses',
        name: '/compliance:clauses',
        description: 'Identify required clauses for an acquisition',
        icon: ShieldCheck,
        color: 'green',
        category: 'Compliance',
    },

    // ── Research ─────────────────────────────────────────────────────
    {
        id: 'research:policy',
        name: '/research:policy',
        description: 'Search NIH/HHS policies',
        icon: Search,
        color: 'cyan',
        category: 'Research',
    },
    {
        id: 'research:regulation',
        name: '/research:regulation',
        description: 'Look up federal regulations',
        icon: Search,
        color: 'cyan',
        category: 'Research',
    },
    {
        id: 'research:precedent',
        name: '/research:precedent',
        description: 'Find similar past acquisitions',
        icon: Search,
        color: 'cyan',
        category: 'Research',
    },

    // ── Workflow ─────────────────────────────────────────────────────
    {
        id: 'intake',
        name: '/intake',
        description: 'Start acquisition intake process',
        icon: ClipboardList,
        color: 'blue',
        category: 'Workflow',
    },
    {
        id: 'tech-review:specs',
        name: '/tech-review:specs',
        description: 'Review technical specifications',
        icon: Cpu,
        color: 'orange',
        category: 'Workflow',
    },
    {
        id: 'tech-review:508',
        name: '/tech-review:508',
        description: 'Check Section 508 compliance',
        icon: Accessibility,
        color: 'orange',
        category: 'Workflow',
    },
    {
        id: 'ingest',
        name: '/ingest',
        description: 'Upload and process a document',
        icon: Upload,
        color: 'indigo',
        category: 'Workflow',
    },

    // ── Admin ────────────────────────────────────────────────────────
    {
        id: 'admin:skills',
        name: '/admin:skills',
        description: 'List and manage custom skills',
        icon: Settings,
        color: 'rose',
        category: 'Admin',
    },
    {
        id: 'admin:prompts',
        name: '/admin:prompts',
        description: 'View and edit agent prompt overrides',
        icon: Settings,
        color: 'rose',
        category: 'Admin',
    },
    {
        id: 'admin:templates',
        name: '/admin:templates',
        description: 'View and edit document templates',
        icon: Settings,
        color: 'rose',
        category: 'Admin',
    },

    // ── Info ─────────────────────────────────────────────────────────
    {
        id: 'status',
        name: '/status',
        description: 'Check acquisition package status',
        icon: BarChart3,
        color: 'amber',
        category: 'Info',
    },
    {
        id: 'help',
        name: '/help',
        description: 'Show available commands and capabilities',
        icon: HelpCircle,
        color: 'gray',
        category: 'Info',
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
