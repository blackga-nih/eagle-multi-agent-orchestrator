'use client';

import { useState } from 'react';
import { CheckCircle2, FileText, Download, Eye, ChevronDown, X, Send, Loader2, Clock, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { getPackage, PackageChecklist } from '@/lib/document-store';
import { Message } from '@/types/chat';
import { AcquisitionData, DocumentType } from '@/types/schema';
import { useAuth } from '@/contexts/auth-context';

interface DocumentChecklistProps {
    messages: Message[];
    data: AcquisitionData;
    sessionId?: string;
}

// Map checklist IDs to document-store document_type keys
const DOC_TYPE_MAP: Record<string, DocumentType> = {
    'sow': 'sow',
    'igce': 'igce',
    'market-research': 'market_research',
    'plan': 'acquisition_plan',
    'funding': 'funding_doc',
    'urgency': 'justification',
};

export default function DocumentChecklist({ messages, data, sessionId }: DocumentChecklistProps) {
    const [selectedDoc, setSelectedDoc] = useState<{ id: string; name: string; content: string; isTemplate?: boolean } | null>(null);
    const [showExportMenu, setShowExportMenu] = useState(false);
    const [isExporting, setIsExporting] = useState(false);
    const { getToken } = useAuth();

    const messageCount = messages.length;

    // Look up actual package state from localStorage
    const packageData = sessionId ? getPackage(sessionId) : null;
    const packageChecklist = packageData?.checklist || [];

    // Create a map for quick lookup: document_type -> checklist item
    const checklistMap = new Map<DocumentType, PackageChecklist>();
    packageChecklist.forEach(item => {
        checklistMap.set(item.document_type, item);
    });

    // Helper to check if relevant intake data exists for a doc type
    const getRelevantDataForDoc = (docId: string): boolean => {
        switch (docId) {
            case 'sow': return !!(data.requirement || data.equipmentType);
            case 'igce': return !!data.estimatedValue;
            case 'market-research': return !!(data.requirement || data.equipmentType);
            case 'plan': return !!(data.requirement && data.estimatedValue);
            case 'funding': return !!data.funding;
            case 'urgency': return !!data.urgency;
            default: return false;
        }
    };

    // Derive status from actual package state (document_id presence = completed)
    const getDocStatus = (docId: string): 'pending' | 'in-progress' | 'completed' => {
        const docType = DOC_TYPE_MAP[docId];
        const checklistItem = checklistMap.get(docType);

        // If document_id exists in checklist, it's actually completed
        if (checklistItem?.document_id) {
            return 'completed';
        }

        // Otherwise, use intake fields to determine in-progress vs pending
        const hasStartedIntake = messageCount > 0;
        const hasRelevantData = getRelevantDataForDoc(docId);

        if (hasRelevantData) return 'in-progress';
        if (hasStartedIntake) return 'in-progress';
        return 'pending';
    };

    // Get document_id from checklist if it exists
    const getDocumentId = (docId: string): string | undefined => {
        const docType = DOC_TYPE_MAP[docId];
        return checklistMap.get(docType)?.document_id;
    };

    const hasStartedIntake = messageCount > 0;
    const isRequirementDone = !!(data.requirement || data.equipmentType);
    const isSpecsDone = !!data.equipmentType;
    const isFundingDone = !!data.funding;

    // Build documents array with actual status from document-store
    const documents = [
        {
            id: 'sow',
            name: 'Statement of Work (SOW)',
            status: getDocStatus('sow'),
            description: 'Equipment specs, installation, training',
            documentId: getDocumentId('sow'),
        },
        {
            id: 'igce',
            name: 'Independent Government Cost Estimate (IGCE)',
            status: getDocStatus('igce'),
            description: 'Market research, vendor quotes',
            documentId: getDocumentId('igce'),
        },
        {
            id: 'market-research',
            name: 'Market Research Report',
            status: getDocStatus('market-research'),
            description: 'Identify capable vendors',
            documentId: getDocumentId('market-research'),
        },
        {
            id: 'plan',
            name: 'Acquisition Plan',
            status: getDocStatus('plan'),
            description: 'Strategy, milestones',
            documentId: getDocumentId('plan'),
        },
        {
            id: 'funding',
            name: 'Funding Documentation',
            status: getDocStatus('funding'),
            description: 'Grant number, balance, expiration',
            documentId: getDocumentId('funding'),
        },
        {
            id: 'urgency',
            name: 'Urgency Justification',
            status: getDocStatus('urgency'),
            description: 'Grant expiration date, impact',
            documentId: getDocumentId('urgency'),
        },
    ];

    // Check if all documents are actually generated
    const isAllDone = documents.every(d => d.status === 'completed');

    if (messageCount === 0 && !isAllDone && !hasStartedIntake) {
        return null;
    }

    // Calculate overall progress
    const completedCount = documents.filter(d => d.status === 'completed').length;
    const overallProgress = Math.round((completedCount / documents.length) * 100);

    const getDocContent = (docId: string) => {
        const req = data.requirement || 'Equipment';
        const value = data.estimatedValue || 'TBD';
        const timeline = data.timeline || 'TBD';

        const contents: Record<string, string> = {
            'sow': `# Statement of Work: ${req}\n\n## 1. Objective\nThe purpose of this acquisition is to procure a ${data.equipmentType || req} for clinical/research use at NCI.\n\n## 2. Specifications\n- Type: ${data.equipmentType || 'Standard'}\n- Requirements: 128-slice resolution, high-speed imaging.\n- Compliance: FDA approved for medical use.\n\n## 3. Deliverables\n- One (1) ${req} system.\n- Installation and calibration.\n- On-site training for up to 5 staff members.`,
            'igce': `# Independent Government Cost Estimate (IGCE)\n\n**Project:** ${req}\n**Date:** ${new Date().toLocaleDateString()}\n\n## Cost Breakdown\n| Item | Estimated Cost |\n|------|----------------|\n| ${req} System | ${value} |\n| Installation | Included |\n| Training | Included |\n| Warranty (3yr) | Included |\n\n**Total Estimated Value:** ${value}`,
            'market-research': `# Market Research Report\n\n## 1. Background\nMarket research conducted to identify vendors capable of providing a ${req}.\n\n## 2. Identified Vendors\n- GE Healthcare\n- Siemens Healthineers\n- Philips Medical Systems\n\n## 3. Determination\nMultiple vendors exist on GSA Schedule and NIH BPA contract vehicles.`,
            'plan': `# Acquisition Plan\n\n**Requirement:** ${req}\n**Anticipated Value:** ${value}\n\n## Strategy\nDue to the urgent requirement for ${data.urgency || 'deadline'}, we will utilize an existing NIH IDIQ contract vehicle to ensure delivery by ${timeline}.`,
            'funding': `# Funding Documentation\n\n**Source:** ${data.funding || 'Grant funds'}\n**Status:** Allocated\n\nFunds have been verified by the Budget Office for the acquisition of ${req} in the amount of ${value}.`,
            'urgency': `# Urgency Justification\n\n**Justification:** ${data.urgency || 'Grant expiration'}\n\nFailure to obligate funds by the current deadline will result in the loss of critical research funding. The ${req} is essential for ongoing research milestones scheduled for next quarter.`,
        };
        return contents[docId] || 'Content not yet generated.';
    };

    // Handle document click - navigate to viewer for completed, show preview for others
    const handleDocClick = (doc: typeof documents[0]) => {
        if (doc.status === 'completed' && doc.documentId) {
            // Open actual document in viewer page (new tab)
            const params = new URLSearchParams();
            if (sessionId) params.set('session', sessionId);
            window.open(`/documents/${doc.documentId}?${params.toString()}`, '_blank');
        } else {
            // Show inline preview (template) for non-completed docs
            setSelectedDoc({
                id: doc.id,
                name: doc.name,
                content: getDocContent(doc.id),
                isTemplate: true,
            });
        }
    };

    const handleDownload = async (format: 'pdf' | 'docx') => {
        setShowExportMenu(false);
        setIsExporting(true);
        try {
            const token = await getToken();
            const headers: Record<string, string> = {
                'Content-Type': 'application/json',
            };
            if (token) headers['Authorization'] = `Bearer ${token}`;

            // Generate combined markdown content from all documents
            const packageTitle = data.requirement || 'Acquisition Package';
            const allDocContent = documents
                .map(doc => getDocContent(doc.id))
                .join('\n\n---\n\n');

            const content = `# ${packageTitle}\n\n**Generated:** ${new Date().toLocaleDateString()}\n**Session:** ${sessionId || 'N/A'}\n\n---\n\n${allDocContent}`;

            const response = await fetch('/api/documents', {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    content,
                    title: packageTitle,
                    format,
                }),
            });

            if (!response.ok) {
                throw new Error(`Export failed: ${response.status}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Acquisition_Package_${packageTitle.replace(/[^a-z0-9]/gi, '_')}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download the package. Please try again.');
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm relative">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-blue-600" />
                    Document Checklist
                </h3>
                <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
                    {completedCount}/{documents.length} complete
                </span>
            </div>

            {/* Overall Progress Bar */}
            {hasStartedIntake && (
                <div className="mb-4">
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-blue-500 to-green-500 rounded-full transition-all duration-500"
                            style={{ width: `${overallProgress}%` }}
                        />
                    </div>
                    <p className="text-[10px] text-gray-400 mt-1 text-right">{overallProgress}% complete</p>
                </div>
            )}

            <div className="space-y-3">
                {documents.map((doc, idx) => (
                    <div
                        key={idx}
                        onClick={() => handleDocClick(doc)}
                        className={`flex items-start gap-3 p-3 rounded-lg transition-all cursor-pointer group border ${
                            doc.status === 'completed'
                                ? 'bg-green-50 border-green-200 hover:bg-green-100'
                                : doc.status === 'in-progress'
                                ? 'bg-blue-50 border-blue-200 hover:bg-blue-100'
                                : 'bg-gray-50 border-gray-100 hover:bg-gray-100'
                        }`}
                    >
                        <div className="mt-0.5">
                            {doc.status === 'completed' && (
                                <CheckCircle2 className="w-5 h-5 text-green-600" />
                            )}
                            {doc.status === 'in-progress' && (
                                <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
                            )}
                            {doc.status === 'pending' && (
                                <Clock className="w-5 h-5 text-gray-400" />
                            )}
                        </div>
                        <div className="flex-1">
                            <div className="flex items-center justify-between">
                                <div className={`font-medium text-sm ${
                                    doc.status === 'completed'
                                        ? 'text-green-900'
                                        : doc.status === 'in-progress'
                                        ? 'text-blue-900'
                                        : 'text-gray-900'
                                }`}>{doc.name}</div>
                                {doc.status === 'completed' && doc.documentId ? (
                                    <ExternalLink className="w-4 h-4 text-green-600 opacity-0 group-hover:opacity-100 transition-opacity" />
                                ) : (
                                    <Eye className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                                )}
                            </div>
                            <div className={`text-xs mt-1 ${
                                doc.status === 'completed'
                                    ? 'text-green-700'
                                    : doc.status === 'in-progress'
                                    ? 'text-blue-700'
                                    : 'text-gray-500'
                            }`}>{doc.description}</div>
                        </div>
                    </div>
                ))}
            </div>

            {isAllDone && (
                <div className="mt-6 pt-6 border-t border-gray-100 relative">
                    <div className="text-sm font-semibold text-gray-900 mb-3">Final Action</div>
                    <div className="relative">
                        {showExportMenu && (
                            <div className="absolute bottom-full left-0 right-0 mb-2 bg-white border border-gray-100 rounded-xl shadow-xl z-20 overflow-hidden animate-in fade-in slide-in-from-bottom-2 duration-200">
                                <button
                                    onClick={() => handleDownload('pdf')}
                                    className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 hover:bg-red-50 hover:text-red-700 transition-colors border-b border-gray-50"
                                >
                                    <div className="w-8 h-8 rounded-lg bg-red-100 flex items-center justify-center text-red-600 font-bold text-xs">PDF</div>
                                    <span>Download as PDF</span>
                                </button>
                                <button
                                    onClick={() => handleDownload('docx')}
                                    className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                                >
                                    <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs">DOCX</div>
                                    <span>Download as Word</span>
                                </button>
                            </div>
                        )}
                        <button
                            onClick={() => setShowExportMenu(!showExportMenu)}
                            disabled={isExporting}
                            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all font-medium shadow-md shadow-blue-100 group disabled:opacity-70 disabled:cursor-not-allowed"
                        >
                            {isExporting ? (
                                <>
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                    Exporting...
                                </>
                            ) : (
                                <>
                                    <Download className="w-5 h-5 group-hover:translate-y-0.5 transition-transform" />
                                    Export Package
                                    <ChevronDown className={`w-4 h-4 ml-1 transition-transform ${showExportMenu ? 'rotate-180' : ''}`} />
                                </>
                            )}
                        </button>
                    </div>
                </div>
            )}

            {!isAllDone && (
                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="text-xs font-semibold text-blue-900 mb-1">Next Steps</div>
                    <div className="space-y-1">
                        {!isRequirementDone && (
                            <div className="text-[10px] flex items-center gap-1 text-blue-800">
                                <span className="text-red-500 text-xs">🔴</span> Define primary requirement
                            </div>
                        )}
                        {!isSpecsDone && (
                            <div className="text-[10px] flex items-center gap-1 text-blue-800">
                                <span className="text-yellow-500 text-xs">🟡</span> Provide equipment specifications
                            </div>
                        )}
                        {!isFundingDone && (
                            <div className="text-[10px] flex items-center gap-1 text-blue-800">
                                <span className="text-red-500 text-xs">🔴</span> Confirm funding source
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Document Viewer Modal */}
            {selectedDoc && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-300">
                    <div data-testid="modal-document-viewer" className="bg-white rounded-2xl shadow-2xl w-[85vw] h-[85vh] flex overflow-hidden animate-in zoom-in-95 duration-300">
                        {/* Preview Area */}
                        <div className="flex-1 flex flex-col bg-white">
                            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
                                <h3 className="font-bold text-gray-900 text-lg flex items-center gap-2">
                                    <FileText className="w-5 h-5 text-blue-600" />
                                    {selectedDoc.isTemplate ? 'Preview: ' : ''}{selectedDoc.name}
                                    {selectedDoc.isTemplate && (
                                        <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full ml-2">
                                            Template
                                        </span>
                                    )}
                                </h3>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => setSelectedDoc(null)}
                                        className="p-2 hover:bg-gray-200 rounded-full transition-colors text-gray-500"
                                    >
                                        <X className="w-5 h-5" />
                                    </button>
                                </div>
                            </div>
                            <div className="flex-1 p-8 overflow-y-auto bg-gray-50/30">
                                <article className="prose prose-blue max-w-none bg-white p-10 shadow-sm border border-gray-100 min-h-full">
                                    <ReactMarkdown
                                        components={{
                                            p: ({ children }) => <p className="mb-4 text-gray-700 leading-relaxed">{children}</p>,
                                            h1: ({ children }) => <h1 className="text-2xl font-bold text-blue-900 mb-6 border-b pb-2">{children}</h1>,
                                            h2: ({ children }) => <h2 className="text-xl font-semibold text-blue-800 mt-8 mb-4">{children}</h2>,
                                            ul: ({ children }) => <ul className="list-disc ml-6 mb-4 space-y-2 text-gray-700">{children}</ul>,
                                        }}
                                    >
                                        {selectedDoc.content}
                                    </ReactMarkdown>
                                </article>
                            </div>
                        </div>

                        {/* Modal Chat Sidebar */}
                        <div className="w-80 border-l border-gray-200 flex flex-col bg-gray-50">
                            <div className="p-4 border-b border-gray-200 bg-white">
                                <h4 className="font-semibold text-sm text-gray-900">Chat with Document</h4>
                                <p className="text-[10px] text-gray-500">Ask EAGLE to refine specific sections.</p>
                            </div>
                            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-800">
                                    I can help you adjust the specifications or add more technical details to this {selectedDoc.name.split('(')[0].trim()}.
                                </div>
                            </div>
                            <div className="p-4 border-t border-gray-200 bg-white">
                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        placeholder="Suggest an edit..."
                                        className="flex-1 text-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                                    />
                                    <button className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                                        <Send className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
