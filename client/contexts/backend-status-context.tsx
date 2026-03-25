'use client';

import { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { checkBackendHealth } from '@/hooks/use-agent-stream';

interface BackendStatusContextValue {
  backendConnected: boolean | null;
}

const BackendStatusContext = createContext<BackendStatusContextValue>({ backendConnected: null });

const CONSECUTIVE_FAILURES_THRESHOLD = 2;

/**
 * Fires a single backend health check on app mount, then re-checks every 30 seconds.
 * Requires 2 consecutive failures before marking disconnected (single-worker dev
 * uvicorn can intermittently stall under load).
 */
export function BackendStatusProvider({ children }: { children: ReactNode }) {
  const [backendConnected, setBackendConnected] = useState<boolean | null>(null);
  const failCount = useRef(0);

  useEffect(() => {
    const check = async () => {
      const ok = await checkBackendHealth();
      if (ok) {
        failCount.current = 0;
        setBackendConnected(true);
      } else {
        failCount.current += 1;
        if (failCount.current >= CONSECUTIVE_FAILURES_THRESHOLD) {
          setBackendConnected(false);
        }
      }
    };
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <BackendStatusContext.Provider value={{ backendConnected }}>
      {children}
    </BackendStatusContext.Provider>
  );
}

export function useBackendStatus(): BackendStatusContextValue {
  return useContext(BackendStatusContext);
}
