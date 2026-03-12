'use client';

import { createContext, useContext, useRef, useCallback, ReactNode } from 'react';

export interface FeedbackSnapshot {
  messages: { role: string; content: string; id?: string; timestamp?: unknown }[];
  lastMessageId: string | null;
}

interface FeedbackContextValue {
  getSnapshot: () => FeedbackSnapshot;
  setSnapshot: (snapshot: FeedbackSnapshot) => void;
}

const FeedbackContext = createContext<FeedbackContextValue | null>(null);

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const snapshotRef = useRef<FeedbackSnapshot>({ messages: [], lastMessageId: null });

  const setSnapshot = useCallback((snapshot: FeedbackSnapshot) => {
    snapshotRef.current = snapshot;
  }, []);

  const getSnapshot = useCallback(() => snapshotRef.current, []);

  return (
    <FeedbackContext.Provider value={{ getSnapshot, setSnapshot }}>
      {children}
    </FeedbackContext.Provider>
  );
}

export function useFeedback() {
  const ctx = useContext(FeedbackContext);
  if (!ctx) throw new Error('useFeedback must be used within FeedbackProvider');
  return ctx;
}
