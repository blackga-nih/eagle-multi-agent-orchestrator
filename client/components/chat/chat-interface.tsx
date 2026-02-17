'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Send, Mic, MicOff, History, ClipboardList, DollarSign, Calendar, Wifi, WifiOff, Activity, Upload } from 'lucide-react';
import MessageList from './message-list';
import MultiAgentLogs from './multi-agent-logs';
import DocumentChecklist from '../checklist/document-checklist';
import DocumentUpload from '../documents/document-upload';
import AcquisitionCard from '../summary/acquisition-card';
import SuggestedPrompts from './suggested-prompts';
import SlashCommandPicker from './slash-command-picker';
import { useAgentStream, checkBackendHealth } from '@/hooks/use-agent-stream';
import { useSlashCommands } from '@/hooks/use-slash-commands';
import { useSession } from '@/contexts/session-context';
import { useAuth } from '@/contexts/auth-context';
import { SlashCommand } from '@/lib/slash-commands';
import { Message as StreamMessage, AuditLogEntry } from '@/types/stream';
import {
    PAST_WORKFLOWS,
    MOCK_AUDIT_LOGS,
    getWorkflowStatusColor,
    getAcquisitionTypeLabel,
    formatCurrency,
    formatDate,
    formatTime,
} from '@/lib/mock-data';
import type { ChatMessage } from '@/types/chat';

// Re-export shared types so existing imports from this file keep working.
export type { ChatMessage, DocumentInfo } from '@/types/chat';
export type Message = ChatMessage;

export interface AcquisitionData {
    requirement?: string;
    estimatedValue?: string;
    estimatedCost?: string;
    timeline?: string;
    urgency?: string;
    funding?: string;
    equipmentType?: string;
    acquisitionType?: string;
}

type TabType = 'current' | 'history' | 'logs';

