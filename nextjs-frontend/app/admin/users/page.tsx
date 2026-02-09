'use client';

import { useState } from 'react';
import { Plus, Search, MoreVertical, Mail, Phone, Building, Shield, Edit2, Trash2, UserCheck } from 'lucide-react';
import AuthGuard from '@/components/auth/auth-guard';
import SidebarNav from '@/components/layout/sidebar-nav';
import PageHeader from '@/components/layout/page-header';
import Badge from '@/components/ui/badge';
import Modal from '@/components/ui/modal';
import DataTable, { Column } from '@/components/ui/data-table';
import {
  MOCK_USERS,
  MOCK_USER_GROUPS,
  getUserRoleColor,
  getUserRoleLabel,
  formatDate,
} from '@/lib/mock-data';
import { User, UserRole } from '@/types/schema';

export default function UsersPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showGroupsModal, setShowGroupsModal] = useState(false);

  const filteredUsers = MOCK_USERS.filter(u =>
    u.display_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const columns: Column<User>[] = [
    {
      key: 'display_name',
      header: 'User',
      sortable: true,
      render: (user) => (
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-semibold text-xs">
            {user.display_name.split(' ').map(n => n[0]).join('')}
          </div>
          <div>
            <p className="font-medium text-gray-900">{user.display_name}</p>
            <p className="text-xs text-gray-500">{user.email}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      sortable: true,
      render: (user) => (
        <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${getUserRoleColor(user.role)}`}>
          {getUserRoleLabel(user.role)}
        </span>
      ),
    },
    {
      key: 'division',
      header: 'Division',
      sortable: true,
      render: (user) => (
        <span className="text-sm text-gray-600">{user.division || '-'}</span>
      ),
    },
    {
      key: 'updated_at',
      header: 'Last Active',
      sortable: true,
      render: (user) => (
        <span className="text-sm text-gray-500">{formatDate(user.updated_at)}</span>
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
          <button className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <AuthGuard>
    <div className="flex h-screen bg-gray-50">
      <SidebarNav />

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
          <DataTable
            columns={columns}
            data={filteredUsers}
            keyField="id"
            onRowClick={(user) => setSelectedUser(user)}
            emptyMessage="No users found"
          />
        </div>
      </main>

      {/* User Detail/Edit Modal */}
      <Modal
        isOpen={!!selectedUser}
        onClose={() => setSelectedUser(null)}
        title={selectedUser ? `Edit User: ${selectedUser.display_name}` : 'User Details'}
        size="md"
        footer={
          <div className="flex justify-between">
            <button className="flex items-center gap-2 px-4 py-2 text-red-600 hover:text-red-700">
              <Trash2 className="w-4 h-4" />
              Delete User
            </button>
            <div className="flex gap-3">
              <button
                onClick={() => setSelectedUser(null)}
                className="px-4 py-2 text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                Save Changes
              </button>
            </div>
          </div>
        }
      >
        {selectedUser && (
          <form className="space-y-4">
            <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-xl mb-4">
              <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-purple-500 rounded-full flex items-center justify-center text-white font-bold text-xl">
                {selectedUser.display_name.split(' ').map(n => n[0]).join('')}
              </div>
              <div>
                <p className="font-semibold text-gray-900">{selectedUser.display_name}</p>
                <p className="text-sm text-gray-500">{selectedUser.email}</p>
                <p className="text-xs text-gray-400">ID: {selectedUser.id}</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                <input
                  type="text"
                  defaultValue={selectedUser.display_name}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                <select
                  defaultValue={selectedUser.role}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white"
                >
                  <option value="requestor">Requestor</option>
                  <option value="co">Contracting Officer</option>
                  <option value="cor">COR</option>
                  <option value="budget_analyst">Budget Analyst</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
              <input
                type="email"
                defaultValue={selectedUser.email}
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Division</label>
                <input
                  type="text"
                  defaultValue={selectedUser.division}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                <input
                  type="tel"
                  defaultValue={selectedUser.phone}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
                />
              </div>
            </div>
          </form>
        )}
      </Modal>

      {/* Groups Modal */}
      <Modal
        isOpen={showGroupsModal}
        onClose={() => setShowGroupsModal(false)}
        title="User Groups"
        size="lg"
      >
        <div className="space-y-4">
          {MOCK_USER_GROUPS.map((group) => (
            <div key={group.id} className="p-4 border border-gray-200 rounded-xl">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h4 className="font-semibold text-gray-900">{group.name}</h4>
                  <p className="text-xs text-gray-500">{group.description}</p>
                </div>
                <button className="p-2 text-gray-400 hover:text-gray-600">
                  <Edit2 className="w-4 h-4" />
                </button>
              </div>
              <div className="flex flex-wrap gap-1 mt-3">
                {group.permissions.map((perm, i) => (
                  <span key={i} className="text-[10px] bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
                    {perm.replace('_', ' ')}
                  </span>
                ))}
              </div>
            </div>
          ))}
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
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Add User
            </button>
          </div>
        }
      >
        <form className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
              <input
                type="text"
                placeholder="Jane"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Last Name *</label>
              <input
                type="text"
                placeholder="Smith"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
            <input
              type="email"
              placeholder="jane.smith@nih.gov"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role *</label>
              <select className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 bg-white">
                <option value="">Select role...</option>
                <option value="requestor">Requestor</option>
                <option value="co">Contracting Officer</option>
                <option value="cor">COR</option>
                <option value="budget_analyst">Budget Analyst</option>
                <option value="admin">Administrator</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Division</label>
              <input
                type="text"
                placeholder="e.g., Center for Cancer Research"
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
            <input
              type="tel"
              placeholder="301-555-0123"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">User Groups</label>
            <div className="flex flex-wrap gap-2 mt-2">
              {MOCK_USER_GROUPS.map((group) => (
                <label key={group.id} className="flex items-center gap-2 p-2 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                  <input type="checkbox" className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                  <span className="text-sm text-gray-700">{group.name}</span>
                </label>
              ))}
            </div>
          </div>
        </form>
      </Modal>
    </div>
    </AuthGuard>
  );
}
