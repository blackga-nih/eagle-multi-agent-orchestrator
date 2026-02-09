'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Users,
  FileStack,
  Bot,
  Activity,
  TrendingUp,
  Clock,
  DollarSign,
  FileText,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Zap
} from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import {
  MOCK_USERS,
  MOCK_DOCUMENT_TEMPLATES,
  MOCK_AGENT_SKILLS,
  PAST_WORKFLOWS,
  CURRENT_WORKFLOW,
  MOCK_AUDIT_LOGS,
  formatCurrency,
  formatDate,
  formatTime,
} from '@/lib/mock-data';

const allWorkflows = [CURRENT_WORKFLOW, ...PAST_WORKFLOWS];

// Dashboard stats
const stats = [
  {
    label: 'Active Workflows',
    value: allWorkflows.filter(w => w.status === 'in_progress').length,
    change: '+2 this week',
    icon: <Activity className="w-5 h-5" />,
    color: 'bg-blue-500',
  },
  {
    label: 'Total Value',
    value: formatCurrency(allWorkflows.reduce((sum, w) => sum + (w.estimated_value || 0), 0)),
    change: '+$125K this month',
    icon: <DollarSign className="w-5 h-5" />,
    color: 'bg-green-500',
  },
  {
    label: 'Documents Generated',
    value: '47',
    change: '+12 this week',
    icon: <FileText className="w-5 h-5" />,
    color: 'bg-purple-500',
  },
  {
    label: 'Avg. Completion Time',
    value: '4.2 days',
    change: '-0.5 days',
    icon: <Clock className="w-5 h-5" />,
    color: 'bg-amber-500',
  },
];

const quickActions = [
  { label: 'Manage Users', href: '/admin/users', icon: <Users className="w-5 h-5" />, count: MOCK_USERS.length },
  { label: 'Document Templates', href: '/admin/templates', icon: <FileStack className="w-5 h-5" />, count: MOCK_DOCUMENT_TEMPLATES.length },
  { label: 'Agent Skills', href: '/admin/skills', icon: <Bot className="w-5 h-5" />, count: MOCK_AGENT_SKILLS.filter(s => s.is_active).length },
];

export default function AdminDashboard() {
  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="Admin Dashboard"
            description="System overview and management"
          />

          {/* Stats Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {stats.map((stat, i) => (
              <div key={i} className="bg-white rounded-2xl border border-gray-200 p-5">
                <div className="flex items-start justify-between mb-4">
                  <div className={`p-3 rounded-xl ${stat.color} text-white`}>
                    {stat.icon}
                  </div>
                  <span className="text-xs text-green-600 font-medium bg-green-50 px-2 py-1 rounded-full">
                    {stat.change}
                  </span>
                </div>
                <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
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
                      <p className="font-medium text-gray-900 group-hover:text-blue-600 transition-colors">{action.label}</p>
                      <p className="text-xs text-gray-500">{action.count} items</p>
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
                <Link href="/admin" className="text-sm text-blue-600 hover:text-blue-700">View all</Link>
              </div>
              <div className="space-y-4">
                {MOCK_AUDIT_LOGS.slice(0, 5).map((log) => {
                  const actionParts = log.action.split('.');
                  const actionVerb = actionParts[1]?.replace('_', ' ') || log.action;
                  const isAI = Boolean(log.metadata?.agent_id);

                  return (
                    <div key={log.id} className="flex items-start gap-3 p-3 rounded-xl bg-gray-50">
                      <div className={`p-2 rounded-lg ${isAI ? 'bg-purple-100 text-purple-600' : 'bg-blue-100 text-blue-600'}`}>
                        {isAI ? <Zap className="w-4 h-4" /> : <Activity className="w-4 h-4" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900">
                          <span className="font-medium capitalize">{actionVerb}</span>
                          {isAI && <span className="ml-2 text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded-full">AI</span>}
                        </p>
                        <p className="text-xs text-gray-500 truncate">
                          {log.resource_type} • {formatTime(log.timestamp)}
                        </p>
                      </div>
                    </div>
                  );
                })}
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
                  <p className="text-sm text-green-600">Connected, latency 12ms</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-4 bg-amber-50 rounded-xl">
                <AlertCircle className="w-8 h-8 text-amber-500" />
                <div>
                  <p className="font-semibold text-gray-900">API Rate Limit</p>
                  <p className="text-sm text-amber-600">72% used (720/1000)</p>
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
