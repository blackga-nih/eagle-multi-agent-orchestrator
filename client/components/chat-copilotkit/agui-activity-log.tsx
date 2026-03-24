'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import {
    Play, Square, AlertTriangle, MessageSquare, Wrench,
    CheckSquare, Footprints, Brain, BarChart3, Zap,
    X, Copy, Check, ChevronUp, ChevronDown, Info,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// AG-UI Event Types
// ---------------------------------------------------------------------------

/** Raw AG-UI event as parsed from the SSE stream. */
export interface AGUIEvent {
    type: string;
    timestamp?: string | null;
    // Lifecycle
    run_id?: string;
    thread_id?: string;
    // Text messages
    message_id?: string;
    role?: string;
    delta?: string;
    // Tool calls
    tool_call_id?: string;
    tool_call_name?: string;
    parent_message_id?: string;
    result?: string;
    // Steps (subagent delegation)
    step_name?: string;
    // Custom events
    name?: string;
    value?: Record<string, unknown>;
    // Errors
    message?: string;
    // Raw passthrough
    [key: string]: unknown;
}

/** Captured log entry with a unique ID and arrival time. */
export interface AGUILogEntry {
    id: string;
    event: AGUIEvent;
    receivedAt: string;
}

// ---------------------------------------------------------------------------
// Badge config per AG-UI event type
// ---------------------------------------------------------------------------

interface BadgeConfig {
    label: string;
    bg: string;
    icon: typeof Play;
}

const BADGE_MAP: Record<string, BadgeConfig> = {
    RUN_STARTED:           { label: 'Run Started',     bg: 'bg-emerald-500',  icon: Play },
    RUN_FINISHED:          { label: 'Run Finished',    bg: 'bg-emerald-600',  icon: Square },
    RUN_ERROR:             { label: 'Error',           bg: 'bg-red-500',      icon: AlertTriangle },
    TEXT_MESSAGE_START:    { label: 'Msg Start',       bg: 'bg-blue-400',     icon: MessageSquare },
    TEXT_MESSAGE_CONTENT:  { label: 'Text',            bg: 'bg-blue-500',     icon: MessageSquare },
    TEXT_MESSAGE_END:      { label: 'Msg End',         bg: 'bg-blue-600',     icon: MessageSquare },
    TOOL_CALL_START:       { label: 'Tool Start',      bg: 'bg-yellow-500',   icon: Wrench },
    TOOL_CALL_ARGS:        { label: 'Tool Args',       bg: 'bg-yellow-500',   icon: Wrench },
    TOOL_CALL_END:         { label: 'Tool End',        bg: 'bg-yellow-600',   icon: Wrench },
    TOOL_CALL_RESULT:      { label: 'Tool Result',     bg: 'bg-orange-500',   icon: CheckSquare },
    STEP_STARTED:          { label: 'Step Started',    bg: 'bg-indigo-500',   icon: Footprints },
    STEP_FINISHED:         { label: 'Step Finished',   bg: 'bg-indigo-600',   icon: Footprints },
    CUSTOM:                { label: 'Custom',          bg: 'bg-purple-500',   icon: Zap },
};

function getBadge(type: string): BadgeConfig {
    return BADGE_MAP[type] ?? { label: type, bg: 'bg-gray-400', icon: Info };
}

/** Refine the label for custom events based on their name field. */
function getLabel(entry: AGUILogEntry): string {
    const { event } = entry;
    if (event.type === 'CUSTOM') {
        if (event.name === 'reasoning') return 'Reasoning';
        if (event.name === 'usage') return 'Usage';
        return event.name ?? 'Custom';
    }
    if (event.type === 'TOOL_CALL_START' && event.tool_call_name) {
        return event.tool_call_name;
    }
    if (event.type === 'STEP_STARTED' && event.step_name) {
        return event.step_name;
    }
    if (event.type === 'STEP_FINISHED' && event.step_name) {
        return `${event.step_name} done`;
    }
    return getBadge(event.type).label;
}

function getCustomIcon(entry: AGUILogEntry) {
    if (entry.event.type === 'CUSTOM' && entry.event.name === 'reasoning') return Brain;
    if (entry.event.type === 'CUSTOM' && entry.event.name === 'usage') return BarChart3;
    return getBadge(entry.event.type).icon;
}

// ---------------------------------------------------------------------------
// Collapsed text delta grouping
// ---------------------------------------------------------------------------

interface DisplayEntry {
    entries: AGUILogEntry[];
    label: string;
    type: string;
    icon: typeof Play;
    bg: string;
    preview: string;
}

