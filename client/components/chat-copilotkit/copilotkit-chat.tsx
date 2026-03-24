'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { CopilotKit } from '@copilotkit/react-core';
import { CopilotChat } from '@copilotkit/react-ui';
import { useCopilotAction } from '@copilotkit/react-core';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';
import '@copilotkit/react-ui/styles.css';

import AGUIActivityLog, { type AGUILogEntry } from './agui-activity-log';
import InlineToolCards from './inline-tool-cards';

// ---------------------------------------------------------------------------
// SSE stream interceptor — tees the fetch response to capture AG-UI events
// ---------------------------------------------------------------------------

/**
 * Reads an SSE ReadableStream, parsing `data: {...}` lines into AG-UI events.
 * Calls `onEvent` for each parsed event.
 */
function readSSEStream(
    stream: ReadableStream<Uint8Array>,
    onEvent: (event: Record<string, unknown>) => void,
) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    function pump(): Promise<void> {
        return reader.read().then(({ done, value }) => {
            if (done) return;
            buffer += decoder.decode(value, { stream: true });

            // Split on double newline (SSE event boundary)
            const parts = buffer.split('\n\n');
            // Keep the last part (may be incomplete)
            buffer = parts.pop() ?? '';

            for (const part of parts) {
                for (const line of part.split('\n')) {
                    if (line.startsWith('data: ')) {
                        const json = line.slice(6).trim();
                        if (!json || json === '[DONE]') continue;
                        try {
                            const parsed = JSON.parse(json);
                            if (parsed && typeof parsed === 'object' && parsed.type) {
                                onEvent(parsed);
                            }
                        } catch {
                            // Not valid JSON — skip
                        }
                    }
                }
            }

            return pump();
        });
    }

    pump().catch(() => {});
}

/**
 * Patches `window.fetch` to intercept SSE responses from the CopilotKit
 * runtime URL, tees the stream, and forwards AG-UI events to the callback.
 *
 * Returns a cleanup function that restores the original fetch.
 */
function installFetchInterceptor(
    runtimeUrl: string,
    onEvent: (event: Record<string, unknown>) => void,
): () => void {
    const originalFetch = window.fetch.bind(window);

    window.fetch = async (input, init) => {
        const response = await originalFetch(input, init);

        // Only intercept SSE responses to our CopilotKit endpoint
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
        const isSSE = response.headers.get('content-type')?.includes('text/event-stream');

        if (url.includes(runtimeUrl) && isSSE && response.body) {
            const [forCopilotKit, forCapture] = response.body.tee();

            // Read the capture fork in background
            readSSEStream(forCapture, onEvent);

            // Return response with the CopilotKit fork
            return new Response(forCopilotKit, {
                status: response.status,
                statusText: response.statusText,
                headers: response.headers,
            });
        }

        return response;
    };

    return () => {
        window.fetch = originalFetch;
    };
}

// ---------------------------------------------------------------------------
// Inner chat component with CopilotKit actions
// ---------------------------------------------------------------------------

function EagleChatInner() {
    useCopilotAction({
        name: 'view_document',
        description: 'Display a generated acquisition document for the user to review',
        parameters: [
            {
                name: 'document_type',
                type: 'string',
                description: 'Type of document (sow, igce, acquisition_plan, justification)',
            },
            {
                name: 'title',
                type: 'string',
                description: 'Document title',
            },
            {
                name: 'content',
                type: 'string',
                description: 'Document content in markdown',
            },
        ],
        handler: async ({ document_type, title }) => {
            console.log(`[EAGLE] Document generated: ${document_type} — ${title}`);
            return `Document "${title}" displayed to user.`;
        },
        render: ({ args, status }) => {
            if (status === 'executing') {
                return (
                    <div className="my-2 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <div className="flex items-center gap-2">
                            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                            <span className="text-sm text-blue-700">
                                Generating {args.document_type?.toUpperCase()}...
                            </span>
                        </div>
                    </div>
                );
            }
            if (status === 'complete' && args.title) {
                return (
                    <div className="my-2 p-4 bg-white border border-[#D8DEE6] rounded-lg shadow-sm">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="text-green-600">&#10003;</span>
                            <span className="font-medium text-sm text-[#1A2332]">
                                {args.title}
                            </span>
                            <span className="text-xs px-2 py-0.5 bg-[#E8F5E9] text-[#2E7D32] rounded-full">
                                {args.document_type?.toUpperCase()}
                            </span>
                        </div>
                        {args.content && (
                            <details className="mt-2">
                                <summary className="text-xs text-[#5A6B7D] cursor-pointer hover:text-[#1A2332]">
                                    Preview content
                                </summary>
                                <pre className="mt-2 p-3 bg-[#F5F7FA] rounded text-xs overflow-x-auto max-h-60 whitespace-pre-wrap">
                                    {args.content?.slice(0, 2000)}
                                    {(args.content?.length ?? 0) > 2000 ? '\n...(truncated)' : ''}
                                </pre>
                            </details>
                        )}
                    </div>
                );
            }
            return <></>;
        },
    });

    return (
        <CopilotChat
            className="h-full"
            labels={{
                title: 'EAGLE Acquisition Assistant',
                initial: `Hi, I'm EAGLE \u2014 your NCI Acquisition Assistant.\n\nI can help you with FAR/DFARS guidance, document generation (SOW, IGCE, Acquisition Plans), intake processing, and compliance reviews.\n\nWhat are you working on today?`,
                placeholder: 'Ask about acquisitions, FAR/DFARS, or request documents...',
            }}
            instructions={`You are EAGLE, the NCI Acquisition Assistant. You help contracting officers with:
- Federal acquisition guidance (FAR, DFARS, HHS policies)
- Document generation (SOW, IGCE, Acquisition Plans, J&A)
- Intake processing for new acquisitions
- Compliance checking and review

Always be professional and reference specific FAR/DFARS clauses when applicable.
When generating documents, use the view_document action to display them.`}
            icons={{
                sendIcon: (
                    <span className="text-base">&#10148;</span>
                ),
            }}
        />
    );
}

