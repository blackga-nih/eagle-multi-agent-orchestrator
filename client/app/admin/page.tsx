'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  Users,
  FileStack,
  Bot,
  Activity,
  Clock,
  DollarSign,
  FileText,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Zap,
  FlaskConical,
  GitBranch,
  PenTool,
  Layers,
  Loader2,
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import { formatCurrency, formatTime } from '@/lib/format-helpers';
import { useAuth } from '@/contexts/auth-context';

interface DashboardStats {
  active_users?: number;
  total_sessions?: number;
  total_cost?: number;
  active_packages?: number;
  total_value?: number;
  documents_generated?: number;
}

const quickActions = [
  { label: 'Workspaces', href: '/admin/workspaces', icon: <Layers className="w-5 h-5" /> },
  { label: 'Test Results', href: '/admin/tests', icon: <FlaskConical className="w-5 h-5" /> },
  { label: 'Eval Viewer', href: '/admin/eval', icon: <GitBranch className="w-5 h-5" /> },
  { label: 'AI Diagram Studio', href: '/admin/diagrams', icon: <PenTool className="w-5 h-5" /> },
  { label: 'Manage Users', href: '/admin/users', icon: <Users className="w-5 h-5" /> },
  {
    label: 'Document Templates',
    href: '/admin/templates',
    icon: <FileStack className="w-5 h-5" />,
  },
  { label: 'Agent Skills', href: '/admin/skills', icon: <Bot className="w-5 h-5" /> },
];

export default function AdminDashboard() {
  const { getToken } = useAuth();
  const [dashboardData, setDashboardData] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      try {
        const token = await getToken();
        const res = await fetch('/api/admin/dashboard', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok && !cancelled) {
          setDashboardData(await res.json());
        }
      } catch {
        // Backend unavailable
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [getToken]);

  const stats = [
    {
      label: 'Active Packages',
      value: dashboardData?.active_packages ?? '-',
      icon: <Activity className="w-5 h-5" />,
      color: 'bg-blue-500',
    },
    {
      label: 'Total Value',
      value: dashboardData?.total_value ? formatCurrency(dashboardData.total_value) : '-',
      icon: <DollarSign className="w-5 h-5" />,
      color: 'bg-green-500',
    },
    {
      label: 'Documents Generated',
      value: dashboardData?.documents_generated ?? '-',
      icon: <FileText className="w-5 h-5" />,
      color: 'bg-purple-500',
    },
    {
      label: 'Active Users',
      value: dashboardData?.active_users ?? '-',
      icon: <Users className="w-5 h-5" />,
      color: 'bg-amber-500',
    },
  ];

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen bg-gray-50">
        <TopNav />

        <main className="flex-1 overflow-y-auto">
          <div className="p-8">
            <PageHeader title="Admin Dashboard" description="System overview and management" />

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              {stats.map((stat, i) => (
                <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className={`p-3 rounded-xl ${stat.color} text-white`}>{stat.icon}</div>
                  </div>
                  <p className="text-2xl font-bold text-gray-900">
                    {loading ? <Loader2 className="w-5 h-5 animate-spin inline" /> : stat.value}
                  </p>
                  <p className="text-sm text-gray-500">{stat.label}</p>
                </div>
              ))}
            </div>

            {/* Quick Actions + Recent Activity */}
            <div className="grid lg:grid-cols-3 gap-6 mb-8">
              {/* Quick Actions */}
              <div className="bg-white rounded-2xl border border-gray-200 p-6">
                <h3 className="font-bold text-gray-900 mb-4">Quick Actions</h3>
                <div className="space-y-3">
                  {quickActions.map((action, i) => (
                    <Link
                      key={i}
                      href={action.href}
                      className="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-50 transition-colors group"
                    >
                      <div className="p-2 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-blue-100 transition-colors">
                        {action.icon}
                      </div>
                      <div className="flex-1">
                        <p className="font-medium text-gray-900 group-hover:text-blue-600 transition-colors">
                          {action.label}
                        </p>
                      </div>
                      <ArrowRight className="w-4 h-4 text-gray-400 group-hover:text-blue-600 transition-colors" />
                    </Link>
                  ))}
                </div>
              </div>

              {/* Recent Activity */}
              <div className="lg:col-span-2 bg-white rounded-2xl border border-gray-200 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-bold text-gray-900">Recent Activity</h3>
                </div>
                <div className="text-center py-8">
                  <Activity className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-500">Activity log coming soon.</p>
                  <p className="text-xs text-gray-400 mt-1">
                    Session and document events will appear here.
                  </p>
                </div>
              </div>
            </div>

            {/* System Health */}
            <div className="bg-white rounded-2xl border border-gray-200 p-6">
              <h3 className="font-bold text-gray-900 mb-4">System Health</h3>
              <div className="grid md:grid-cols-3 gap-4">
                <div className="flex items-center gap-3 p-4 bg-green-50 rounded-xl">
                  <CheckCircle2 className="w-8 h-8 text-green-500" />
                  <div>
                    <p className="font-semibold text-gray-900">AI Services</p>
                    <p className="text-sm text-green-600">All agents operational</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 bg-green-50 rounded-xl">
                  <CheckCircle2 className="w-8 h-8 text-green-500" />
                  <div>
                    <p className="font-semibold text-gray-900">Database</p>
                    <p className="text-sm text-green-600">Connected</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 p-4 bg-green-50 rounded-xl">
                  <CheckCircle2 className="w-8 h-8 text-green-500" />
                  <div>
                    <p className="font-semibold text-gray-900">Backend</p>
                    <p className="text-sm text-green-600">
                      {loading ? 'Checking...' : dashboardData ? 'Connected' : 'Unavailable'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </AuthGuard>
  );
}
