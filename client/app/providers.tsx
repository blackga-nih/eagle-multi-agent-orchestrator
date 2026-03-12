'use client';

import { ReactNode } from 'react';
import { AuthProvider } from '@/contexts/auth-context';
import { SessionProvider } from '@/contexts/session-context';
import { BackendStatusProvider } from '@/contexts/backend-status-context';
import FeedbackModal from '@/components/feedback/feedback-modal';

export function Providers({ children }: { children: ReactNode }) {
    return (
        <AuthProvider>
            <SessionProvider>
                <BackendStatusProvider>
                    {children}
                    <FeedbackModal />
                </BackendStatusProvider>
            </SessionProvider>
        </AuthProvider>
    );
}
