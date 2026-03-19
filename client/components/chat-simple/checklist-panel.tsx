'use client';

import React, { useCallback, useState } from 'react';
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
};

function docLabel(docType: string): string {
  return DOC_LABELS[docType] || docType.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

interface ChecklistPanelProps {
  state: PackageState;
}

export function ChecklistPanel({ state }: ChecklistPanelProps) {
  const { checklist, progressPct, phase, complianceAlerts, packageId } = state;
  const [downloading, setDownloading] = useState(false);

  const handleDownloadZip = useCallback(async () => {
    if (!packageId) return;
    setDownloading(true);
    try {
      const res = await fetch(`/api/packages/${encodeURIComponent(packageId)}/export/zip`);
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
  }, [packageId]);

  // Don't render if no package context
  if (!checklist && !packageId) return null;

  const required = checklist?.required || [];
  const completed = new Set(checklist?.completed || []);
  const alertCount = complianceAlerts.filter((a) => a.severity !== 'info').length;

  return (
    <div className="border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 w-72 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Acquisition Package
        </h3>
        {packageId && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 font-mono">
            {packageId}
          </p>
        )}
        {phase && (
          <span className="inline-block mt-1 px-2 py-0.5 text-xs rounded-full bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200">
            {phase}
          </span>
        )}
      </div>

      {/* Progress Bar */}
      {required.length > 0 && (
        <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-600 dark:text-gray-400">Progress</span>
            <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
              {completed.size}/{required.length}
            </span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className="bg-blue-600 dark:bg-blue-500 h-2 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      {/* ZIP Download */}
      {packageId && completed.size > 0 && (
        <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={handleDownloadZip}
            disabled={downloading}
            className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {downloading ? (
              <span>Downloading...</span>
            ) : (
              <>
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>Download Package (ZIP)</span>
              </>
            )}
          </button>
        </div>
      )}

      {/* Document Checklist */}
      {required.length > 0 && (
        <div className="flex-1 overflow-y-auto px-4 py-2">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
            Required Documents
          </p>
          <ul className="space-y-1.5">
            {required.map((docType) => {
              const isDone = completed.has(docType);
              return (
                <li key={docType} className="flex items-start gap-2">
                  <span className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded border flex items-center justify-center text-xs ${
                    isDone
                      ? 'bg-green-100 dark:bg-green-900 border-green-500 text-green-700 dark:text-green-300'
                      : 'border-gray-300 dark:border-gray-600'
                  }`}>
                    {isDone && (
                      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    )}
                  </span>
                  <span className={`text-xs leading-tight ${
                    isDone
                      ? 'text-gray-500 dark:text-gray-400 line-through'
                      : 'text-gray-800 dark:text-gray-200'
                  }`}>
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
        <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
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
                      ? 'bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-300'
                      : 'bg-yellow-50 dark:bg-yellow-950 text-yellow-700 dark:text-yellow-300'
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
