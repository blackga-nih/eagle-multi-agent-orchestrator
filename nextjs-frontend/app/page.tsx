import ChatInterface from '@/components/chat/chat-interface';
import SidebarNav from '@/components/layout/sidebar-nav';
import AuthGuard from '@/components/auth/auth-guard';

export default function Home() {
    return (
        <AuthGuard>
            <div className="flex h-screen bg-gray-50">
                <SidebarNav />
                <main className="flex-1 overflow-hidden">
                    <ChatInterface />
                </main>
            </div>
        </AuthGuard>
    );
}
