'use client';

import { useState } from 'react';
import {
  CheckCircle2,
  Circle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Sparkles,
  User,
  Clock
} from 'lucide-react';
import {
  RequirementSubmission,
  ReviewStatus,
  SubmissionSource,
  REVIEW_STATUS_CLASSES,
  SUBMISSION_SOURCE_CLASSES
} from '@/types/schema';

interface DocumentRequirementsProps {
  documentId: string;
}

// Mock requirements data for the document
const MOCK_REQUIREMENTS = [
  {
    id: 'req-001',
    label: 'Equipment Description',
    fieldType: 'text',
    required: true,
    submission: {
      id: 'sub-001',
      value: '128-slice CT Scanner with cardiac imaging capabilities',
      source: 'user' as SubmissionSource,
      reviewStatus: 'approved' as ReviewStatus,
      submittedBy: 'Jane Smith',
      submittedAt: '2026-01-28T12:05:00Z',
    }
  },
  {
    id: 'req-002',
    label: 'Estimated Cost Range',
    fieldType: 'text',
    required: true,
    submission: {
      id: 'sub-002',
      value: '$750,000 - $950,000',
      source: 'ai_generated' as SubmissionSource,
      reviewStatus: 'approved' as ReviewStatus,
      confidence: 0.92,
      reasoning: 'Based on market analysis of similar 128-slice CT scanners from Siemens, GE, and Philips.',
      citations: [
        { title: 'MD Buyline CT Scanner Pricing Report 2025', url: 'https://mdbuyline.com/reports/ct-2025' },
        { title: 'GSA Schedule GS-07F-0000X', url: '#' }
      ],
      submittedAt: '2026-01-28T12:08:00Z',
    }
  },
  {
    id: 'req-003',
    label: 'Delivery Timeline',
    fieldType: 'text',
    required: true,
    submission: {
      id: 'sub-003',
      value: '90 days from contract award',
      source: 'ai_generated' as SubmissionSource,
      reviewStatus: 'pending' as ReviewStatus,
      confidence: 0.85,
      reasoning: 'Standard lead time for high-end CT scanners based on vendor specifications.',
      submittedAt: '2026-01-28T12:10:00Z',
    }
  },
  {
    id: 'req-004',
    label: 'Installation Requirements',
    fieldType: 'textarea',
    required: true,
    submission: {
      id: 'sub-004',
      value: 'Complete installation within 30 days of delivery, including site preparation, electrical, and HVAC modifications.',
      source: 'user' as SubmissionSource,
      reviewStatus: 'approved' as ReviewStatus,
      submittedBy: 'Jane Smith',
      submittedAt: '2026-01-28T12:12:00Z',
    }
  },
  {
    id: 'req-005',
    label: 'Training Requirements',
    fieldType: 'textarea',
    required: false,
    submission: {
      id: 'sub-005',
      value: '40 hours of on-site training for up to 20 staff members',
      source: 'ai_generated' as SubmissionSource,
      reviewStatus: 'pending' as ReviewStatus,
      confidence: 0.78,
      reasoning: 'Recommended based on similar equipment acquisitions and FDA guidelines for CT operator training.',
      submittedAt: '2026-01-28T12:15:00Z',
    }
  },
  {
    id: 'req-006',
    label: 'Warranty Period',
    fieldType: 'text',
    required: true,
    submission: null
  },
];

