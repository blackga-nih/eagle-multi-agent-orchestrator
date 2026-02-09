'use client';

import { ReactNode, useState } from 'react';

export interface Tab {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: string | number;
}

export interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
  variant?: 'pills' | 'underline' | 'boxed';
}

export function Tabs({ tabs, activeTab, onChange, variant = 'pills' }: TabsProps) {
  const baseClasses = 'flex items-center gap-2 text-sm font-medium transition-all';

  const variantClasses = {
    pills: {
      container: 'flex gap-1 p-1 bg-gray-100 rounded-xl',
      tab: 'px-4 py-2 rounded-lg',
      active: 'bg-white text-blue-600 shadow-sm',
      inactive: 'text-gray-600 hover:text-gray-900',
    },
    underline: {
      container: 'flex gap-6 border-b border-gray-200',
      tab: 'pb-3 border-b-2 -mb-px',
      active: 'border-blue-600 text-blue-600',
      inactive: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
    },
    boxed: {
      container: 'flex gap-2',
      tab: 'px-4 py-2 border rounded-lg',
      active: 'bg-blue-600 text-white border-blue-600',
      inactive: 'bg-white text-gray-600 border-gray-200 hover:border-blue-300',
    },
  };

  const styles = variantClasses[variant];

  return (
    <div className={styles.container}>
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`${baseClasses} ${styles.tab} ${
            activeTab === tab.id ? styles.active : styles.inactive
          }`}
        >
          {tab.icon}
          {tab.label}
          {tab.badge !== undefined && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
              activeTab === tab.id ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'
            }`}>
              {tab.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}

export interface TabPanelProps {
  children: ReactNode;
  isActive: boolean;
}

export function TabPanel({ children, isActive }: TabPanelProps) {
  if (!isActive) return null;
  return <div className="animate-in fade-in duration-200">{children}</div>;
}
