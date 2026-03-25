'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { MessageSquare, FolderKanban, FileText, Layers, LayoutDashboard, Settings } from 'lucide-react';
import { useAuth } from '@/contexts/auth-context';
import { useBackendStatus } from '@/contexts/backend-status-context';
import { useSettings } from '@/contexts/settings-context';

const allNavLinks = [
    { href: '/chat', label: 'Chat', icon: <MessageSquare className="w-4 h-4" />, admin: false },
    { href: '/workflows', label: 'Packages', icon: <FolderKanban className="w-4 h-4" />, admin: false },
    { href: '/documents', label: 'Documents', icon: <FileText className="w-4 h-4" />, admin: false },
    { href: '/admin/workspaces', label: 'Workspaces', icon: <Layers className="w-4 h-4" />, admin: true },
    { href: '/admin', label: 'Admin', icon: <LayoutDashboard className="w-4 h-4" />, admin: true },
];

export default function SimpleHeader() {
    const pathname = usePathname();
    const { isAuthenticated, user } = useAuth();
    const { backendConnected } = useBackendStatus();
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
        if (href === '/admin') return pathname === '/admin' || (pathname.startsWith('/admin/') && !pathname.startsWith('/admin/workspaces'));
        return pathname.startsWith(href);
    };

    return (
        <header
            className="bg-[#003366] text-white shrink-0 z-10"
            style={{ boxShadow: '0 2px 8px rgba(0,51,102,0.3)' }}
        >
            {/* Row 1: Branding centered, status + settings on the right */}
            <div className="grid grid-cols-3 items-center px-6" style={{ height: 56 }}>
                <div /> {/* empty left column */}
                <div className="flex items-center justify-center gap-3">
                    <span className="text-[28px] leading-none" style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.3))' }}>
                        🦅
                    </span>
                    <div>
                        <h1 className="text-lg font-bold tracking-wider">EAGLE</h1>
                        <p className="text-[11px] text-white/70 tracking-wide">Acquisition Assistant</p>
                    </div>
                </div>
                <div className="flex items-center justify-end gap-3">
                    {/* Backend status */}
                    <div className="flex items-center gap-1" title={backendConnected === null ? 'Connecting to backend…' : backendConnected ? 'Backend connected' : 'Backend offline'}>
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
                        <span className="text-xs text-white/85">API</span>
                    </div>
                    {/* Auth status */}
                    <div className="flex items-center gap-1" title={isAuthenticated ? `Authenticated as ${user?.email}` : 'Not authenticated'}>
                        <span
                            className={`inline-block w-2 h-2 rounded-full ${
                                isAuthenticated ? 'bg-[#4CAF50]' : 'bg-[#E53935]'
                            }`}
                            style={isAuthenticated ? { boxShadow: '0 0 6px rgba(76,175,80,0.6)' } : {}}
                        />
                        <span className="text-xs text-white/85">Auth</span>
                    </div>
                    {/* Settings gear */}
                    <div className="relative" ref={dropdownRef}>
                        <button
                            onClick={() => setSettingsOpen((p) => !p)}
                            className="p-2 text-white/60 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
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
                </div>
            </div>

            {/* Row 2: Nav tabs centered */}
            <nav className="flex items-center justify-center gap-1 px-6 pb-2">
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
        </header>
    );
}
