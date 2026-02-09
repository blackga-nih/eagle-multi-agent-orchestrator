'use client';

import { ReactNode } from 'react';
import { AuthProvider } from '@/contexts/auth-context';
import { SessionProvider } from '@/contexts/session-context';

export function Providers({ children }: { children: ReactNode }) {
    return (
        <AuthProvider>
            <SessionProvider>
                {children}
            </SessionProvider>
        </AuthProvider>
    );
}
