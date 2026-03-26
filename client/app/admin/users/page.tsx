'use client';

import { useState, useEffect } from 'react';
import { Plus, Search, Shield, Edit2, Trash2, Loader2 } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';
import PageHeader from '@/components/layout/page-header';
import Modal from '@/components/ui/modal';
import DataTable, { Column } from '@/components/ui/data-table';
import {
  getUserRoleColor,
  getUserRoleLabel,
  formatDate,
} from '@/lib/format-helpers';
import { useAuth } from '@/contexts/auth-context';

interface BackendUser {
  user_id: string;
  email?: string;
  display_name?: string;
  role?: string;
  division?: string;
  session_count?: number;
  total_cost?: string;
  last_active?: string;
}

export default function UsersPage() {
  const { getToken } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [users, setUsers] = useState<BackendUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState<BackendUser | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showGroupsModal, setShowGroupsModal] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadUsers() {
      try {
        const token = await getToken();
        const res = await fetch('/api/admin/users', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok && !cancelled) {
          const data = await res.json();
          setUsers(data.users || data || []);
        }
      } catch {
        // Backend unavailable
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadUsers();
    return () => { cancelled = true; };
  }, [getToken]);

  const filteredUsers = users.filter(u => {
    const name = u.display_name || u.user_id || '';
    const email = u.email || '';
    return name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      email.toLowerCase().includes(searchQuery.toLowerCase());
  });

  const columns: Column<BackendUser>[] = [
    {
      key: 'user_id',
      header: 'User',
      sortable: true,
      render: (user) => (
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-semibold text-xs">
            {(user.display_name || user.user_id || '?').substring(0, 2).toUpperCase()}
          </div>
          <div>
            <p className="font-medium text-gray-900">{user.display_name || user.user_id}</p>
            {user.email && <p className="text-xs text-gray-500">{user.email}</p>}
          </div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      sortable: true,
      render: (user) => {
        const role = user.role as import('@/types/schema').UserRole | undefined;
        return role ? (
          <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${getUserRoleColor(role)}`}>
            {getUserRoleLabel(role)}
          </span>
        ) : (
          <span className="text-xs text-gray-400">-</span>
        );
      },
    },
    {
      key: 'session_count',
      header: 'Sessions',
      sortable: true,
      render: (user) => (
        <span className="text-sm text-gray-600">{user.session_count ?? '-'}</span>
      ),
    },
    {
      key: 'last_active',
      header: 'Last Active',
      sortable: true,
      render: (user) => (
        <span className="text-sm text-gray-500">{user.last_active ? formatDate(user.last_active) : '-'}</span>
      ),
    },
    {
      key: 'actions',
      header: '',
      width: '80px',
      render: (user) => (
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); setSelectedUser(user); }}
            className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
          >
            <Edit2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <AuthGuard>
    <div className="flex flex-col h-screen bg-gray-50">
      <TopNav />

      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          <PageHeader
            title="User Management"
            description="Manage system users and permissions"
            breadcrumbs={[
              { label: 'Admin', href: '/admin' },
              { label: 'Users' },
            ]}
            actions={
              <div className="flex gap-3">
                <button
                  onClick={() => setShowGroupsModal(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl font-medium hover:bg-gray-50 transition-colors"
                >
                  <Shield className="w-4 h-4" />
                  Groups
                </button>
                <button
                  onClick={() => setShowNewModal(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl font-medium hover:bg-blue-700 transition-colors shadow-md shadow-blue-200"
                >
                  <Plus className="w-4 h-4" />
                  Add User
                </button>
              </div>
            }
          />

          {/* Search */}
          <div className="mb-6">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Search users..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          {/* Users Table */}
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500 mr-2" />
              <span className="text-gray-500">Loading users...</span>
            </div>
          ) : (
            <DataTable
              columns={columns}
              data={filteredUsers}
              keyField="user_id"
              onRowClick={(user) => setSelectedUser(user)}
              emptyMessage="No users found. User data is sourced from AWS Cognito."
            />
          )}
        </div>
      </main>

      {/* User Detail Modal */}
      <Modal
        isOpen={!!selectedUser}
        onClose={() => setSelectedUser(null)}
        title={selectedUser ? `User: ${selectedUser.display_name || selectedUser.user_id}` : 'User Details'}
        size="md"
        footer={
          <div className="flex justify-end">
            <button
              onClick={() => setSelectedUser(null)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Close
            </button>
          </div>
        }
      >
        {selectedUser && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-xl">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-bold text-xl">
                {(selectedUser.display_name || selectedUser.user_id || '?').substring(0, 2).toUpperCase()}
              </div>
              <div>
                <p className="font-semibold text-gray-900">{selectedUser.display_name || selectedUser.user_id}</p>
                {selectedUser.email && <p className="text-sm text-gray-500">{selectedUser.email}</p>}
                <p className="text-xs text-gray-400">ID: {selectedUser.user_id}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Sessions</label>
                <p className="mt-1 text-sm font-medium">{selectedUser.session_count ?? '-'}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Total Cost</label>
                <p className="mt-1 text-sm font-medium">{selectedUser.total_cost ? `$${selectedUser.total_cost}` : '-'}</p>
              </div>
              <div>
                <label className="text-xs text-gray-500 uppercase tracking-wide">Last Active</label>
                <p className="mt-1 text-sm font-medium">{selectedUser.last_active ? formatDate(selectedUser.last_active) : '-'}</p>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* Groups Modal */}
      <Modal
        isOpen={showGroupsModal}
        onClose={() => setShowGroupsModal(false)}
        title="User Groups"
        size="lg"
      >
        <div className="text-center py-8">
          <Shield className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">User groups are managed in AWS Cognito.</p>
          <p className="text-xs text-gray-400 mt-1">Contact your administrator for group changes.</p>
        </div>
      </Modal>

      {/* New User Modal */}
      <Modal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        title="Add New User"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowNewModal(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800"
            >
              Cancel
            </button>
          </div>
        }
      >
        <div className="text-center py-8">
          <p className="text-sm text-gray-500">User provisioning is handled through AWS Cognito.</p>
          <p className="text-xs text-gray-400 mt-1">Users are automatically registered on first login.</p>
        </div>
      </Modal>
    </div>
    </AuthGuard>
  );
}
