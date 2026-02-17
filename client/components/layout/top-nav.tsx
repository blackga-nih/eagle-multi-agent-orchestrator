'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { LogOut, MessageSquare, FolderKanban, FileText, LayoutDashboard } from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import { checkBackendHealth } from '@/hooks/use-agent-stream';

const navLinks = [
  { href: '/chat', label: 'Chat', icon: <MessageSquare className="w-4 h-4" /> },
  { href: '/workflows', label: 'Packages', icon: <FolderKanban className="w-4 h-4" /> },
  { href: '/documents', label: 'Documents', icon: <FileText className="w-4 h-4" /> },
  { href: '/admin', label: 'Admin', icon: <LayoutDashboard className="w-4 h-4" /> },
];

export default function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);

  useEffect(() => {
    checkBackendHealth().then(setBackendConnected);
    const interval = setInterval(() => {
      checkBackendHealth().then(setBackendConnected);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const isActive = (href: string) => {
    if (href === '/chat') return pathname === '/chat';
    return pathname.startsWith(href);
  };

  const displayName = user?.displayName || user?.email || 'User';

  const handleSignOut = async () => {
    await signOut();
    router.push('/login/');
  };

  return (
    <header
      className="bg-[#003366] text-white px-6 flex items-center justify-between shrink-0 z-10"
      style={{ height: 56, boxShadow: '0 2px 8px rgba(0,51,102,0.3)' }}
    >
      {/* Left: branding */}
      <div className="flex items-center gap-3">
        <span className="text-[28px] leading-none" style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.3))' }}>
          🦅
        </span>
        <div>
          <h1 className="text-lg font-bold tracking-wider">EAGLE</h1>
          <p className="text-[11px] text-white/70 tracking-wide">Acquisition Assistant</p>
        </div>
      </div>

      {/* Center: nav links */}
      <nav className="flex items-center gap-1">
        {navLinks.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              isActive(link.href)
                ? 'bg-white/20 text-white'
                : 'text-white/70 hover:bg-white/10 hover:text-white'
            }`}
          >
            {link.icon}
            {link.label}
          </Link>
        ))}
      </nav>

      {/* Right: status + user + sign out */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              backendConnected === null
                ? 'bg-[#D4A843] animate-pulse'
                : backendConnected
                  ? 'bg-[#4CAF50]'
                  : 'bg-[#E53935]'
            }`}
            style={backendConnected ? { boxShadow: '0 0 6px rgba(76,175,80,0.6)' } : {}}
          />
          <span className="text-xs text-white/85">
            {backendConnected === null ? 'Connecting\u2026' : backendConnected ? 'Connected' : 'Offline'}
          </span>
        </div>

        <span className="text-sm text-white/85">{displayName}</span>

        <button
          onClick={handleSignOut}
          className="p-2 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
          title="Sign out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
