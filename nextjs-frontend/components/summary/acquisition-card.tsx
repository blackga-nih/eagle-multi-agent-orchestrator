'use client';

import { AcquisitionData } from '../chat/chat-interface';
import { FileText, DollarSign, Clock, AlertCircle } from 'lucide-react';

interface AcquisitionCardProps {
    data: AcquisitionData;
}

export default function AcquisitionCard({ data }: AcquisitionCardProps) {
    const hasData = Object.keys(data).length > 0;

    if (!hasData) {
        return (
            <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h3 className="text-lg font-semibold text-gray-900 mb-2 flex items-center gap-2">
                    <FileText className="w-5 h-5 text-blue-600" />
                    Acquisition Summary
                </h3>
                <p className="text-sm text-gray-500">
                    Information will appear here as you provide details in the conversation.
                </p>
            </div>
        );
    }

    return (
        <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
            <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-600" />
                Acquisition Summary
            </h3>

            <div className="space-y-3">
                {data.requirement && (
                    <div>
                        <div className="text-xs font-medium text-gray-500 uppercase mb-1">Requirement</div>
                        <div className="text-sm text-gray-900">{data.requirement}</div>
                    </div>
                )}

                {data.estimatedValue && (
                    <div className="flex items-start gap-2">
                        <DollarSign className="w-4 h-4 text-green-600 mt-0.5" />
                        <div>
                            <div className="text-xs font-medium text-gray-500 uppercase mb-1">
                                Estimated Value
                            </div>
                            <div className="text-sm text-gray-900">{data.estimatedValue}</div>
                        </div>
                    </div>
                )}

                {data.timeline && (
                    <div className="flex items-start gap-2">
                        <Clock className="w-4 h-4 text-blue-600 mt-0.5" />
                        <div>
                            <div className="text-xs font-medium text-gray-500 uppercase mb-1">Timeline</div>
                            <div className="text-sm text-gray-900">{data.timeline}</div>
                        </div>
                    </div>
                )}

                {data.urgency && (
                    <div className="flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 text-orange-600 mt-0.5" />
                        <div>
                            <div className="text-xs font-medium text-gray-500 uppercase mb-1">Urgency</div>
                            <div className="text-sm text-gray-900">{data.urgency}</div>
                        </div>
                    </div>
                )}

                {data.funding && (
                    <div>
                        <div className="text-xs font-medium text-gray-500 uppercase mb-1">Funding</div>
                        <div className="text-sm text-gray-900">{data.funding}</div>
                    </div>
                )}
            </div>

            {data.estimatedValue && data.estimatedValue.includes('$400,000') && (
                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <div className="text-xs font-semibold text-blue-900 mb-1">Acquisition Type</div>
                    <div className="text-sm text-blue-800">Negotiated (Over $250K)</div>
                </div>
            )}
        </div>
    );
}