function buildDisplayEntries(logs: AGUILogEntry[]): DisplayEntry[] {
    const result: DisplayEntry[] = [];
    let textBuffer: AGUILogEntry[] = [];

    function flushText() {
        if (textBuffer.length === 0) return;
        const merged = textBuffer.map(e => e.event.delta ?? '').join('');
        result.push({
            entries: [...textBuffer],
            label: `Text (${textBuffer.length} chunks)`,
            type: 'TEXT_MESSAGE_CONTENT',
            icon: MessageSquare,
            bg: 'bg-blue-500',
            preview: merged.length > 120 ? merged.slice(0, 120) + '...' : merged,
        });
        textBuffer = [];
    }

    for (const entry of logs) {
        if (entry.event.type === 'TEXT_MESSAGE_CONTENT') {
            textBuffer.push(entry);
            continue;
        }
        flushText();

        const badge = getBadge(entry.event.type);
        const label = getLabel(entry);
        const Icon = getCustomIcon(entry);
        let preview = '';

        if (entry.event.type === 'TOOL_CALL_ARGS') {
            preview = entry.event.delta?.slice(0, 100) ?? '';
        } else if (entry.event.type === 'TOOL_CALL_RESULT') {
            preview = entry.event.result?.slice(0, 100) ?? '';
        } else if (entry.event.type === 'RUN_ERROR') {
            preview = entry.event.message ?? '';
        } else if (entry.event.type === 'CUSTOM' && entry.event.name === 'reasoning') {
            const text = (entry.event.value as Record<string, string>)?.text ?? '';
            preview = text.slice(0, 100);
        } else if (entry.event.type === 'CUSTOM' && entry.event.name === 'usage') {
            const val = entry.event.value as Record<string, unknown>;
            const usage = val?.usage as Record<string, number> | undefined;
            if (usage) {
                preview = `${(usage.input_tokens ?? 0).toLocaleString()} in / ${(usage.output_tokens ?? 0).toLocaleString()} out`;
            }
            const tools = val?.tools_called as string[] | undefined;
            if (tools?.length) preview += ` · ${tools.length} tool${tools.length !== 1 ? 's' : ''}`;
        }

        result.push({
            entries: [entry],
            label,
            type: entry.event.type,
            icon: Icon,
            bg: badge.bg,
            preview,
        });
    }
    flushText();
    return result;
}

// ---------------------------------------------------------------------------
// Detail Modal
// ---------------------------------------------------------------------------

