'use client';

import Link from 'next/link';
import { MessageSquare, FileText, Package, Settings } from 'lucide-react';
import SimpleHeader from '@/components/chat-simple/simple-header';
import AuthGuard from '@/components/auth/auth-guard';

const features = [
    {
        icon: MessageSquare,
        title: 'Chat',
        description: 'AI-powered assistant for acquisition tasks, FAR/DFARS search, and document guidance',
        href: '/chat',
        color: 'text-blue-600',
        bgColor: 'bg-blue-50',
    },
    {
        icon: FileText,
        title: 'Document Templates',
        description: 'Browse and use templates for SOWs, IGCEs, acquisition plans, and more',
        href: '/admin/templates',
        color: 'text-emerald-600',
        bgColor: 'bg-emerald-50',
    },
    {
        icon: Package,
        title: 'Acquisition Packages',
        description: 'View, manage, and track your acquisition packages and workflows',
        href: '/workflows',
        color: 'text-purple-600',
        bgColor: 'bg-purple-50',
    },
    {
        icon: Settings,
        title: 'Admin',
        description: 'Dashboard, analytics, user management, and system settings',
        href: '/admin',
        color: 'text-orange-600',
        bgColor: 'bg-orange-50',
    },
];

export default function HomePage() {
    return (
        <AuthGuard>
            <div className="flex flex-col min-h-screen">
                <SimpleHeader />
                <main className="flex-1 flex items-center justify-center p-8 bg-gradient-to-b from-slate-50 to-white">
                    <div className="max-w-6xl w-full flex flex-col lg:flex-row gap-12 lg:gap-16">
                        {/* Left Column - Branding */}
                        <div className="lg:w-2/5 flex flex-col justify-center">
                            <h1 className="text-5xl lg:text-6xl font-bold mb-2">
                                <span className="bg-gradient-to-r from-[#003366] to-[#0066cc] bg-clip-text text-transparent">
                                    EAGLE
                                </span>
                            </h1>
                            <h2 className="text-xl lg:text-2xl font-semibold text-gray-700 mb-6">
                                AI-Powered Acquisition Assistant
                            </h2>
                            <p className="text-gray-600 leading-relaxed mb-4">
                                Empowering the NCI Office of Acquisitions with intelligent tools
                                that streamline procurement workflows, automate document generation,
                                and provide instant access to federal acquisition regulations.
                            </p>
                            <p className="text-gray-500 text-sm">
                                Developed by NCI for acquisition professionals.
                            </p>
                        </div>

                        {/* Right Column - Feature Cards */}
                        <div className="lg:w-3/5 flex flex-col gap-4">
                            {features.map((feature) => (
                                <Link
                                    key={feature.title}
                                    href={feature.href}
                                    className="flex items-start gap-4 p-5 bg-white rounded-xl border border-gray-200
                                             hover:border-gray-300 hover:shadow-md transition-all group"
                                >
                                    <div className={`p-3 rounded-lg ${feature.bgColor}`}>
                                        <feature.icon className={`w-6 h-6 ${feature.color}`} />
                                    </div>
                                    <div className="flex-1">
                                        <h3 className={`font-semibold text-lg ${feature.color} group-hover:underline`}>
                                            {feature.title}
                                        </h3>
                                        <p className="text-gray-600 text-sm mt-1">
                                            {feature.description}
                                        </p>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>
                </main>

                {/* Footer */}
                <footer className="text-center py-4 text-xs text-gray-400 border-t border-gray-100">
                    EAGLE · National Cancer Institute · Powered by Claude (Anthropic SDK)
                </footer>
            </div>
        </AuthGuard>
    );
}
