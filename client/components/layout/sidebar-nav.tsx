'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  FileText,
  FolderKanban,
  ChevronRight,
  LogOut,
  MessageSquare,
  Loader2,
  LayoutDashboard,
  FlaskConical,
  GitBranch,
} from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import { useSession } from '@/contexts/session-context';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const resourceNavItems: NavItem[] = [
  { href: '/workflows', label: 'Acquisition Packages', icon: <FolderKanban className="w-5 h-5" /> },
  { href: '/documents', label: 'Documents', icon: <FileText className="w-5 h-5" /> },
];

const toolNavItems: NavItem[] = [
  { href: '/admin', label: 'Dashboard', icon: <LayoutDashboard className="w-5 h-5" /> },
  { href: '/admin/tests', label: 'Test Results', icon: <FlaskConical className="w-5 h-5" /> },
  { href: '/admin/eval', label: 'Eval Viewer', icon: <GitBranch className="w-5 h-5" /> },
];

export default function SidebarNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const { sessions, currentSessionId, isLoading, createNewSession, setCurrentSession } = useSession();

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

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
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
          isActive(item.href) ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-700'
        }`}>
          {item.badge}
        </span>
      )}
      {isActive(item.href) && <ChevronRight className="w-4 h-4" />}
    </Link>
  );

  // Sort sessions by updatedAt descending
  const sortedSessions = [...sessions]
    .map(s => ({ ...s, createdAt: new Date(s.createdAt), updatedAt: new Date(s.updatedAt) }))
    .sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());

  const formatDate = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    if (days === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (days === 1) return 'Yesterday';
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-full">
      {/* Chat section + conversation history */}
      <nav className="flex-1 flex flex-col overflow-hidden p-4 gap-4">
        <div className="flex flex-col flex-1 min-h-0">
          {/* New Chat button */}
          <button
            onClick={() => { createNewSession(); router.push('/chat'); }}
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
              <div className="py-4 text-center text-gray-400 text-xs">
                No conversations yet
              </div>
            ) : (
              <div className="space-y-0.5">
                {sortedSessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => { setCurrentSession(session.id); router.push('/chat'); }}
                    className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left transition-colors ${
                      session.id === currentSessionId
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${
                      session.id === currentSessionId ? 'text-blue-500' : 'text-gray-300'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium truncate">{session.title}</p>
                      <p className="text-[10px] text-gray-400 truncate">
                        {formatDate(session.updatedAt)} {session.messageCount > 0 && `• ${session.messageCount} msgs`}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Resources section — pinned below conversations */}
        <div className="shrink-0 border-t border-gray-100 pt-3">
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2 px-3">Resources</p>
          <div className="space-y-1">
            {resourceNavItems.map((item) => (
              <NavLink key={item.href} item={item} />
            ))}
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