function DetailModal({
    display,
    allDisplay,
    index,
    onClose,
}: {
    display: DisplayEntry;
    allDisplay: DisplayEntry[];
    index: number;
    onClose: () => void;
}) {
    const [activeIndex, setActiveIndex] = useState(index);
    const [showRaw, setShowRaw] = useState(false);
    const [copied, setCopied] = useState(false);

    const active = allDisplay[activeIndex];

    useEffect(() => {
        const handle = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
            if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIndex(i => Math.max(0, i - 1)); }
            if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIndex(i => Math.min(allDisplay.length - 1, i + 1)); }
        };
        window.addEventListener('keydown', handle);
        return () => window.removeEventListener('keydown', handle);
    }, [onClose, allDisplay.length]);

    const handleCopy = async () => {
        const payload = active.entries.length > 1 ? active.entries.map(e => e.event) : active.entries[0].event;
        await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
            <div
                className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[78vh] flex flex-col overflow-hidden"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className={`px-4 py-3 border-b flex items-center justify-between shrink-0 ${active.bg.replace('bg-', 'bg-')}/10`}>
                    <div className="flex items-center gap-2">
                        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-white ${active.bg}`}>
                            <active.icon className="w-3 h-3" />
                        </span>
                        <span className="text-sm font-bold text-gray-800">{active.label}</span>
                        <span className="text-xs text-gray-400 font-mono">
                            {active.entries[0].receivedAt ? new Date(active.entries[0].receivedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                        </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <button onClick={() => setActiveIndex(i => Math.max(0, i - 1))} disabled={activeIndex === 0} className="p-1 hover:bg-black/10 rounded disabled:opacity-30">
                            <ChevronUp className="w-4 h-4" />
                        </button>
                        <span className="text-[11px] text-gray-500 font-mono min-w-[3rem] text-center">{activeIndex + 1}/{allDisplay.length}</span>
                        <button onClick={() => setActiveIndex(i => Math.min(allDisplay.length - 1, i + 1))} disabled={activeIndex === allDisplay.length - 1} className="p-1 hover:bg-black/10 rounded disabled:opacity-30">
                            <ChevronDown className="w-4 h-4" />
                        </button>
                        <button onClick={onClose} className="ml-1 p-1 hover:bg-black/10 rounded">
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                </div>

                {/* Action bar */}
                <div className="flex items-center justify-end gap-2 px-4 py-2 border-b shrink-0">
                    <button onClick={handleCopy} className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-lg">
                        {copied ? <Check className="w-3 h-3 text-green-600" /> : <Copy className="w-3 h-3" />}
                        {copied ? 'Copied!' : 'Copy JSON'}
                    </button>
                    <button
                        onClick={() => setShowRaw(!showRaw)}
                        className={`flex items-center gap-1 px-2 py-1 text-xs rounded-lg ${showRaw ? 'bg-[#003366] text-white' : 'bg-gray-100 hover:bg-gray-200'}`}
                    >
                        <Info className="w-3 h-3" />
                        {showRaw ? 'Formatted' : 'Raw JSON'}
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-4">
                    {showRaw ? (
                        <pre className="bg-gray-900 text-green-400 p-4 rounded-xl text-xs overflow-x-auto font-mono whitespace-pre-wrap">
                            {JSON.stringify(active.entries.length > 1 ? active.entries.map(e => e.event) : active.entries[0].event, null, 2)}
                        </pre>
                    ) : (
                        <div className="space-y-3">
                            {active.preview && (
                                <div className="bg-gray-50 p-4 rounded-xl text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                                    {active.preview}
                                </div>
                            )}
                            {active.entries.length > 1 && (
                                <p className="text-xs text-gray-400">{active.entries.length} events grouped</p>
                            )}
                            <div className="pt-3 border-t border-gray-100 text-[10px] text-gray-400 font-mono">
                                {active.entries[0].id} · {active.type}
                                {active.entries[0].event.run_id && ` · run:${active.entries[0].event.run_id.slice(0, 8)}`}
                                {active.entries[0].event.tool_call_id && ` · tc:${active.entries[0].event.tool_call_id.slice(0, 8)}`}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

interface AGUIActivityLogProps {
    events: AGUILogEntry[];
    onClear: () => void;
    isStreaming: boolean;
}

export default function AGUIActivityLog({ events, onClear, isStreaming }: AGUIActivityLogProps) {
    const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);

    const displayEntries = useMemo(() => buildDisplayEntries(events), [events]);

    // Auto-scroll to bottom
    useEffect(() => {
        const el = scrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
    }, [displayEntries.length]);

    // Summary counts
    const counts = useMemo(() => {
        const c = { tool: 0, step: 0, text: 0, error: 0, custom: 0 };
        for (const e of events) {
            const t = e.event.type;
            if (t === 'TOOL_CALL_START') c.tool++;
            else if (t === 'STEP_STARTED') c.step++;
            else if (t === 'TEXT_MESSAGE_CONTENT') c.text++;
            else if (t === 'RUN_ERROR') c.error++;
            else if (t === 'CUSTOM') c.custom++;
        }
        return c;
    }, [events]);

    if (events.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
                    <Zap className="w-5 h-5 text-gray-400" />
                </div>
                <p className="text-sm text-gray-500">No AG-UI events yet.</p>
                <p className="text-xs text-gray-400 mt-1">Events will stream here as the agent runs.</p>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full">
            {/* Summary bar */}
            <div className="flex items-center gap-2 px-3 py-2 border-b border-[#D8DEE6] shrink-0 flex-wrap">
                <span className="text-[10px] text-gray-400 font-medium uppercase tracking-wider">
                    {events.length} event{events.length !== 1 ? 's' : ''}
                    {isStreaming && <span className="ml-2 inline-block w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />}
                </span>
                {counts.step > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-indigo-100 text-indigo-700">{counts.step} subagent{counts.step !== 1 ? 's' : ''}</span>
                )}
                {counts.tool > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-yellow-100 text-yellow-800">{counts.tool} tool{counts.tool !== 1 ? 's' : ''}</span>
                )}
                {counts.error > 0 && (
                    <span className="px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-red-100 text-red-700">{counts.error} error{counts.error !== 1 ? 's' : ''}</span>
                )}
                <button onClick={onClear} className="ml-auto text-[10px] text-red-500 hover:text-red-700 font-medium">
                    Clear
                </button>
            </div>

            {/* Badge grid */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto p-3">
                <div className="flex flex-wrap gap-1">
                    {displayEntries.map((display, i) => {
                        const Icon = display.icon;
                        const tooltip = `${display.label}\n${display.preview || display.type}`;
                        return (
                            <button
                                key={display.entries[0].id + '-' + i}
                                type="button"
                                onClick={() => setSelectedIndex(i)}
                                title={tooltip}
                                className={`w-7 h-7 rounded-full flex items-center justify-center text-white transition-transform hover:scale-125 hover:shadow-lg shrink-0 ${display.bg}`}
                            >
                                <Icon className="w-3.5 h-3.5" />
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Detail modal */}
            {selectedIndex !== null && displayEntries[selectedIndex] && (
                <DetailModal
                    display={displayEntries[selectedIndex]}
                    allDisplay={displayEntries}
                    index={selectedIndex}
                    onClose={() => setSelectedIndex(null)}
                />
            )}
        </div>
    );
}
