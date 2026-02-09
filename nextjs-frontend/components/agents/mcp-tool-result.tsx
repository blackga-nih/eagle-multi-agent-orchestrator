'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, Terminal, CheckCircle2, XCircle } from 'lucide-react';
import { ToolResult } from '@/types/mcp';

interface MCPToolResultProps {
  toolResult: ToolResult;
}

export default function MCPToolResult({ toolResult }: MCPToolResultProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const hasError = Boolean(toolResult.error);

  const formatResult = (result: unknown): string => {
    if (typeof result === 'string') return result;
    try {
      return JSON.stringify(result, null, 2);
    } catch {
      return String(result);
    }
  };

  return (
    <div
      className={`border rounded-lg overflow-hidden ${
        hasError ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-gray-50'
      }`}
    >
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-100 transition-colors"
      >
        <Terminal className="w-4 h-4 text-gray-500" />
        <span className="font-mono text-sm font-medium text-gray-700">{toolResult.name}</span>
        {hasError ? (
          <XCircle className="w-4 h-4 text-red-500 ml-auto" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-green-500 ml-auto" />
        )}
        {isExpanded ? (
          <ChevronUp className="w-4 h-4 text-gray-400" />
        ) : (
          <ChevronDown className="w-4 h-4 text-gray-400" />
        )}
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-2">
          {/* Arguments */}
          {Object.keys(toolResult.args).length > 0 && (
            <div>
              <p className="text-[10px] font-semibold text-gray-500 uppercase mb-1">Arguments</p>
              <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-x-auto font-mono">
                {formatResult(toolResult.args)}
              </pre>
            </div>
          )}

          {/* Result or Error */}
          <div>
            <p className="text-[10px] font-semibold text-gray-500 uppercase mb-1">
              {hasError ? 'Error' : 'Result'}
            </p>
            <pre
              className={`text-xs border rounded p-2 overflow-x-auto font-mono ${
                hasError
                  ? 'bg-red-100 border-red-200 text-red-700'
                  : 'bg-white border-gray-200 text-gray-700'
              }`}
            >
              {hasError ? toolResult.error : formatResult(toolResult.result)}
            </pre>
          </div>

          {/* Timestamp */}
          <p className="text-[10px] text-gray-400">
            Executed at {toolResult.timestamp.toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}
