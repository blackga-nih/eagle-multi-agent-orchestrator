'use client';

import { useEffect, useState } from 'react';

export default function NotAuthorizedPage() {
    const [email, setEmail] = useState<string>('');

    useEffect(() => {
        if (typeof window === 'undefined') return;
        const params = new URLSearchParams(window.location.search);
        const e = params.get('email');
        if (e) setEmail(e);
    }, []);

    return (
        <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white flex flex-col">
            <header
                className="bg-[#003366] text-white px-6 flex items-center shrink-0"
                style={{ height: 56 }}
            >
                <div className="flex items-center gap-3">
                    <span className="text-[28px] leading-none">🦅</span>
                    <div>
                        <h1 className="text-lg font-bold tracking-wider">EAGLE</h1>
                        <p className="text-[11px] text-white/70 tracking-wide">Acquisition Assistant</p>
                    </div>
                </div>
            </header>

            <main className="flex-1 flex items-center justify-center p-8">
                <div className="w-full max-w-md">
                    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8 text-center">
                        <h2 className="text-2xl font-bold text-[#003366]">Access not yet granted</h2>
                        <p className="text-sm text-gray-600 mt-3">
                            You signed in successfully{email ? ` as ${email}` : ''}, but your
                            account isn&apos;t provisioned for EAGLE yet.
                        </p>
                        <p className="text-sm text-gray-600 mt-3">
                            Contact the EAGLE administrator to request access. Once you&apos;re
                            added you can sign in again.
                        </p>
                        <a
                            href="/api/auth/logout"
                            className="inline-block mt-6 py-2 px-4 bg-[#003366] hover:bg-[#0066cc] text-white text-sm font-medium rounded-lg transition-colors"
                        >
                            Sign out
                        </a>
                    </div>
                </div>
            </main>
        </div>
    );
}
