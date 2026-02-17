'use client';

import { FileText, ExternalLink, FileSpreadsheet, ClipboardList, Scale, BarChart3 } from 'lucide-react';
import { DocumentInfo } from '@/types/chat';

interface DocumentCardProps {
    document: DocumentInfo;
    sessionId: string;
}

const DOC_TYPE_CONFIG: Record<string, { label: string; icon: typeof FileText; color: string; bg: string }> = {
    sow: { label: 'Statement of Work', icon: ClipboardList, color: 'text-blue-700', bg: 'bg-blue-50 border-blue-200' },
    igce: { label: 'Cost Estimate (IGCE)', icon: FileSpreadsheet, color: 'text-green-700', bg: 'bg-green-50 border-green-200' },
    market_research: { label: 'Market Research', icon: BarChart3, color: 'text-purple-700', bg: 'bg-purple-50 border-purple-200' },
    acquisition_plan: { label: 'Acquisition Plan', icon: FileText, color: 'text-indigo-700', bg: 'bg-indigo-50 border-indigo-200' },
    justification: { label: 'Justification & Approval', icon: Scale, color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' },
};

function getDocId(doc: DocumentInfo): string {
    const raw = doc.document_id || doc.s3_key || doc.title;
    return encodeURIComponent(raw);
}

export default function DocumentCard({ document, sessionId }: DocumentCardProps) {
    const config = DOC_TYPE_CONFIG[document.document_type] || {
        label: document.document_type,
        icon: FileText,
        color: 'text-gray-700',
        bg: 'bg-gray-50 border-gray-200',
    };
    const Icon = config.icon;

    const handleOpen = () => {
        const docId = getDocId(document);
        const params = new URLSearchParams();
        if (sessionId) params.set('session', sessionId);

        // Store document content in sessionStorage for instant load
        try {
            sessionStorage.setItem(`doc-content-${docId}`, JSON.stringify(document));
        } catch {
            // sessionStorage may be unavailable
        }

        window.open(`/documents/${docId}?${params.toString()}`, '_blank');
    };

    return (
        <div
            className={`border-l-4 border-l-[#003366] rounded-xl bg-white border border-[#E8ECF1] shadow-sm overflow-hidden
                        hover:shadow-md hover:border-[#BBDEFB] transition-all cursor-pointer group`}
            onClick={handleOpen}
        >
            <div className="p-4 flex items-start gap-3">
                {/* Icon */}
                <div className={`p-2 rounded-lg ${config.bg}`}>
                    <Icon className={`w-5 h-5 ${config.color}`} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${config.bg} ${config.color}`}>
                            {config.label}
                        </span>
                    </div>
                    <h4 className="font-semibold text-gray-900 text-sm truncate group-hover:text-[#003366] transition-colors">
                        {document.title}
                    </h4>
                    {document.word_count && (
                        <p className="text-xs text-gray-500 mt-0.5">
                            {document.word_count.toLocaleString()} words
                        </p>
                    )}
                </div>

                {/* Action */}
                <button
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-[#003366] text-white text-xs font-medium rounded-lg
                               hover:bg-[#004488] transition-colors shrink-0 opacity-90 group-hover:opacity-100"
                    onClick={(e) => {
                        e.stopPropagation();
                        handleOpen();
                    }}
                >
                    Open Document
                    <ExternalLink className="w-3.5 h-3.5" />
                </button>
            </div>
        </div>
    );
}
