'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/auth-context';

export default function LoginPage() {
    const { signIn, isAuthenticated, isLoading, error } = useAuth();
    const router = useRouter();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [localError, setLocalError] = useState<string | null>(null);

    useEffect(() => {
        if (!isLoading && isAuthenticated) {
            router.replace('/');
        }
    }, [isLoading, isAuthenticated, router]);

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault();
        setLocalError(null);
        setSubmitting(true);
        try {
            await signIn(email, password);
            router.replace('/');
        } catch {
            // error is surfaced via auth context `error` field
        } finally {
            setSubmitting(false);
        }
    }

    const displayError = localError || error;

    return (
        <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white flex flex-col">
            {/* Header */}
            <header
                className="bg-[#003366] text-white px-6 flex items-center shrink-0"
                style={{ height: 56, boxShadow: '0 2px 8px rgba(0,51,102,0.3)' }}
            >
                <div className="flex items-center gap-3">
                    <span className="text-[28px] leading-none" style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.3))' }}>
                        🦅
                    </span>
                    <div>
                        <h1 className="text-lg font-bold tracking-wider">EAGLE</h1>
                        <p className="text-[11px] text-white/70 tracking-wide">Acquisition Assistant</p>
                    </div>
                </div>
            </header>

            {/* Login card */}
            <main className="flex-1 flex items-center justify-center p-8">
                <div className="w-full max-w-sm">
                    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
                        <div className="mb-6 text-center">
                            <h2 className="text-2xl font-bold text-[#003366]">Sign in</h2>
                            <p className="text-sm text-gray-500 mt-1">NCI Office of Acquisitions</p>
                        </div>

                        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                            <div>
                                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                                    Email
                                </label>
                                <input
                                    id="email"
                                    type="email"
                                    autoComplete="email"
                                    required
                                    value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                                               focus:outline-none focus:ring-2 focus:ring-[#0066cc] focus:border-transparent
                                               disabled:bg-gray-50 disabled:text-gray-400"
                                    disabled={submitting}
                                    placeholder="you@nih.gov"
                                />
                            </div>

                            <div>
                                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
                                    Password
                                </label>
                                <input
                                    id="password"
                                    type="password"
                                    autoComplete="current-password"
                                    required
                                    value={password}
                                    onChange={e => setPassword(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                                               focus:outline-none focus:ring-2 focus:ring-[#0066cc] focus:border-transparent
                                               disabled:bg-gray-50 disabled:text-gray-400"
                                    disabled={submitting}
                                    placeholder="••••••••"
                                />
                            </div>

                            {displayError && (
                                <div className="rounded-lg bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
                                    {displayError}
                                </div>
                            )}

                            <button
                                type="submit"
                                disabled={submitting || !email || !password}
                                className="w-full py-2.5 px-4 bg-[#003366] hover:bg-[#0066cc] text-white text-sm font-medium
                                           rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {submitting ? 'Signing in…' : 'Sign in'}
                            </button>
                        </form>
                    </div>

                    <p className="text-center text-xs text-gray-400 mt-4">
                        National Cancer Institute · EAGLE v1
                    </p>
                </div>
            </main>
        </div>
    );
}
