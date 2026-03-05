'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { MessageSquare, FolderKanban, FileText, Layers, LayoutDashboard } from 'lucide-react';
import { checkBackendHealth } from '@/hooks/use-agent-stream';

const navLinks = [
    { href: '/chat', label: 'Chat', icon: <MessageSquare className="w-4 h-4" /> },
    { href: '/workflows', label: 'Packages', icon: <FolderKanban className="w-4 h-4" /> },
    { href: '/documents', label: 'Documents', icon: <FileText className="w-4 h-4" /> },
    { href: '/admin/workspaces', label: 'Workspaces', icon: <Layers className="w-4 h-4" /> },
    { href: '/admin', label: 'Admin', icon: <LayoutDashboard className="w-4 h-4" /> },
];

export default function SimpleHeader() {
    const pathname = usePathname();
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
        if (href === '/admin') return pathname === '/admin' || (pathname.startsWith('/admin/') && !pathname.startsWith('/admin/workspaces'));
        return pathname.startsWith(href);
    };

    return (
        <header
            className="bg-[#003366] text-white shrink-0 z-10"
            style={{ boxShadow: '0 2px 8px rgba(0,51,102,0.3)' }}
        >
            {/* Row 1: Branding centered, status on the right */}
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
                <div className="flex items-center justify-end gap-1.5">
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
