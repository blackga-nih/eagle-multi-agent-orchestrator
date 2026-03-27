'use client';

import { useState, useEffect, useRef } from 'react';
import { SlashCommand, FALLBACK_COMMANDS, mapBackendCommand } from '@/lib/slash-commands';

/**
 * Fetches the slash command registry from /api/commands and maps
 * backend entries to SlashCommand objects with resolved Lucide icons.
 *
 * Returns FALLBACK_COMMANDS while loading or if the API is unreachable,
 * so the picker is never empty.
 */
export function useCommands(): { commands: SlashCommand[]; loading: boolean } {
  const [commands, setCommands] = useState<SlashCommand[]>(FALLBACK_COMMANDS);
  const [loading, setLoading] = useState(true);
  const fetched = useRef(false);

  useEffect(() => {
    if (fetched.current) return;
    fetched.current = true;

    fetch('/api/commands')
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}`);
        return res.json();
      })
      .then((data: Record<string, unknown>[]) => {
        if (Array.isArray(data) && data.length > 0) {
          setCommands(data.map(mapBackendCommand));
        }
      })
      .catch(() => {
        // Keep fallback commands — picker stays functional
      })
      .finally(() => setLoading(false));
  }, []);

  return { commands, loading };
}