export default function DocumentRequirements({ documentId }: DocumentRequirementsProps) {
  const [expandedRequirements, setExpandedRequirements] = useState<string[]>(['req-002', 'req-003']);

  const toggleExpanded = (reqId: string) => {
    setExpandedRequirements(prev =>
      prev.includes(reqId)
        ? prev.filter(id => id !== reqId)
        : [...prev, reqId]
    );
  };

  const getStatusIcon = (submission: typeof MOCK_REQUIREMENTS[0]['submission']) => {
    if (!submission) {
      return <Circle className="w-5 h-5 text-gray-300" />;
    }
    switch (submission.reviewStatus) {
      case 'approved':
        return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
      case 'pending':
        return <Clock className="w-5 h-5 text-amber-500" />;
      case 'rejected':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Circle className="w-5 h-5 text-gray-300" />;
    }
  };

  const getSourceBadge = (source: SubmissionSource) => {
    const labels = {
      user: 'Manual',
      ai_generated: 'AI Generated',
      imported: 'Imported'
    };
    return (
      <span className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full ${SUBMISSION_SOURCE_CLASSES[source]}`}>
        {source === 'ai_generated' && <Sparkles className="w-3 h-3" />}
        {source === 'user' && <User className="w-3 h-3" />}
        {labels[source]}
      </span>
    );
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
  };

  const completedCount = MOCK_REQUIREMENTS.filter(r => r.submission?.reviewStatus === 'approved').length;
  const pendingCount = MOCK_REQUIREMENTS.filter(r => r.submission?.reviewStatus === 'pending').length;
  const missingCount = MOCK_REQUIREMENTS.filter(r => !r.submission).length;

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
            <span className="text-2xl font-bold text-emerald-700">{completedCount}</span>
          </div>
          <p className="text-xs text-emerald-600 mt-1">Approved</p>
        </div>
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-amber-600" />
            <span className="text-2xl font-bold text-amber-700">{pendingCount}</span>
          </div>
          <p className="text-xs text-amber-600 mt-1">Pending Review</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <Circle className="w-5 h-5 text-gray-400" />
            <span className="text-2xl font-bold text-gray-600">{missingCount}</span>
          </div>
          <p className="text-xs text-gray-500 mt-1">Not Submitted</p>
        </div>
      </div>

      {/* Requirements List */}
      <div className="space-y-3">
        {MOCK_REQUIREMENTS.map((req) => {
          const isExpanded = expandedRequirements.includes(req.id);
          const hasDetails = req.submission?.source === 'ai_generated';

          return (
            <div
              key={req.id}
              className={`border rounded-xl overflow-hidden transition-all ${
                req.submission?.reviewStatus === 'approved'
                  ? 'border-emerald-200 bg-emerald-50/30'
                  : req.submission?.reviewStatus === 'pending'
                    ? 'border-amber-200 bg-amber-50/30'
                    : 'border-gray-200 bg-white'
              }`}
            >
              {/* Header */}
              <button
                onClick={() => hasDetails && toggleExpanded(req.id)}
                className={`w-full flex items-center gap-3 p-4 text-left ${hasDetails ? 'cursor-pointer hover:bg-gray-50/50' : ''}`}
              >
                {getStatusIcon(req.submission)}

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{req.label}</span>
                    {req.required && (
                      <span className="text-[10px] text-red-500 font-medium">Required</span>
                    )}
                  </div>
                  {req.submission && (
                    <p className="text-sm text-gray-600 mt-0.5 truncate">{req.submission.value}</p>
                  )}
                  {!req.submission && (
                    <p className="text-sm text-gray-400 italic mt-0.5">No value submitted</p>
                  )}
                </div>

                {req.submission && (
                  <div className="flex items-center gap-2">
                    {getSourceBadge(req.submission.source)}
                    {hasDetails && (
                      isExpanded ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />
                    )}
                  </div>
                )}
              </button>

              {/* Expanded Details (for AI-generated submissions) */}
              {isExpanded && req.submission?.source === 'ai_generated' && (
                <div className="px-4 pb-4 pt-0 border-t border-gray-100 bg-white/50">
                  {/* Confidence Score */}
                  {req.submission.confidence && (
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-xs text-gray-500">Confidence:</span>
                      <div className="flex-1 h-2 bg-gray-200 rounded-full max-w-32">
                        <div
                          className={`h-2 rounded-full ${
                            req.submission.confidence >= 0.9 ? 'bg-emerald-500' :
                            req.submission.confidence >= 0.7 ? 'bg-amber-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${req.submission.confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-gray-700">
                        {Math.round(req.submission.confidence * 100)}%
                      </span>
                    </div>
                  )}

                  {/* Reasoning */}
                  {req.submission.reasoning && (
                    <div className="mb-3">
                      <p className="text-xs text-gray-500 mb-1">AI Reasoning:</p>
                      <p className="text-sm text-gray-700 bg-violet-50 border border-violet-100 rounded-lg p-3">
                        {req.submission.reasoning}
                      </p>
                    </div>
                  )}

                  {/* Citations */}
                  {req.submission.citations && req.submission.citations.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 mb-2">Sources:</p>
                      <div className="space-y-1">
                        {req.submission.citations.map((citation, idx) => (
                          <a
                            key={idx}
                            href={citation.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800 hover:underline"
                          >
                            <ExternalLink className="w-3 h-3" />
                            {citation.title}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Buttons */}
                  {req.submission.reviewStatus === 'pending' && (
                    <div className="flex gap-2 mt-4 pt-3 border-t border-gray-100">
                      <button className="flex-1 px-3 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 transition-colors">
                        Approve
                      </button>
                      <button className="flex-1 px-3 py-2 bg-white border border-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors">
                        Edit
                      </button>
                      <button className="px-3 py-2 bg-white border border-red-200 text-red-600 text-sm font-medium rounded-lg hover:bg-red-50 transition-colors">
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
