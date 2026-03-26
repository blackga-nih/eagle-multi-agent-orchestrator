'use client';

import { useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { X, Copy, Send, Grid3X3, ListChecks, Search } from 'lucide-react';
import { Tabs } from '../ui/tabs';
import { useMatrixState } from './use-matrix-state';
import DetailExplorerTab from './detail-explorer-tab';
import GridMatrixTab from './grid-matrix-tab';
import ContractTypeSelectorTab from './contract-type-selector-tab';
import type { MatrixTab } from './matrix-types';

interface ContractMatrixModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (text: string) => void;
  initialTab?: MatrixTab;
  initialAcquisitionMethod?: string;
  initialContractType?: string;
}

export default function ContractMatrixModal({
  isOpen,
  onClose,
  onApply,
  initialTab = 'explorer',
  initialAcquisitionMethod,
  initialContractType,
}: ContractMatrixModalProps) {
  const {
    state,
    activeTab,
    setActiveTab,
    setMethod,
    setType,
    setDollarValue,
    toggleFlag,
    applyPreset,
    requirements,
    summary,
    factorAnswers,
    setFactorAnswer,
    clearFactorAnswers,
    recommendations,
  } = useMatrixState(initialAcquisitionMethod, initialContractType);

  // Set initial tab on open
  useEffect(() => {
    if (isOpen) setActiveTab(initialTab);
  }, [isOpen, initialTab, setActiveTab]);

  // Escape to close
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  const handleApply = useCallback(() => {
    onApply(summary);
    onClose();
  }, [summary, onApply, onClose]);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(summary);
  }, [summary]);

  const handleUseType = useCallback((typeId: string) => {
    setType(typeId);
    setActiveTab('explorer');
  }, [setType, setActiveTab]);

  if (!isOpen) return null;

  const tabs = [
    { id: 'explorer' as MatrixTab, label: 'Detail Explorer', icon: <Search className="w-3.5 h-3.5" /> },
    { id: 'grid' as MatrixTab, label: '2D Grid Matrix', icon: <Grid3X3 className="w-3.5 h-3.5" /> },
    { id: 'selector' as MatrixTab, label: 'Contract Type Selector', icon: <ListChecks className="w-3.5 h-3.5" /> },
  ];

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        data-testid="contract-matrix-modal"
        className="w-[92vw] max-w-[1600px] h-[88vh] bg-white rounded-2xl shadow-2xl animate-in zoom-in-95 duration-200 flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100 bg-gray-50/50 flex-shrink-0">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-lg font-bold text-gray-900">Contract Requirements Matrix</h2>
              <p className="text-[11px] text-gray-400">NCI Office of Acquisitions &mdash; HHS/NIH Thresholds (FAC 2025-06)</p>
            </div>
            <div className="ml-4">
              <Tabs
                tabs={tabs}
                activeTab={activeTab}
                onChange={(id) => setActiveTab(id as MatrixTab)}
                variant="underline"
              />
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'explorer' && (
            <DetailExplorerTab
              state={state}
              requirements={requirements}
              onSetMethod={setMethod}
              onSetType={setType}
              onSetDollarValue={setDollarValue}
              onToggleFlag={toggleFlag}
              onApplyPreset={applyPreset}
            />
          )}
          {activeTab === 'grid' && (
            <GridMatrixTab
              state={state}
              onSelectCell={(methodId, typeId) => {
                setMethod(methodId);
                setType(typeId);
                setActiveTab('explorer');
              }}
            />
          )}
          {activeTab === 'selector' && (
            <ContractTypeSelectorTab
              factorAnswers={factorAnswers}
              recommendations={recommendations}
              onSetFactorAnswer={setFactorAnswer}
              onClearAnswers={clearFactorAnswers}
              onUseType={handleUseType}
            />
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-gray-100 bg-gray-50/50 flex-shrink-0">
          <div className="text-[11px] text-gray-400">
            Press <kbd className="px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 font-mono text-[10px]">Esc</kbd> to close
            &nbsp;&middot;&nbsp;
            <kbd className="px-1.5 py-0.5 rounded bg-gray-200 text-gray-500 font-mono text-[10px]">Ctrl+M</kbd> to toggle
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <Copy className="w-3.5 h-3.5" />
              Copy Summary
            </button>
            <button
              onClick={handleApply}
              className="flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Send className="w-3.5 h-3.5" />
              Apply to Chat
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
