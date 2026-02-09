'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  FileText,
  FolderKanban,
  Users,
  Layers,
  Bot,
  FileStack,
  ChevronRight,
  LogOut,
  BarChart3,
  MessageSquare,
  DollarSign,
  CreditCard,
} from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import ChatHistoryDropdown from './chat-history-dropdown';
import { useSession } from '@/contexts/session-context';

interface NavItem {
  href: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const mainNavItems: NavItem[] = [
  { href: '/', label: 'Chats', icon: <MessageSquare className="w-5 h-5" /> },
  { href: '/workflows', label: 'Acquisition Packages', icon: <FolderKanban className="w-5 h-5" /> },
  { href: '/documents', label: 'Documents', icon: <FileText className="w-5 h-5" /> },
];

const adminNavItems: NavItem[] = [
  { href: '/admin', label: 'Dashboard', icon: <Layers className="w-5 h-5" /> },
  { href: '/admin/users', label: 'Users', icon: <Users className="w-5 h-5" /> },
  { href: '/admin/costs', label: 'Costs', icon: <DollarSign className="w-5 h-5" /> },
  { href: '/admin/subscription', label: 'Subscription', icon: <CreditCard className="w-5 h-5" /> },
  { href: '/admin/templates', label: 'Templates', icon: <FileStack className="w-5 h-5" /> },
  { href: '/admin/skills', label: 'Agent Skills', icon: <Bot className="w-5 h-5" /> },
  { href: '/admin/analytics', label: 'Analytics', icon: <BarChart3 className="w-5 h-5" /> },
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

  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-screen">
      {/* Logo */}
      <div className="p-4 border-b border-gray-100">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-10 h-10 bg-gradient-to-br from-[#003149] to-[#0D2648] rounded-xl flex items-center justify-center shadow-lg shadow-blue-200">
            <span className="text-white font-bold text-lg">E</span>
          </div>
          <div>
            <h1 className="font-bold text-gray-900">EAGLE</h1>
            <p className="text-[9px] text-gray-500 uppercase tracking-wider">Office of Acquisitions</p>
          </div>
        </Link>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 p-4 space-y-6 overflow-y-auto">
        <div>
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2 px-3">Main</p>
          <div className="space-y-1">
            {mainNavItems.map((item) => (
              item.href === '/' ? (
                <div key={item.href} className="flex items-center gap-1">
                  <Link
                    href={item.href}
                    className={`flex-1 flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                      isActive(item.href)
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-200'
                        : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                    }`}
                  >
                    {item.icon}
                    <span className="flex-1">{item.label}</span>
                  </Link>
                  <ChatHistoryDropdown
                    sessions={sessions.map(s => ({
                      ...s,
                      createdAt: new Date(s.createdAt),
                      updatedAt: new Date(s.updatedAt),
                    }))}
                    currentSessionId={currentSessionId}
                    onSessionSelect={(sessionId) => {
                      setCurrentSession(sessionId);
                      router.push('/');
                    }}
                    onNewChat={() => {
                      createNewSession();
                      router.push('/');
                    }}
                    isLoading={isLoading}
                  />
                </div>
              ) : (
                <NavLink key={item.href} item={item} />
              )
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2 px-3">Administration</p>
          <div className="space-y-1">
            {adminNavItems.map((item) => (
              <NavLink key={item.href} item={item} />
            ))}
          </div>
        </div>
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
