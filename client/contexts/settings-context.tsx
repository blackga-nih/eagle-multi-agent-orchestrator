'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

interface SettingsContextValue {
    adminMode: boolean;
    setAdminMode: (enabled: boolean) => void;
}

const SettingsContext = createContext<SettingsContextValue>({
    adminMode: false,
    setAdminMode: () => {},
});

const ADMIN_MODE_KEY = 'eagle_admin_mode';

export function SettingsProvider({ children }: { children: ReactNode }) {
    const [adminMode, setAdminModeState] = useState(false);

    useEffect(() => {
        try {
            const stored = localStorage.getItem(ADMIN_MODE_KEY);
            if (stored === 'true') setAdminModeState(true);
        } catch {}
    }, []);

    const setAdminMode = useCallback((enabled: boolean) => {
        setAdminModeState(enabled);
        try {
            localStorage.setItem(ADMIN_MODE_KEY, String(enabled));
        } catch {}
    }, []);

    return (
        <SettingsContext.Provider value={{ adminMode, setAdminMode }}>
            {children}
        </SettingsContext.Provider>
    );
}

export function useSettings() {
    return useContext(SettingsContext);
}
