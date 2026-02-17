'use client';

import { SimpleChatInterface } from '@/components/chat-simple';
import SimpleHeader from '@/components/chat-simple/simple-header';
import SidebarNav from '@/components/layout/sidebar-nav';
import AuthGuard from '@/components/auth/auth-guard';

export default function ChatPage() {
    return (
        <AuthGuard>
            <div className="flex flex-col h-screen overflow-hidden">
                <SimpleHeader />
                <div className="flex flex-1 min-h-0 overflow-hidden">
                    <SidebarNav />
                    <main className="flex-1 overflow-hidden">
                        <SimpleChatInterface />
                    </main>
                </div>
            </div>
        </AuthGuard>
    );
}
