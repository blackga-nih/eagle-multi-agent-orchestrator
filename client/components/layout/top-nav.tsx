'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LogOut,
  MessageSquare,
  FolderKanban,
  FileText,
  BookOpen,
  LayoutDashboard,
  Layers,
  Settings,
} from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import { useBackendStatus } from '@/contexts/backend-status-context';
import { useSettings } from '@/contexts/settings-context';

const allNavLinks = [
  { href: '/chat', label: 'Chat', icon: <MessageSquare className="w-4 h-4" />, admin: false },
  {
    href: '/packages',
    label: 'Packages',
    icon: <FolderKanban className="w-4 h-4" />,
    admin: false,
  },
  { href: '/documents', label: 'Documents', icon: <FileText className="w-4 h-4" />, admin: false },
  {
    href: '/knowledge-base',
    label: 'Knowledge Base',
    icon: <BookOpen className="w-4 h-4" />,
    admin: false,
  },
  {
    href: '/admin/workspaces',
    label: 'Workspaces',
    icon: <Layers className="w-4 h-4" />,
    admin: true,
  },
  { href: '/admin', label: 'Admin', icon: <LayoutDashboard className="w-4 h-4" />, admin: true },
];

export default function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isAuthenticated, signOut } = useAuth();
  const { backendConnected, gitSha, startedAt, pid, lastRestartAt } = useBackendStatus();

  // Flash amber for 3 seconds after a backend restart is detected.
  const [isFlashing, setIsFlashing] = useState(false);
  useEffect(() => {
    if (lastRestartAt === null) return;
    setIsFlashing(true);
    const t = setTimeout(() => setIsFlashing(false), 3000);
    return () => clearTimeout(t);
  }, [lastRestartAt]);

  const backendTooltip = useMemo(() => {
    if (backendConnected === null) return 'Connecting to backend…';
    if (!backendConnected) return 'Backend offline';
    const parts = ['Backend connected'];
    if (gitSha) parts.push(`git ${gitSha}`);
    if (startedAt) parts.push(`started ${startedAt}`);
    if (pid !== null) parts.push(`PID ${pid}`);
    return parts.join(' · ');
  }, [backendConnected, gitSha, startedAt, pid]);

  const backendLabel =
    backendConnected === null
      ? 'API…'
      : backendConnected && gitSha
        ? gitSha.slice(0, 7)
        : 'API';
  const { adminMode, setAdminMode } = useSettings();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const navLinks = adminMode ? allNavLinks : allNavLinks.filter((l) => !l.admin);

  // Close dropdown on outside click
  useEffect(() => {
    if (!settingsOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setSettingsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [settingsOpen]);

  const isActive = (href: string) => {
    if (href === '/chat') return pathname === '/chat';
    if (href === '/admin')
      return (
        pathname === '/admin' ||
        (pathname.startsWith('/admin/') && !pathname.startsWith('/admin/workspaces'))
      );
    return pathname.startsWith(href);
  };

  const displayName = user?.displayName || user?.email || 'User';

  const handleSignOut = async () => {
    // signOut() does a hard navigation to /api/auth/logout (which 302s to
    // Entra's OIDC logout). No client-side router push needed afterward.
    await signOut();
  };

  return (
    <header
      className="bg-white text-gray-900 px-6 flex items-center justify-between shrink-0 z-10 border-b border-gray-200"
      style={{ height: 56, boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
    >
      {/* Left: branding */}
      <div className="flex items-center">
        <Image
          src="/nci-logo.svg"
          alt="National Cancer Institute — EAGLE"
          width={280}
          height={36}
          priority
        />
      </div>

      {/* Center: nav links */}
      <nav className="flex items-center gap-1">
        {navLinks.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              isActive(link.href)
                ? 'bg-nci-blue/10 text-nci-blue'
                : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
            }`}
          >
            {link.icon}
            {link.label}
          </Link>
        ))}
      </nav>

      {/* Right: status + user + settings + sign out */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          {/* Backend status */}
          <div className="flex items-center gap-1" title={backendTooltip}>
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                backendConnected === null || isFlashing
                  ? 'bg-[#D4A843] animate-pulse'
                  : backendConnected
                    ? 'bg-[#4CAF50]'
                    : 'bg-[#E53935]'
              }`}
              style={
                backendConnected && !isFlashing
                  ? { boxShadow: '0 0 6px rgba(76,175,80,0.6)' }
                  : {}
              }
            />
            <span className="text-xs font-mono text-gray-700">{backendLabel}</span>
          </div>
          {/* Auth status */}
          <div
            className="flex items-center gap-1"
            title={isAuthenticated ? `Authenticated as ${user?.email}` : 'Not authenticated'}
          >
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                isAuthenticated ? 'bg-[#4CAF50]' : 'bg-[#E53935]'
              }`}
              style={isAuthenticated ? { boxShadow: '0 0 6px rgba(76,175,80,0.6)' } : {}}
            />
            <span className="text-xs text-gray-700">Auth</span>
          </div>
        </div>

        <span className="text-sm text-gray-700">{displayName}</span>

        {/* Settings gear */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setSettingsOpen((p) => !p)}
            className="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            title="Settings"
          >
            <Settings className="w-4 h-4" />
          </button>
          {settingsOpen && (
            <div className="absolute right-0 top-full mt-1 w-52 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-50">
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
          className="p-2 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
          title="Sign out"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
