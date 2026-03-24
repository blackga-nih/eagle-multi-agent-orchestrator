'use client';

import { useState, useRef, KeyboardEvent } from 'react';
import { X, Lock, Plus } from 'lucide-react';

export interface TagEditorProps {
  systemTags?: string[];
  userTags?: string[];
  farTags?: string[];
  onAddTag?: (tag: string) => void;
  onRemoveTag?: (tag: string) => void;
  readOnly?: boolean;
}

interface TagGroupProps {
  label: string;
  tags: string[];
  variant: 'system' | 'far' | 'user';
  onRemove?: (tag: string) => void;
  readOnly?: boolean;
}

function TagGroup({ label, tags, variant, onRemove, readOnly }: TagGroupProps) {
  if (tags.length === 0) return null;

  const baseClasses = 'inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full';
  const variantClasses = {
    system: 'bg-gray-100 text-gray-700',
    far: 'bg-amber-100 text-amber-700',
    user: 'bg-blue-100 text-blue-700',
  };

  return (
    <div className="mb-2 last:mb-0">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-400 mb-1">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <span key={tag} className={`${baseClasses} ${variantClasses[variant]}`}>
            {variant === 'system' && (
              <Lock className="w-2.5 h-2.5 flex-shrink-0" aria-hidden="true" />
            )}
            <span>{tag}</span>
            {variant === 'user' && !readOnly && onRemove && (
              <button
                type="button"
                onClick={() => onRemove(tag)}
                className="ml-0.5 rounded-full hover:bg-blue-200 transition-colors p-0.5"
                aria-label={`Remove tag ${tag}`}
              >
                <X className="w-2.5 h-2.5" />
              </button>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function TagEditor({
  systemTags = [],
  userTags = [],
  farTags = [],
  onAddTag,
  onRemoveTag,
  readOnly = false,
}: TagEditorProps) {
  const [inputValue, setInputValue] = useState('');
  const [showInput, setShowInput] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleAdd = () => {
    const trimmed = inputValue.trim();
    if (!trimmed) return;
    onAddTag?.(trimmed);
    setInputValue('');
    setShowInput(false);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    } else if (e.key === 'Escape') {
      setInputValue('');
      setShowInput(false);
    }
  };

  const handleShowInput = () => {
    setShowInput(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const hasAnyTags = systemTags.length > 0 || farTags.length > 0 || userTags.length > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-3">
      {!hasAnyTags && readOnly ? (
        <p className="text-xs text-gray-400 italic">No tags</p>
      ) : (
        <>
          <TagGroup label="System" tags={systemTags} variant="system" readOnly={readOnly} />
          <TagGroup label="FAR/DFARS" tags={farTags} variant="far" readOnly={readOnly} />
          <TagGroup
            label="Custom"
            tags={userTags}
            variant="user"
            onRemove={onRemoveTag}
            readOnly={readOnly}
          />
        </>
      )}

      {!readOnly && (
        <div className="mt-2">
          {showInput ? (
            <div className="flex items-center gap-1.5">
              <input
                ref={inputRef}
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Add tag..."
                className="flex-1 text-xs px-2 py-1 border border-blue-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-400 text-gray-700 placeholder-gray-400"
                maxLength={64}
              />
              <button
                type="button"
                onClick={handleAdd}
                disabled={!inputValue.trim()}
                className="text-xs px-2 py-1 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Add
              </button>
              <button
                type="button"
                onClick={() => { setInputValue(''); setShowInput(false); }}
                className="text-xs px-2 py-1 text-gray-500 hover:text-gray-700 rounded-md hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={handleShowInput}
              className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 hover:bg-blue-50 px-2 py-0.5 rounded-md transition-colors"
            >
              <Plus className="w-3 h-3" />
              Add tag
            </button>
          )}
        </div>
      )}
    </div>
  );
}
