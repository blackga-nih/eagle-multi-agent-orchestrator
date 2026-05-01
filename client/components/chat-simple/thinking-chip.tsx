'use client';

import { useState } from 'react';
import { ThinkingBlock } from '@/types/stream';
import Modal from '@/components/ui/modal';

interface ThinkingChipProps {
  block: ThinkingBlock;
}

function StatusDot({ status }: { status: ThinkingBlock['status'] }) {
  if (status === 'streaming') {
    return (
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-purple-500" />
      </span>
    );
  }
  return <span className="inline-flex h-1.5 w-1.5 rounded-full bg-purple-400 shrink-0" />;
}

function durationLabel(block: ThinkingBlock): string {
  if (block.status === 'streaming') return '';
  if (block.endedAt == null) return '';
  const ms = Math.max(0, block.endedAt - block.startedAt);
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function ThinkingChip({ block }: ThinkingChipProps) {
  const [open, setOpen] = useState(false);

  const label = block.status === 'streaming' ? 'Thinking' : 'Thought';
  const dur = durationLabel(block);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-purple-300 bg-purple-50 hover:bg-purple-100 text-xs cursor-pointer transition-colors select-none"
        title={
          block.agentName
            ? `${label} — ${block.agentName}${dur ? ` (${dur})` : ''}`
            : `${label}${dur ? ` (${dur})` : ''}`
        }
      >
        <span className="text-sm leading-none shrink-0" aria-hidden>
          🧠
        </span>
        <span className="font-medium text-purple-900 whitespace-nowrap">{label}</span>
        {dur && <span className="text-purple-700/70 whitespace-nowrap">{dur}</span>}
        <StatusDot status={block.status} />
      </button>

      {open && (
        <Modal isOpen={open} onClose={() => setOpen(false)} title={label}>
          <div className="space-y-3">
            {block.agentName && (
              <div className="text-xs text-gray-500">
                Agent: <span className="font-medium text-gray-700">{block.agentName}</span>
              </div>
            )}
            <pre className="whitespace-pre-wrap text-sm text-gray-800 bg-purple-50/40 border border-purple-100 rounded-md p-3 font-mono leading-relaxed max-h-[60vh] overflow-y-auto">
              {block.content || (block.status === 'streaming' ? '…' : '(empty)')}
            </pre>
          </div>
        </Modal>
      )}
    </>
  );
}
