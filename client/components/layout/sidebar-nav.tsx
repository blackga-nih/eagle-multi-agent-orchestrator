'use client';

import { useState, useRef, useEffect, memo, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  ChevronRight,
  LogOut,
  Loader2,
  LayoutDashboard,
  FlaskConical,
  GitBranch,
  Pencil,
  Trash2,
  Settings,
} from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';
import { useSettings } from '@/contexts/settings-context';
import { useChatRuntime } from '@/hooks/use-chat-runtime';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const toolNavItems: NavItem[] = [
  { href: '/admin', label: 'Dashboard', icon: <LayoutDashboard className="w-5 h-5" /> },
  { href: '/admin/tests', label: 'Test Results', icon: <FlaskConical className="w-5 h-5" /> },
  { href: '/admin/eval', label: 'Eval Viewer', icon: <GitBranch className="w-5 h-5" /> },
];

/** Tiny component so we can call useChatRuntime per session row. */
const SessionStreamingDot = memo(function SessionStreamingDot({
  sessionId,
}: {
  sessionId: string;
}) {
  const runtime = useChatRuntime(sessionId);
  if (!runtime.isStreaming) return null;
  return (
    <span
      className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse shrink-0"
      title="Generating..."
    />
  );
});

/** Pure helper — no component deps. */
function formatDate(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export default function SidebarNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const {
    sessions,
    currentSessionId,
    isLoading,
    createNewSession,
    setCurrentSession,
    renameSession,
    deleteSession,
  } = useSession();
  const { adminMode, setAdminMode } = useSettings();

  // Settings dropdown state
  const [settingsOpen, setSettingsOpenState] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  // Close settings dropdown on outside click
  useEffect(() => {
    if (!settingsOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setSettingsOpenState(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [settingsOpen]);

  // Inline rename state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  // Delete confirmation state
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Focus input when editing starts
  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const handleStartEdit = (sessionId: string, currentTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(sessionId);
    setEditTitle(currentTitle);
  };

  const handleSaveEdit = () => {
    if (editingId && editTitle.trim()) {
      renameSession(editingId, editTitle.trim());
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

  const handleDelete = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (deletingId === sessionId) {
      deleteSession(sessionId);
      setDeletingId(null);
    } else {
      setDeletingId(sessionId);
      // Auto-reset confirmation after 3 seconds
      setTimeout(() => setDeletingId((prev) => (prev === sessionId ? null : prev)), 3000);
    }
  };

  const isActive = useCallback(
    (href: string) => {
      if (href === '/') return pathname === '/';
      return pathname.startsWith(href);
    },
    [pathname],
  );

  const displayName = user?.displayName || user?.email || 'User';
  const initials = displayName
    .split(' ')
    .map((n: string) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
  const tierLabel = user?.tier ? user.tier.charAt(0).toUpperCase() + user.tier.slice(1) : 'Free';

  const handleSignOut = async () => {
    await signOut();
    router.push('/login/');
  };

  const NavLink = ({ item }: { item: NavItem }) => (
    <Link
      href={item.href}
      className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
        isActive(item.href)
          ? 'bg-blue-600 text-white shadow-md shadow-blue-200'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
      }`}
    >
      {item.icon}
      <span className="flex-1">{item.label}</span>
      {item.badge && (
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
            isActive(item.href) ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-700'
          }`}
        >
          {item.badge}
        </span>
      )}
      {isActive(item.href) && <ChevronRight className="w-4 h-4" />}
    </Link>
  );

  // Sort sessions by updatedAt descending — memoized to avoid re-sort on pathname changes
  const sortedSessions = useMemo(
    () =>
      [...sessions]
        .map((s) => ({ ...s, createdAt: new Date(s.createdAt), updatedAt: new Date(s.updatedAt) }))
        .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()),
    [sessions],
  );

  return (
    <aside className="w-72 bg-white border-r border-gray-200 flex flex-col h-full">
      {/* Chat section + conversation history */}
      <nav className="flex-1 flex flex-col overflow-hidden p-4 gap-4">
        <div className="flex flex-col flex-1 min-h-0">
          {/* New Chat button */}
          <button
            onClick={() => {
              createNewSession();
              router.push('/chat');
            }}
            className="flex items-center justify-center px-3 py-2.5 mb-2 rounded-xl text-sm font-medium transition-all w-full bg-blue-600 text-white hover:bg-blue-700 shadow-md shadow-blue-200"
          >
            <span>New Chat</span>
          </button>

          {/* Inline conversation list */}
          <div className="flex-1 overflow-y-auto custom-scrollbar -mx-1 px-1">
            {isLoading ? (
              <div className="py-4 text-center text-gray-400 text-xs">
                <Loader2 className="w-4 h-4 animate-spin mx-auto mb-1" />
                Loading...
              </div>
            ) : sortedSessions.length === 0 ? (
              <div className="py-4 text-center text-gray-400 text-xs">No conversations yet</div>
            ) : (
              <div className="space-y-0.5">
                {sortedSessions.map((session) => (
                  <div
                    key={session.id}
                    onClick={() => {
                      if (editingId !== session.id) {
                        setCurrentSession(session.id);
                        router.push('/chat');
                      }
                    }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-left transition-colors cursor-pointer group ${
                      session.id === currentSessionId
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <SessionStreamingDot sessionId={session.id} />
                    <div className="flex-1 min-w-0">
                      {editingId === session.id ? (
                        <input
                          ref={inputRef}
                          type="text"
                          value={editTitle}
                          onChange={(e) => setEditTitle(e.target.value)}
                          onBlur={handleSaveEdit}
                          onKeyDown={handleKeyDown}
                          onClick={(e) => e.stopPropagation()}
                          className="text-xs w-full bg-white border border-blue-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      ) : (
                        <p
                          className="text-xs leading-snug"
                          style={{
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                          onDoubleClick={(e) => handleStartEdit(session.id, session.title, e)}
                          title={session.title}
                        >
                          {session.title}
                        </p>
                      )}
                      <div className="flex items-center gap-1">
                        <p className="text-[11px] text-gray-400 truncate flex-1">
                          {formatDate(session.updatedAt)}{' '}
                          {session.messageCount > 0 && `• ${session.messageCount} msgs`}
                        </p>
                        <div className="flex items-center gap-0.5 shrink-0">
                          <button
                            onClick={(e) => handleStartEdit(session.id, session.title, e)}
                            className="opacity-0 group-hover:opacity-100 p-0.5 hover:bg-gray-200 rounded transition-opacity"
                            title="Rename chat"
                          >
                            <Pencil className="w-3 h-3 text-gray-400" />
                          </button>
                          <button
                            onClick={(e) => handleDelete(session.id, e)}
                            className={`p-0.5 rounded transition-opacity ${
                              deletingId === session.id
                                ? 'opacity-100 bg-red-100 hover:bg-red-200'
                                : 'opacity-0 group-hover:opacity-100 hover:bg-gray-200'
                            }`}
                            title={
                              deletingId === session.id
                                ? 'Click again to confirm delete'
                                : 'Delete chat'
                            }
                          >
                            <Trash2
                              className={`w-3 h-3 ${
                                deletingId === session.id ? 'text-red-500' : 'text-gray-400'
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Tools section — hidden for now */}
      </nav>

      {/* User Profile */}
      <div className="p-4 border-t border-gray-100">
        <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl">
          <div className="w-10 h-10 bg-gradient-to-br from-[#003149] to-[#7740A4] rounded-full flex items-center justify-center text-white font-semibold text-sm">
            {initials}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{displayName}</p>
            <p className="text-[10px] text-gray-500">{tierLabel}</p>
          </div>
          <div className="relative" ref={settingsRef}>
            <button
              onClick={() => setSettingsOpenState((p) => !p)}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
            {settingsOpen && (
              <div className="absolute right-0 bottom-full mb-1 w-52 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-50">
                <label className="flex items-center justify-between px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 cursor-pointer">
                  <span>Admin mode</span>
                  <input
                    type="checkbox"
                    checked={adminMode}
                    onChange={(e) => setAdminMode(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                </label>
              </div>
            )}
          </div>
          <button
            onClick={handleSignOut}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-200 rounded-lg transition-colors"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