// ---------------------------------------------------------------------------
// Main export — CopilotKit provider + fetch interceptor + activity panel
// ---------------------------------------------------------------------------

const RUNTIME_URL = '/api/copilotkit';

export default function CopilotKitChatInterface() {
    const [events, setEvents] = useState<AGUILogEntry[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [panelOpen, setPanelOpen] = useState(true);
    const eventCounter = useRef(0);

    const handleEvent = useCallback((raw: Record<string, unknown>) => {
        const entry: AGUILogEntry = {
            id: `agui-${++eventCounter.current}`,
            event: raw as AGUILogEntry['event'],
            receivedAt: new Date().toISOString(),
        };
        setEvents(prev => [...prev, entry]);

        // Track streaming state; clear tool events on new run
        if (raw.type === 'RUN_STARTED') {
            setIsStreaming(true);
            setEvents([entry]);
            return;
        }
        if (raw.type === 'RUN_FINISHED' || raw.type === 'RUN_ERROR') setIsStreaming(false);
    }, []);

    // Patch window.fetch to intercept SSE responses from CopilotKit runtime.
    // Uses bind(window) on the original to avoid infinite recursion.
    useEffect(() => {
        return installFetchInterceptor(RUNTIME_URL, handleEvent);
    }, [handleEvent]);

    const handleClear = useCallback(() => setEvents([]), []);

    return (
        <div className="h-full flex bg-[#F5F7FA]">
            {/* Chat panel */}
            <div className="flex-1 min-w-0 flex flex-col">
                <CopilotKit
                    runtimeUrl={RUNTIME_URL}
                    agent="eagle"
                    useSingleEndpoint={false}
                >
                    <div className="flex-1 min-h-0 flex flex-col">
                        <div className="flex-1 min-h-0">
                            <EagleChatInner />
                        </div>
                        <InlineToolCards events={events} />
                    </div>
                </CopilotKit>
            </div>

            {/* Activity panel */}
            {panelOpen ? (
                <div className="w-[340px] shrink-0 border-l border-[#D8DEE6] bg-white flex flex-col">
                    {/* Panel header */}
                    <div className="flex items-center justify-between px-3 py-2 bg-[#F5F7FA] border-b border-[#D8DEE6] shrink-0">
                        <span className="text-xs font-bold text-[#003366] uppercase tracking-wider">AG-UI Events</span>
                        <button
                            onClick={() => setPanelOpen(false)}
                            className="p-1 text-gray-400 hover:text-gray-600 rounded transition"
                            title="Collapse panel"
                        >
                            <PanelRightClose className="w-4 h-4" />
                        </button>
                    </div>
                    <div className="flex-1 min-h-0">
                        <AGUIActivityLog
                            events={events}
                            onClear={handleClear}
                            isStreaming={isStreaming}
                        />
                    </div>
                </div>
            ) : (
                <button
                    onClick={() => setPanelOpen(true)}
                    className="w-9 shrink-0 border-l border-[#D8DEE6] bg-[#F5F7FA] hover:bg-[#EDF0F4] transition flex flex-col items-center justify-center gap-1.5 cursor-pointer"
                    title="Open AG-UI event log"
                >
                    <PanelRightOpen className="w-4 h-4 text-gray-400" />
                    {events.length > 0 && (
                        <span className="px-1 py-0.5 rounded-full text-[8px] bg-[#003366] text-white font-bold min-w-[16px] text-center">
                            {events.length}
                        </span>
                    )}
                </button>
            )}
        </div>
    );
}
