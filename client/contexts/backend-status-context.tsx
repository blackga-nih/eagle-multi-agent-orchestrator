'use client';

import { createContext, useContext, useState, useEffect, useRef, useMemo, ReactNode } from 'react';
import { checkBackendHealth } from '@/hooks/use-agent-stream';

interface BackendStatusContextValue {
  backendConnected: boolean | null;
  gitSha: string | null;
  startedAt: string | null;
  pid: number | null;
  /** Date.now() when we first observed a new startedAt value (flash trigger). */
  lastRestartAt: number | null;
}

const BackendStatusContext = createContext<BackendStatusContextValue>({
  backendConnected: null,
  gitSha: null,
  startedAt: null,
  pid: null,
  lastRestartAt: null,
});

const CONSECUTIVE_FAILURES_THRESHOLD = 2;

/**
 * Fires a single backend health check on app mount, then re-checks every 30 seconds.
 * Requires 2 consecutive failures before marking disconnected (single-worker dev
 * uvicorn can intermittently stall under load).
 *
 * Also surfaces backend identity (git_sha, started_at, pid) so the UI can show
 * which backend build is running, and flashes briefly when started_at changes
 * (i.e. uvicorn --reload picked up a code edit).
 */
export function BackendStatusProvider({ children }: { children: ReactNode }) {
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const [gitSha, setGitSha] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<string | null>(null);
  const [pid, setPid] = useState<number | null>(null);
  const [lastRestartAt, setLastRestartAt] = useState<number | null>(null);
  const failCount = useRef(0);
  const lastStartedAtRef = useRef<string | null>(null);

  useEffect(() => {
    const check = async () => {
      const health = await checkBackendHealth();
      if (health.ok) {
        failCount.current = 0;
        setBackendConnected((prev) => (prev === true ? prev : true));
        if (health.gitSha !== undefined) setGitSha(health.gitSha);
        if (health.pid !== undefined) setPid(health.pid);
        if (health.startedAt !== undefined) {
          // Only flash when we've seen a DIFFERENT non-null value before.
          // First observation on mount should not trigger a restart flash.
          const prev = lastStartedAtRef.current;
          if (prev !== null && prev !== health.startedAt) {
            setLastRestartAt(Date.now());
          }
          lastStartedAtRef.current = health.startedAt;
          setStartedAt(health.startedAt);
        }
      } else {
        failCount.current += 1;
        if (failCount.current >= CONSECUTIVE_FAILURES_THRESHOLD) {
          setBackendConnected((prev) => (prev === false ? prev : false));
        }
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  const value = useMemo(
    () => ({ backendConnected, gitSha, startedAt, pid, lastRestartAt }),
    [backendConnected, gitSha, startedAt, pid, lastRestartAt],
  );

  return <BackendStatusContext.Provider value={value}>{children}</BackendStatusContext.Provider>;
}

export function useBackendStatus(): BackendStatusContextValue {
  return useContext(BackendStatusContext);
}