// Track submitted forms to keep them visible but frozen
interface SubmittedForm {
    type: 'initial' | 'equipment' | 'funding';
    data: any;
    timestamp: Date;
}

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [acquisitionData, setAcquisitionData] = useState<AcquisitionData>({});
    const [activeForm, setActiveForm] = useState<'initial' | 'equipment' | 'funding' | null>(null);
    const [submittedForms, setSubmittedForms] = useState<SubmittedForm[]>([]);
    const [isRecording, setIsRecording] = useState(false);
    const [recognition, setRecognition] = useState<any>(null);
    const [activeTab, setActiveTab] = useState<TabType>('current');
    const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
    const [isLoadingSession, setIsLoadingSession] = useState(true);
    const [uploadedDocuments, setUploadedDocuments] = useState<string[]>([]);

    // Use session context for persistence
    const { currentSessionId, saveSession, loadSession } = useSession();
    const { getToken } = useAuth();

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Load session data when session changes
    useEffect(() => {
        if (!currentSessionId) {
            setIsLoadingSession(false);
            return;
        }

        const sessionData = loadSession(currentSessionId);
        if (sessionData) {
            setMessages(sessionData.messages);
            setAcquisitionData(sessionData.acquisitionData);
        } else {
            // New session, reset state
            setMessages([]);
            setAcquisitionData({});
            setSubmittedForms([]);
            setActiveForm(null);
        }
        setIsLoadingSession(false);
    }, [currentSessionId, loadSession]);

    // Auto-save session when messages or acquisition data change
    const saveSessionDebounced = useCallback(() => {
        if (messages.length > 0 || Object.keys(acquisitionData).length > 0) {
            saveSession(messages, acquisitionData);
        }
    }, [messages, acquisitionData, saveSession]);

    useEffect(() => {
        // Debounce saves to avoid too many writes
        const timeoutId = setTimeout(saveSessionDebounced, 500);
        return () => clearTimeout(timeoutId);
    }, [saveSessionDebounced]);

    // Handle slash command selection
    const handleCommandSelect = (command: SlashCommand) => {
        // Check if this is the acquisition package command
        if (command.id === 'acquisition-package') {
            // Show the intake form instead of inserting command
            setActiveForm('initial');
            setInput('');
            return;
        }
        setInput(command.name + ' ');
        inputRef.current?.focus();
    };

    // Slash commands hook
    const {
        isOpen: isCommandPickerOpen,
        filteredCommands,
        selectedIndex,
        handleInputChange: handleSlashInputChange,
        handleKeyDown: handleSlashKeyDown,
        selectCommand,
        closeCommandPicker,
    } = useSlashCommands({
        onCommandSelect: handleCommandSelect,
    });

    // Use the agent stream hook
    const { sendQuery, isStreaming, logs, lastMessage, clearLogs, error, addUserInputLog, addFormSubmitLog } = useAgentStream({
        getToken,
        onMessage: (msg) => {
            // Add assistant message to chat
            const newMessage: Message = {
                id: msg.id,
                role: 'assistant',
                content: msg.content,
                timestamp: msg.timestamp,
                reasoning: msg.reasoning,
                agent_id: msg.agent_id,
                agent_name: msg.agent_name,
            };
            setMessages(prev => [...prev, newMessage]);

            // Parse acquisition data from the response
            parseAcquisitionData(msg.content);
        },
        onComplete: () => {
            // Stream complete
        },
        onError: (err) => {
            console.error('Stream error:', err);
        },
    });

    // Check backend health on mount
    useEffect(() => {
        checkBackendHealth().then(setBackendConnected);

        // Recheck every 30 seconds
        const interval = setInterval(() => {
            checkBackendHealth().then(setBackendConnected);
        }, 30000);

        return () => clearInterval(interval);
    }, []);

    // Speech recognition setup
    useEffect(() => {
        if (typeof window !== 'undefined') {
            const SpeechRecognition = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition;
            if (SpeechRecognition) {
                const recognitionInstance = new SpeechRecognition();
                recognitionInstance.continuous = true;
                recognitionInstance.interimResults = true;
                recognitionInstance.lang = 'en-US';

                recognitionInstance.onresult = (event: any) => {
                    let transcript = '';
                    for (let i = event.resultIndex; i < event.results.length; i++) {
                        if (event.results[i].isFinal) {
                            transcript += event.results[i][0].transcript + ' ';
                        }
                    }
                    if (transcript) {
                        setInput((prev) => prev + transcript);
                    }
                };

                recognitionInstance.onerror = () => setIsRecording(false);
                recognitionInstance.onend = () => setIsRecording(false);
                setRecognition(recognitionInstance);
            }
        }
    }, []);

    // Auto-scroll to bottom
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const toggleRecording = () => {
        if (!recognition) {
            alert('Speech recognition not supported. Please use Chrome or Edge.');
            return;
        }
        if (isRecording) {
            recognition.stop();
        } else {
            recognition.start();
            setIsRecording(true);
        }
    };

    // Parse acquisition data from agent responses
    const parseAcquisitionData = (content: string) => {
        // Look for acquisition type
        const typeMatch = content.match(/Acquisition Type:\s*\*?\*?([^*\n]+)/i);
        if (typeMatch) {
            setAcquisitionData(prev => ({ ...prev, acquisitionType: typeMatch[1].trim() }));
        }

        // Look for estimated value
        const valueMatch = content.match(/Estimated Value:\s*\*?\*?([^*\n]+)/i);
        if (valueMatch) {
            setAcquisitionData(prev => ({ ...prev, estimatedValue: valueMatch[1].trim() }));
        }

        // Look for timeline
        const timelineMatch = content.match(/Timeline:\s*\*?\*?([^*\n]+)/i);
        if (timelineMatch) {
            setAcquisitionData(prev => ({ ...prev, timeline: timelineMatch[1].trim() }));
        }
    };

    const handleInitialIntakeSubmit = async (data: any) => {
        setAcquisitionData((prev) => ({ ...prev, ...data }));

        // Mark form as submitted (freeze it) instead of removing
        setSubmittedForms(prev => [...prev, { type: 'initial', data, timestamp: new Date() }]);
        setActiveForm(null);

        // Log form submission to agent logs
        const summary = `Requirement: ${data.requirement?.slice(0, 50)}${data.requirement?.length > 50 ? '...' : ''}, Cost: ${data.estimatedCost}, Timeline: ${data.timeline}`;
        addFormSubmitLog('Initial Intake', data, summary);

        // Add user message
        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: data.requirement,
            timestamp: new Date(),
        };
        setMessages([userMsg]);

        // Log user input
        addUserInputLog(data.requirement);

        // Send to backend
        if (backendConnected) {
            await sendQuery(data.requirement, currentSessionId);
        } else {
            // Fallback to mock response if backend not available
            setTimeout(() => {
                const mockResponse: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: `I can see you need **${data.requirement}**. Let me help you with this acquisition.\n\n(Backend not connected - showing mock response)`,
                    timestamp: new Date(),
                    reasoning: "Backend offline - using mock response",
                    agent_id: 'oa-intake',
                    agent_name: 'OA Intake Agent',
                };
                setMessages(prev => [...prev, mockResponse]);
            }, 1000);
        }
    };

    const handleEquipmentSubmit = async (data: any) => {
        setAcquisitionData((prev) => ({ ...prev, ...data }));

        // Mark form as submitted (freeze it)
        setSubmittedForms(prev => [...prev, { type: 'equipment', data, timestamp: new Date() }]);
        setActiveForm(null);

        const messageContent = `Equipment: ${data.equipmentType || 'CT Scanner'}, ${data.sliceCount}, ${data.condition}`;

        // Log form submission to agent logs
        const summary = `${data.equipmentType || 'CT Scanner'}, ${data.sliceCount}, ${data.condition} condition`;
        addFormSubmitLog('Equipment Details', data, summary);

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: messageContent,
            timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userMsg]);

        // Log user input
        addUserInputLog(messageContent);

        // Send to backend
        if (backendConnected) {
            await sendQuery(`Equipment specifications: ${data.equipmentType || 'CT Scanner'}, ${data.sliceCount} slices, ${data.condition} condition`, currentSessionId);
        }
    };

    const handleFundingSubmit = async (data: any) => {
        setAcquisitionData((prev) => ({ ...prev, ...data }));

        // Mark form as submitted (freeze it)
        setSubmittedForms(prev => [...prev, { type: 'funding', data, timestamp: new Date() }]);
        setActiveForm(null);

        const messageContent = `Funding: ${data.fundingSource}, Urgency: ${data.urgencyReason || 'Standard'}`;

        // Log form submission to agent logs
        const summary = `Source: ${data.fundingSource}, Urgency: ${data.urgencyReason || 'Standard'}`;
        addFormSubmitLog('Funding Details', data, summary);

        const userMsg: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: messageContent,
            timestamp: new Date(),
        };
        setMessages((prev) => [...prev, userMsg]);

        // Log user input
        addUserInputLog(messageContent);

        // Send to backend
        if (backendConnected) {
            await sendQuery(`Funding source: ${data.fundingSource}, Urgency: ${data.urgencyReason || 'Standard'}`, currentSessionId);
        }
    };

    const handleSend = async () => {
        if (!input.trim()) return;
        if (isRecording) recognition?.stop();

        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: input,
            timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMessage]);
        const query = input;
        setInput('');

        // Log user input to agent logs
        addUserInputLog(query);

        // Send to backend
        if (backendConnected) {
            await sendQuery(query, currentSessionId);
        }
    };

    const handleSuggestedPromptSelect = (prompt: string) => {
        // Check if this is the acquisition package command
        if (prompt === '/acquisition-package') {
            // Show the intake form instead of sending to chat
            setActiveForm('initial');
            return;
        }
        // Insert the prompt into the input field
        setInput(prompt);
    };

    // Handle document upload
    const handleDocumentUpload = async (file: File): Promise<{ success: boolean; error?: string }> => {
        try {
            // In a full implementation, this would upload to S3 or backend
            // For now, we'll simulate a successful upload
            console.log('Uploading document:', file.name);

            // Store the document reference
            setUploadedDocuments(prev => [...prev, file.name]);

            // Log to agent logs
            addFormSubmitLog('Document Upload', { fileName: file.name, size: file.size }, `Uploaded: ${file.name}`);

            // Simulate upload delay
            await new Promise(resolve => setTimeout(resolve, 1000));

            return { success: true };
        } catch (error) {
            console.error('Upload error:', error);
            return { success: false, error: 'Failed to upload document' };
        }
    };

    const handleDocumentRemove = (documentId: string) => {
        // In a full implementation, this would delete from storage
        console.log('Removing document:', documentId);
    };

    // Handle actions from welcome message capability cards
    const handleWelcomeAction = (action: string) => {
        switch (action) {
            case 'acquisition-package':
                setActiveForm('initial');
                break;
            case 'research':
                setInput('/research ');
                inputRef.current?.focus();
                break;
            case 'document':
                setInput('/document ');
                inputRef.current?.focus();
                break;
            case 'compliance':
                setInput('I need help with FAR/DFAR compliance for my acquisition.');
                inputRef.current?.focus();
                break;
            default:
                break;
        }
    };

    return (
        <div className="h-full flex flex-col lg:flex-row bg-gray-50 overflow-hidden">
            <div className="flex-1 flex flex-col">
                {/* Minimal header with status indicators only */}
                <header className="bg-white border-b border-gray-200 px-6 py-3 z-10">
                    <div className="flex justify-between items-center">
                        <div>
                            <h1 className="text-lg font-semibold text-gray-900">EAGLE Chat</h1>
                            <p className="text-xs text-gray-500">Office of Acquisitions - AI Assistant</p>
                        </div>
                        <div className="flex items-center gap-3">
                            {/* Backend Status */}
                            <div className={`text-xs px-3 py-1.5 rounded-full border flex items-center gap-2 ${
                                backendConnected === null
                                    ? 'bg-gray-100 border-gray-200 text-gray-600'
                                    : backendConnected
                                        ? 'bg-green-50 border-green-200 text-green-700'
                                        : 'bg-red-50 border-red-200 text-red-700'
                            }`}>
                                {backendConnected === null ? (
                                    <>
                                        <Activity className="w-3 h-3 animate-pulse" />
                                        Connecting...
                                    </>
                                ) : backendConnected ? (
                                    <>
                                        <Wifi className="w-3 h-3" />
                                        Multi-Agent Online
                                    </>
                                ) : (
                                    <>
                                        <WifiOff className="w-3 h-3" />
                                        Backend Offline
                                    </>
                                )}
                            </div>
                            <div className={`text-xs px-3 py-1.5 rounded-full border flex items-center gap-2 ${
                                isStreaming
                                    ? 'bg-yellow-50 border-yellow-200 text-yellow-700'
                                    : 'bg-blue-50 border-blue-200 text-blue-700'
                            }`}>
                                <div className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-yellow-500 animate-pulse' : 'bg-green-500'}`}></div>
                                {isStreaming ? 'Streaming...' : 'Ready'}
                            </div>
                        </div>
                    </div>
                </header>

                <div className="flex-1 overflow-hidden relative">
                    <MessageList
                        messages={messages}
                        isTyping={isStreaming}
                        activeForm={activeForm}
                        onInitialIntakeSubmit={handleInitialIntakeSubmit}
                        onEquipmentSubmit={handleEquipmentSubmit}
                        onFundingSubmit={handleFundingSubmit}
                        onFormDismiss={() => setActiveForm(null)}
                        onSuggestedPromptSelect={handleSuggestedPromptSelect}
                        showWelcome={messages.length === 0}
                    />
                    <div ref={messagesEndRef} />
                </div>

                <div className="border-t bg-white p-6 shadow-[0_-4px_20px_rgba(0,0,0,0.03)]">
                    <div className="container mx-auto max-w-4xl">
                        {error && (
                            <div className="mb-3 px-4 py-2 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                                {error}
                            </div>
                        )}
                        {/* Compact suggested prompts when there are messages */}
                        {messages.length > 0 && (
                            <div className="mb-3 flex items-center justify-between">
                                <span className="text-xs text-gray-400">Quick actions:</span>
                                <SuggestedPrompts onSelect={handleSuggestedPromptSelect} compact={true} />
                            </div>
                        )}
                        <div className="flex gap-3">
                            <button
                                onClick={toggleRecording}
                                className={`p-3 rounded-xl transition-all ${isRecording
                                    ? 'bg-red-500 text-white shadow-lg shadow-red-200 animate-pulse'
                                    : 'bg-gray-100 text-gray-500 hover:bg-blue-50 hover:text-blue-600'
                                    }`}
                                title={isRecording ? 'Stop Recording' : 'Start Voice Input'}
                            >
                                {isRecording ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                            </button>
                            <div className="flex-1 relative">
                                {/* Slash Command Picker */}
                                {isCommandPickerOpen && (
                                    <SlashCommandPicker
                                        commands={filteredCommands}
                                        selectedIndex={selectedIndex}
                                        onSelect={selectCommand}
                                        onClose={closeCommandPicker}
                                    />
                                )}
                                <input
                                    ref={inputRef}
                                    type="text"
                                    value={input}
                                    onChange={(e) => {
                                        setInput(e.target.value);
                                        handleSlashInputChange(e.target.value, e.target.selectionStart || 0);
                                    }}
                                    onKeyDown={(e) => {
                                        // Handle slash commands first
                                        if (isCommandPickerOpen) {
                                            handleSlashKeyDown(e);
                                            if (['ArrowUp', 'ArrowDown', 'Enter', 'Escape', 'Tab'].includes(e.key)) {
                                                return;
                                            }
                                        }
                                        // Then handle send on Enter
                                        if (e.key === 'Enter' && !isStreaming && !isCommandPickerOpen) {
                                            handleSend();
                                        }
                                    }}
                                    placeholder={isRecording ? 'Listening...' : isStreaming ? 'Waiting for response...' : 'Message EAGLE... (type / for commands)'}
                                    disabled={isStreaming}
                                    className={`w-full px-5 py-3.5 bg-gray-50 border border-gray-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-nci-blue/20 focus:border-nci-blue transition-all text-sm ${isRecording ? 'bg-red-50/50 border-red-100' : ''} ${isStreaming ? 'opacity-50' : ''}`}
                                />
                                <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
                                    <button
                                        onClick={handleSend}
                                        disabled={!input.trim() || isStreaming}
                                        className="p-2 bg-nci-blue text-white rounded-xl hover:bg-nci-blue-light disabled:opacity-30 disabled:grayscale transition-all shadow-md shadow-blue-200"
                                    >
                                        <Send className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <aside className="lg:w-[450px] border-l border-gray-200 bg-white flex flex-col shadow-[-10px_0_30px_rgba(0,0,0,0.02)]">
                {/* Tab Navigation */}
                <div className="flex border-b border-gray-100 px-2 py-2 gap-1 bg-gray-50/50">
                    <button
                        onClick={() => setActiveTab('current')}
                        className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${activeTab === 'current' ? 'bg-white text-blue-600 shadow-sm border border-gray-100' : 'text-gray-500 hover:bg-white hover:text-gray-700'}`}
                    >
                        <ClipboardList className="w-4 h-4" />
                        Active Intake
                    </button>
                    <button
                        onClick={() => setActiveTab('history')}
                        className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${activeTab === 'history' ? 'bg-white text-blue-600 shadow-sm border border-gray-100' : 'text-gray-500 hover:bg-white hover:text-gray-700'}`}
                    >
                        <History className="w-4 h-4" />
                        Order History
                    </button>
                    <button
                        onClick={() => setActiveTab('logs')}
                        className={`flex-1 flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl text-xs font-semibold transition-all ${activeTab === 'logs' ? 'bg-white text-blue-600 shadow-sm border border-gray-100' : 'text-gray-500 hover:bg-white hover:text-gray-700'}`}
                    >
                        <Activity className="w-4 h-4" />
                        Agent Logs
                        {logs.length > 0 && (
                            <span className="ml-1 px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded-full text-[9px]">
                                {logs.length}
                            </span>
                        )}
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
                    {activeTab === 'current' && (
                        <>
                            <AcquisitionCard data={acquisitionData} />
                            <DocumentChecklist messages={messages} data={acquisitionData} />

                            {/* Document Upload Section */}
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <h3 className="font-bold text-gray-900 flex items-center gap-2">
                                        <Upload className="w-5 h-5 text-blue-600" />
                                        Upload Documents
                                    </h3>
                                    {uploadedDocuments.length > 0 && (
                                        <span className="text-[10px] bg-green-100 text-green-600 px-2 py-1 rounded-md">
                                            {uploadedDocuments.length} uploaded
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-gray-500">
                                    Add supporting documents to your acquisition package
                                </p>
                                <DocumentUpload
                                    onUpload={handleDocumentUpload}
                                    onRemove={handleDocumentRemove}
                                    maxSizeMB={10}
                                />
                            </div>
                        </>
                    )}

                    {activeTab === 'history' && (
                        <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
                            <div className="flex items-center justify-between mb-2">
                                <h3 className="font-bold text-gray-900 flex items-center gap-2">
                                    <History className="w-5 h-5 text-blue-600" />
                                    Past Acquisitions
                                </h3>
                                <span className="text-[10px] bg-gray-100 text-gray-500 px-2 py-1 rounded-md">{PAST_WORKFLOWS.length} Records</span>
                            </div>
                            <div className="space-y-4">
                                {PAST_WORKFLOWS.map((workflow) => (
                                    <div key={workflow.id} className="p-4 bg-gray-50 border border-gray-100 rounded-2xl hover:border-blue-200 transition-colors cursor-pointer group">
                                        <div className="flex justify-between items-start mb-2">
                                            <h4 className="font-semibold text-sm text-gray-900 group-hover:text-blue-600 transition-colors">{workflow.title}</h4>
                                            <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${getWorkflowStatusColor(workflow.status)}`}>
                                                {workflow.status.replace('_', ' ')}
                                            </span>
                                        </div>
                                        <p className="text-[11px] text-gray-500 mb-2 line-clamp-1">{workflow.description}</p>
                                        <div className="flex flex-wrap gap-3 text-[11px] text-gray-500">
                                            <span className="flex items-center gap-1">
                                                <Calendar className="w-3 h-3" />
                                                {workflow.completed_at ? formatDate(workflow.completed_at) : formatDate(workflow.updated_at)}
                                            </span>
                                            <span className="flex items-center gap-1 font-medium text-gray-700">
                                                <DollarSign className="w-3 h-3" />
                                                {workflow.estimated_value ? formatCurrency(workflow.estimated_value) : 'TBD'}
                                            </span>
                                            {workflow.acquisition_type && (
                                                <span className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded">
                                                    {getAcquisitionTypeLabel(workflow.acquisition_type)}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {activeTab === 'logs' && (
                        <div className="space-y-4 animate-in slide-in-from-right-4 duration-300">
                            <div className="flex items-center justify-between mb-2">
                                <h3 className="font-bold text-gray-900 flex items-center gap-2">
                                    <Activity className="w-5 h-5 text-blue-600" />
                                    Multi-Agent Stream
                                </h3>
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] bg-gray-100 text-gray-500 px-2 py-1 rounded-md">{logs.length} Events</span>
                                    {logs.length > 0 && (
                                        <button
                                            onClick={clearLogs}
                                            className="text-[10px] text-gray-400 hover:text-gray-600"
                                        >
                                            Clear
                                        </button>
                                    )}
                                </div>
                            </div>
                            <MultiAgentLogs logs={logs} />
                        </div>
                    )}
                </div>
            </aside>
        </div>
    );
}
