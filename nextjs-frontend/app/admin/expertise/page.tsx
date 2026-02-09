'use client';

import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import ExpertiseManager from '@/components/settings/expertise-manager';

export default function ExpertisePage() {
  return (
    <AuthGuard>
    <div className="min-h-screen flex bg-gray-50">
      <SidebarNav />
      <main className="flex-1 ml-[200px]">
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
