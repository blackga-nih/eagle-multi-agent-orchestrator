'use client';

import { ReactNode } from 'react';
import { AuthProvider } from '@/contexts/auth-context';
import { SessionProvider } from '@/contexts/session-context';
import { ChatRuntimeProvider } from '@/contexts/chat-runtime-context';
import { BackendStatusProvider } from '@/contexts/backend-status-context';
import { FeedbackProvider } from '@/contexts/feedback-context';
import { SettingsProvider } from '@/contexts/settings-context';
import FeedbackModal from '@/components/feedback/feedback-modal';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <SettingsProvider>
        <SessionProvider>
          <ChatRuntimeProvider>
            <BackendStatusProvider>
              <FeedbackProvider>
                {children}
                <FeedbackModal />
              </FeedbackProvider>
            </BackendStatusProvider>
          </ChatRuntimeProvider>
        </SessionProvider>
      </SettingsProvider>
    </AuthProvider>
  );
}
