'use client';

import { Loader2, Check, X } from 'lucide-react';

export interface AgentStatusProps {
  agentName: string;
  displayName: string;
  message: string;
  status: 'in_progress' | 'complete' | 'error';
}

const iconMap = {
  in_progress: Loader2,
  complete: Check,
  error: X,
};

const iconClassMap = {
  in_progress: 'animate-spin text-muted-foreground',
  complete: 'text-green-500',
  error: 'text-red-500',
};

export function AgentStatus({ displayName, message, status }: AgentStatusProps) {
  const Icon = iconMap[status];
  const iconClass = iconClassMap[status];

  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-1 px-2 bg-muted/50 rounded">
      <Icon className={`h-3 w-3 flex-shrink-0 ${iconClass}`} />
      <span className="font-medium">{displayName}:</span>
      <span>{message}</span>
    </div>
  );
}

export interface AgentStatusListProps {
  statuses: AgentStatusProps[];
}

export function AgentStatusList({ statuses }: AgentStatusListProps) {
  if (statuses.length === 0) return null;

  return (
    <div className="flex flex-col gap-1 my-2">
      {statuses.map((s, i) => (
        <AgentStatus key={`${s.agentName}-${i}`} {...s} />
      ))}
    </div>
  );
}
