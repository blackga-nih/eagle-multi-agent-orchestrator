'use client';

import { useState, useRef, useEffect } from 'react';
import {
  ChevronDown,
  MessageSquare,
  Plus,
  Clock,
  CheckCircle2,
  Loader2,
  Pencil,
} from 'lucide-react';

export interface ChatSession {
  id: string;
  title: string;
  summary?: string;
  createdAt: Date;
  updatedAt: Date;
  status: 'in_progress' | 'completed' | 'draft';
  messageCount: number;
}

interface ChatHistoryDropdownProps {
  sessions: ChatSession[];
  currentSessionId?: string;
  onSessionSelect: (sessionId: string) => void;
  onNewChat: () => void;
  onRenameSession?: (sessionId: string, newTitle: string) => void;
  isLoading?: boolean;
}

export default function ChatHistoryDropdown({
  sessions,
  currentSessionId,
  onSessionSelect,
  onNewChat,
  onRenameSession,
  isLoading = false,
}: ChatHistoryDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setEditingId(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Focus input when editing starts
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const handleStartEdit = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditTitle(session.title);
  };

  const handleSaveEdit = () => {
    if (editingId && editTitle.trim() && onRenameSession) {
      onRenameSession(editingId, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSaveEdit();
    } else if (e.key === 'Escape') {
      setEditingId(null);
      setEditTitle('');
    }
  };

  const getStatusIcon = (status: ChatSession['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-3 h-3 text-green-500" />;
      case 'in_progress':
        return <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />;
      default:
        return <Clock className="w-3 h-3 text-gray-400" />;
    }
  };

  const formatDate = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (days === 1) {
      return 'Yesterday';
    } else if (days < 7) {
      return `${days} days ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  // Sort sessions by updatedAt (most recent first)
  const sortedSessions = [...sessions].sort(
    (a, b) => b.updatedAt.getTime() - a.updatedAt.getTime(),
  );

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1 text-gray-400 hover:text-gray-600 transition-colors"
      >
        <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute left-0 top-full mt-1 w-72 bg-white rounded-xl border border-gray-200 shadow-xl z-[100] animate-in fade-in slide-in-from-top-2 duration-200">
          {/* New Chat Button */}
          <div className="p-2 border-b border-gray-100">
            <button
              onClick={() => {
                onNewChat();
                setIsOpen(false);
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          </div>

          {/* Sessions List */}
          <div className="max-h-64 overflow-y-auto">
            {isLoading ? (
              <div className="p-4 text-center text-gray-500 text-sm">
                <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" />
                Loading sessions...
              </div>
            ) : sortedSessions.length === 0 ? (
              <div className="p-4 text-center text-gray-500 text-sm">No chat history yet</div>
            ) : (
              <div className="py-1">
                {sortedSessions.map((session) => (
                  <div
                    key={session.id}
                    onClick={() => {
                      if (editingId !== session.id) {
                        onSessionSelect(session.id);
                        setIsOpen(false);
                      }
                    }}
                    className={`w-full flex items-start gap-3 px-3 py-2.5 text-left hover:bg-gray-50 transition-colors cursor-pointer group ${
                      session.id === currentSessionId ? 'bg-blue-100' : ''
                    }`}
                  >
                    <MessageSquare
                      className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                        session.id === currentSessionId ? 'text-blue-600' : 'text-gray-400'
                      }`}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {editingId === session.id ? (
                          <input
                            ref={inputRef}
                            type="text"
                            value={editTitle}
                            onChange={(e) => setEditTitle(e.target.value)}
                            onBlur={handleSaveEdit}
                            onKeyDown={handleKeyDown}
                            onClick={(e) => e.stopPropagation()}
                            className="text-sm font-medium w-full bg-white border border-blue-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        ) : (
                          <>
                            <p
                              className={`text-sm font-medium truncate flex-1 ${
                                session.id === currentSessionId ? 'text-blue-600' : 'text-gray-900'
                              }`}
                              onDoubleClick={(e) => onRenameSession && handleStartEdit(session, e)}
                              title="Double-click to rename"
                            >
                              {session.title}
                            </p>
                            {onRenameSession && (
                              <button
                                onClick={(e) => handleStartEdit(session, e)}
                                className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-gray-200 rounded transition-opacity"
                                title="Rename chat"
                              >
                                <Pencil className="w-3 h-3 text-gray-400" />
                              </button>
                            )}
                          </>
                        )}
                        {editingId !== session.id && getStatusIcon(session.status)}
                      </div>
                      {session.summary && (
                        <p className="text-xs text-gray-500 truncate mt-0.5">{session.summary}</p>
                      )}
                      <p className="text-[10px] text-gray-400 mt-1">
                        {formatDate(session.updatedAt)} • {session.messageCount} messages
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
