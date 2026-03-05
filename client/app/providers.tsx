'use client';

import { ReactNode } from 'react';
import { AuthProvider } from '@/contexts/auth-context';
import { SessionProvider } from '@/contexts/session-context';
import FeedbackModal from '@/components/feedback/feedback-modal';

export function Providers({ children }: { children: ReactNode }) {
    return (
        <AuthProvider>
            <SessionProvider>
                {children}
                <FeedbackModal />
            </SessionProvider>
        </AuthProvider>
    );
}
