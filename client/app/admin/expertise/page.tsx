'use client';

import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import ExpertiseManager from '@/components/settings/expertise-manager';

export default function ExpertisePage() {
  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />
        <main className="flex-1 overflow-y-auto">
          <PageHeader
            title="Expertise Profile"
            description="View and manage how EAGLE learns from your actions"
          />
          <div className="p-6 max-w-4xl">
            <ExpertiseManager />
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
