'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { PackageState } from '@/hooks/use-package-state';

/** Human-readable labels for document types. */
const DOC_LABELS: Record<string, string> = {
  sow: 'Statement of Work (SOW)',
  igce: 'Independent Government Cost Estimate (IGCE)',
  'market-research': 'Market Research Report',
  'acquisition-plan': 'Acquisition Plan',
  justification: 'Justification & Approval (J&A)',
  'd-f': 'Determination & Findings (D&F)',
  qasp: 'Quality Assurance Surveillance Plan (QASP)',
  'source-selection-plan': 'Source Selection Plan',
  'subcontracting-plan': 'Subcontracting Plan',
  'security-checklist': 'IT Security & Privacy Certification',
  'section-508': 'Section 508 ICT Evaluation',
  'human-subjects': 'Human Subjects Provisions',
  'sb-review': 'Small Business Review (HHS-653)',
  'purchase-request': 'Purchase Request',
  eval_criteria: 'Evaluation Criteria',
  cor_certification: 'COR Certification',
  'transmittal-memo': 'Transmittal Memo',
};

/** Phase-specific badge colors. */
const PHASE_STYLES: Record<string, string> = {
  intake: 'bg-blue-100 text-blue-800',
  drafting: 'bg-amber-100 text-amber-800',
  finalizing: 'bg-purple-100 text-purple-800',
  review: 'bg-green-100 text-green-800',
  approved: 'bg-emerald-100 text-emerald-800',
};

function docLabel(docType: string): string {
  return (
    DOC_LABELS[docType] || docType.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

interface ChecklistPanelProps {
  state: PackageState;
}

/**
 * Embeddable checklist content for use inside the activity panel tab.
 * Renders package header, progress, download, checklist items, and compliance alerts.
 * Shows an empty state when no package is active.
 */
export function ChecklistTabContent({ state }: ChecklistPanelProps) {
  const { checklist, progressPct, phase, complianceAlerts, packageId } = state;
  const [downloading, setDownloading] = useState(false);
  const [showFormatMenu, setShowFormatMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showFormatMenu) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowFormatMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [showFormatMenu]);

  const handleDownloadZip = useCallback(
    async (format: 'docx' | 'pdf') => {
      if (!packageId) return;
      setShowFormatMenu(false);
      setDownloading(true);
      try {
        const res = await fetch(
          `/api/packages/${encodeURIComponent(packageId)}/export/zip?format=${format}`,
        );
        if (!res.ok) throw new Error(`Export failed: ${res.status}`);
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${packageId}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (err) {
        console.error('ZIP download failed:', err);
      } finally {
        setDownloading(false);
      }
    },
    [packageId],
  );

  // Empty state — no package context yet
  if (!checklist && !packageId) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-center px-4">
        <div className="w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center mb-3">
          <svg
            className="w-5 h-5 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
            />
          </svg>
        </div>
        <p className="text-sm text-gray-500">No active package.</p>
        <p className="text-xs text-gray-400 mt-1">
          Start an acquisition intake to track required documents here.
        </p>
      </div>
    );
  }

  const required = checklist?.required || [];
  const completed = new Set(checklist?.completed || []);
  const alertCount = complianceAlerts.filter((a) => a.severity !== 'info').length;

  return (
    <div className="flex flex-col gap-0">
      {/* Package Header */}
      <div className="mb-3">
        <h4 className="text-sm font-semibold text-[#003366]">Acquisition Package</h4>
        {packageId && <p className="text-[10px] text-gray-400 mt-0.5 font-mono">{packageId}</p>}
        {phase && (
          <span
            className={`inline-block mt-1 px-2 py-0.5 text-[10px] rounded-full font-medium ${PHASE_STYLES[phase] || 'bg-blue-100 text-blue-800'}`}
          >
            {phase}
          </span>
        )}
      </div>

      {/* Progress Bar */}
      {required.length > 0 && (
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-gray-500">Progress</span>
            <span className="text-[10px] font-medium text-[#003366]">
              {completed.size}/{required.length}
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-[#2196F3] h-2 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {/* ZIP Download */}
      {packageId && completed.size > 0 && (
        <div className="mb-3 relative" ref={menuRef}>
          {downloading ? (
            <button
              disabled
              className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md bg-[#003366] text-white opacity-50 cursor-not-allowed"
            >
              <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              <span>Downloading...</span>
            </button>
          ) : (
            <>
              <button
                onClick={() => setShowFormatMenu((prev) => !prev)}
                className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md bg-[#003366] text-white hover:bg-[#004488] transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <span>Download Package</span>
                <svg
                  className={`w-3 h-3 transition-transform ${showFormatMenu ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>
              {showFormatMenu && (
                <div className="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg z-50 overflow-hidden">
                  <button
                    onClick={() => handleDownloadZip('docx')}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 hover:bg-blue-50 hover:text-[#003366] transition-colors"
                  >
                    <svg
                      className="w-3.5 h-3.5 text-blue-600"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      />
                    </svg>
                    <span>DOCX (Word)</span>
                  </button>
                  <button
                    onClick={() => handleDownloadZip('pdf')}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-700 hover:bg-red-50 hover:text-red-700 transition-colors"
                  >
                    <svg
                      className="w-3.5 h-3.5 text-red-600"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                      />
                    </svg>
                    <span>PDF</span>
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Document Checklist */}
      {required.length > 0 && (
        <div className="mb-3">
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-2">
            Required Documents
          </p>
          <ul className="space-y-1.5">
            {required.map((docType) => {
              const isDone = completed.has(docType);
              return (
                <li key={docType} className="flex items-start gap-2">
                  <span
                    className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded border flex items-center justify-center text-xs ${
                      isDone ? 'bg-green-100 border-green-500 text-green-700' : 'border-gray-300'
                    }`}
                  >
                    {isDone && (
                      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    )}
                  </span>
                  <span
                    className={`text-xs leading-tight ${
                      isDone ? 'text-gray-400 line-through' : 'text-gray-800'
                    }`}
                  >
                    {docLabel(docType)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Compliance Alerts */}
      {alertCount > 0 && (
        <div className="border-t border-[#D8DEE6] pt-3">
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1">
            Compliance Alerts ({alertCount})
          </p>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {complianceAlerts
              .filter((a) => a.severity !== 'info')
              .slice(-5)
              .map((alert, i) => (
                <div
                  key={i}
                  className={`text-xs px-2 py-1 rounded ${
                    alert.severity === 'critical'
                      ? 'bg-red-50 text-red-700'
                      : 'bg-yellow-50 text-yellow-700'
                  }`}
                >
                  {alert.items.map((item, j) => (
                    <div key={j}>
                      <span className="font-medium">{item.name}</span>
                      {item.note && <span className="opacity-75"> — {item.note}</span>}
                    </div>
                  ))}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** @deprecated Use ChecklistTabContent inside ActivityPanel instead. */
export function ChecklistPanel({ state }: ChecklistPanelProps) {
  return <ChecklistTabContent state={state} />;
}
