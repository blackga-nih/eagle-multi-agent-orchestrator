'use client';

import { useState } from 'react';
import { Message, AcquisitionData } from '../chat/chat-interface';
import { CheckCircle2, AlertCircle, XCircle, FileText, Download, Eye, ChevronDown, X, Send, Loader2, Clock } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface DocumentChecklistProps {
    messages: Message[];
    data: AcquisitionData;
}

export default function DocumentChecklist({ messages, data }: DocumentChecklistProps) {
    const [selectedDoc, setSelectedDoc] = useState<{ id: string; name: string; content: string } | null>(null);
    const [showExportMenu, setShowExportMenu] = useState(false);

    const messageCount = messages.length;

    // Logic for completion
    const isRequirementDone = !!data.requirement || !!data.equipmentType;
    const isSpecsDone = !!data.equipmentType;
    const isFundingDone = !!data.funding;
    const isUrgencyDone = !!data.urgency;
    const isValueDone = !!data.estimatedValue;
    const isAllDone = isRequirementDone && isSpecsDone && isFundingDone && isUrgencyDone;

    if (messageCount === 0 && !isAllDone) {
        return null;
    }

    // Determine progress states based on conversation context
    const hasStartedIntake = messageCount > 0;
    const isGatheringInfo = hasStartedIntake && !isAllDone;

    const documents = [
        {
            id: 'sow',
            name: 'Statement of Work (SOW)',
            status: isSpecsDone ? 'completed' : (isRequirementDone ? 'in-progress' : 'pending'),
            description: 'Equipment specs, installation, training',
            progress: isSpecsDone ? 100 : (isRequirementDone ? 50 : 0),
        },
        {
            id: 'igce',
            name: 'Independent Government Cost Estimate (IGCE)',
            status: isValueDone ? 'completed' : (isRequirementDone ? 'in-progress' : 'pending'),
            description: 'Market research, vendor quotes',
            progress: isValueDone ? 100 : (isRequirementDone ? 30 : 0),
        },
        {
            id: 'market-research',
            name: 'Market Research Report',
            status: isSpecsDone ? 'completed' : (isRequirementDone ? 'in-progress' : 'pending'),
            description: 'Identify capable vendors',
            progress: isSpecsDone ? 100 : (isRequirementDone ? 40 : 0),
        },
        {
            id: 'plan',
            name: 'Acquisition Plan',
            status: isAllDone ? 'completed' : (isRequirementDone && isValueDone ? 'in-progress' : 'pending'),
            description: 'Strategy, milestones',
            progress: isAllDone ? 100 : ((isRequirementDone ? 25 : 0) + (isValueDone ? 25 : 0) + (isFundingDone ? 25 : 0) + (isUrgencyDone ? 25 : 0)),
        },
        {
            id: 'funding',
            name: 'Funding Documentation',
            status: isFundingDone ? 'completed' : (hasStartedIntake ? 'in-progress' : 'pending'),
            description: 'Grant number, balance, expiration',
            progress: isFundingDone ? 100 : (hasStartedIntake ? 20 : 0),
        },
        {
            id: 'urgency',
            name: 'Urgency Justification',
            status: isUrgencyDone ? 'completed' : (hasStartedIntake ? 'in-progress' : 'pending'),
            description: 'Grant expiration date, impact',
            progress: isUrgencyDone ? 100 : (hasStartedIntake ? 10 : 0),
        },
    ];

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

    const handleDownload = async (format: 'pdf' | 'docx') => {
        setShowExportMenu(false);
        try {
            const response = await fetch('/api/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    format,
                    data: data
                }),
            });

            if (!response.ok) {
                throw new Error('Export failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Acquisition_Package_${(data.requirement || 'Package').replace(/\s+/g, '_')}.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Download error:', error);
            alert('Failed to download the package. Please try again.');
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
                        onClick={() => setSelectedDoc({ id: doc.id, name: doc.name, content: getDocContent(doc.id) })}
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
                                <Eye className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                            <div className={`text-xs mt-1 ${
                                doc.status === 'completed'
                                    ? 'text-green-700'
                                    : doc.status === 'in-progress'
                                    ? 'text-blue-700'
                                    : 'text-gray-500'
                            }`}>{doc.description}</div>
                            {doc.status === 'in-progress' && doc.progress > 0 && (
                                <div className="mt-2">
                                    <div className="h-1 bg-blue-100 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-blue-500 rounded-full transition-all duration-500"
                                            style={{ width: `${doc.progress}%` }}
                                        />
                                    </div>
                                </div>
                            )}
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
                            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-all font-medium shadow-md shadow-blue-100 group"
                        >
                            <Download className="w-5 h-5 group-hover:translate-y-0.5 transition-transform" />
                            Export Package
                            <ChevronDown className={`w-4 h-4 ml-1 transition-transform ${showExportMenu ? 'rotate-180' : ''}`} />
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
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[85vh] flex overflow-hidden animate-in zoom-in-95 duration-300">
                        {/* Preview Area */}
                        <div className="flex-1 flex flex-col bg-white">
                            <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/50">
                                <h3 className="font-bold text-gray-900 text-lg flex items-center gap-2">
                                    <FileText className="w-5 h-5 text-blue-600" />
                                    Preview: {selectedDoc.name}
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
