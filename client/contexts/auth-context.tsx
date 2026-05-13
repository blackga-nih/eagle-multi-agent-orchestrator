'use client';

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useRef,
    useState,
    ReactNode,
} from 'react';

// ---------------------------------------------------------------------------
// Auth model
//
// The backend issues a local HS256 session JWT after Microsoft Entra OIDC
// callback (see fcasvp pattern). We store that token in sessionStorage and
// send it as `Authorization: Bearer <token>` on every fetch.
//
// Any time we lack a valid token we redirect the browser to
// `/api/auth/login`, which 302s to Entra. After successful login the backend
// 302s back to `${ENTRA_POST_LOGIN_PATH}?token=…`; we capture and strip the
// token from the URL on mount.
// ---------------------------------------------------------------------------

export interface AuthUser {
    userId: string;
    tenantId: string;
    email: string;
    tier: string;
    roles: string[];
    isAdmin: boolean;
    displayName: string;
}

interface AuthContextValue {
    user: AuthUser | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    /** Returns the current session token (or empty string in dev mode). */
    getToken: () => Promise<string>;
    /** Kick off the Entra OIDC redirect. The legacy email/password params are accepted
     *  but ignored — login no longer happens in-app. */
    signIn: (email?: string, password?: string) => Promise<void>;
    signOut: () => void;
    error: string | null;
}

// ---------------------------------------------------------------------------
// Storage helpers
// ---------------------------------------------------------------------------

const SESSION_TOKEN_KEY = 'eagle_auth_token';
const REDIRECT_GUARD_KEY = 'eagle_auth_login_attempt';
const RETURN_TO_KEY = 'eagle_auth_return_to';
const REDIRECT_GUARD_MS = 10_000;

/**
 * Paths the auto-redirect skips. We must never bounce *to* /not-authorized
 * (the user is already there for a reason) or *from* /api routes.
 */
const PUBLIC_PATHS = new Set(['/not-authorized']);

function shouldGuardPath(pathname: string): boolean {
    if (PUBLIC_PATHS.has(pathname)) return false;
    if (pathname.startsWith('/api/')) return false;
    return true;
}

function getStoredToken(): string | null {
    if (typeof window === 'undefined') return null;
    return window.sessionStorage.getItem(SESSION_TOKEN_KEY);
}

function setStoredToken(token: string): void {
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, token);
}

function clearStoredToken(): void {
    if (typeof window === 'undefined') return;
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
}

/**
 * Returns true when running without a backend Entra config — i.e. local dev
 * with no captured session token. Existing callers used this to skip
 * auth-required UI in DEV_MODE.
 */
export function isDevMode(): boolean {
    if (typeof window === 'undefined') return false;
    const isLocal =
        window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1';
    return isLocal && !getStoredToken();
}

/**
 * Broadcast a session-expired event so non-React layers (stream managers,
 * dynamic imports) can clear local state. Clears the stored token and
 * dispatches a `eagle:session-expired` window event.
 */
export function fireSessionExpired(): void {
    if (typeof window === 'undefined') return;
    clearStoredToken();
    window.dispatchEvent(new CustomEvent('eagle:session-expired'));
}

/**
 * After OIDC callback the backend redirects to `${ENTRA_POST_LOGIN_PATH}?token=…`.
 * Capture the token, store it, and strip it from the URL via
 * `history.replaceState` so the page doesn't hang on to it.
 *
 * If a `RETURN_TO_KEY` was stashed before the redirect, navigate the browser
 * to that original path so users land back on whatever they bookmarked.
 */
function captureTokenFromUrl(): string | null {
    if (typeof window === 'undefined') return null;
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (!token) return null;
    setStoredToken(token);
    params.delete('token');
    const cleaned = params.toString();
    const newUrl = cleaned
        ? `${window.location.pathname}?${cleaned}`
        : window.location.pathname;
    window.history.replaceState({}, '', newUrl);

    const returnTo = window.sessionStorage.getItem(RETURN_TO_KEY);
    if (returnTo && returnTo !== window.location.pathname + window.location.search) {
        window.sessionStorage.removeItem(RETURN_TO_KEY);
        // Hard navigation so server components and middleware re-evaluate
        // with the freshly stored token.
        window.location.replace(returnTo);
    }
    return token;
}

/** Decode a JWT payload without verifying the signature. */
function decodeJwtPayload<T = Record<string, unknown>>(token: string): T | null {
    try {
        const segment = token.split('.')[1];
        if (!segment) return null;
        const base64 = segment.replace(/-/g, '+').replace(/_/g, '/');
        return JSON.parse(atob(base64)) as T;
    } catch {
        return null;
    }
}

interface SessionClaims {
    sub?: string;
    email?: string;
    tenant_id?: string;
    tier?: string;
    is_admin?: boolean;
    display_name?: string;
    exp?: number;
    iat?: number;
}

function userFromClaims(claims: SessionClaims): AuthUser {
    const email = claims.email ?? '';
    return {
        userId: claims.sub ?? email,
        tenantId: claims.tenant_id ?? '',
        email,
        tier: claims.tier ?? 'basic',
        roles: claims.is_admin ? ['admin'] : [],
        isAdmin: !!claims.is_admin,
        displayName:
            claims.display_name || (email.includes('@') ? email.split('@')[0] : email) || 'User',
    };
}

function isClaimsExpired(claims: SessionClaims): boolean {
    if (typeof claims.exp !== 'number') return false;
    return Date.now() / 1000 >= claims.exp;
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

function redirectToEntraLogin() {
    if (typeof window === 'undefined') return;
    const last = window.sessionStorage.getItem(REDIRECT_GUARD_KEY);
    const now = Date.now();
    if (last && now - Number(last) < REDIRECT_GUARD_MS) {
        // Avoid infinite redirect loops if the backend keeps bouncing us back.
        return;
    }
    // Remember where the user was so we can land them back here after auth.
    const here = window.location.pathname + window.location.search;
    if (shouldGuardPath(window.location.pathname)) {
        window.sessionStorage.setItem(RETURN_TO_KEY, here);
    }
    window.sessionStorage.setItem(REDIRECT_GUARD_KEY, String(now));
    window.location.href = '/api/auth/login';
}

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const initRef = useRef(false);

    const handleClaims = useCallback((claims: SessionClaims | null) => {
        if (!claims || isClaimsExpired(claims) || !(claims.email || claims.sub)) {
            clearStoredToken();
            setUser(null);
            return false;
        }
        setUser(userFromClaims(claims));
        return true;
    }, []);

    useEffect(() => {
        if (initRef.current) return;
        initRef.current = true;

        const fromUrl = captureTokenFromUrl();
        const token = fromUrl || getStoredToken();
        const onPublicPath =
            typeof window !== 'undefined' &&
            !shouldGuardPath(window.location.pathname);

        const ensureSession = async (): Promise<boolean> => {
            // Even without a stored token, the backend may resolve a session
            // via DEV_MODE or a server-side cookie. Ask it before redirecting.
            try {
                const res = await fetch('/api/auth/authenticate');
                if (!res.ok) return false;
                const data = await res.json();
                if (data?.result === 'Success') {
                    setUser({
                        userId: data.user_id,
                        tenantId: data.tenant_id ?? '',
                        email: data.email ?? '',
                        tier: data.tier ?? 'basic',
                        roles: data.is_admin ? ['admin'] : [],
                        isAdmin: !!data.is_admin,
                        displayName: data.display_name || data.email || 'User',
                    });
                    return true;
                }
            } catch {
                // fall through
            }
            return false;
        };

        if (!token) {
            (async () => {
                const ok = await ensureSession();
                if (ok) {
                    setIsLoading(false);
                    return;
                }
                if (onPublicPath) {
                    // /not-authorized and friends render without a session.
                    setIsLoading(false);
                    return;
                }
                // Whole site is gated — bounce to Entra and remember where
                // we came from so the post-callback redirect can return us.
                redirectToEntraLogin();
            })();
            return;
        }

        const claims = decodeJwtPayload<SessionClaims>(token);
        if (!handleClaims(claims)) {
            // Token decoded but expired/invalid — drop it and re-auth.
            if (onPublicPath) {
                setIsLoading(false);
                return;
            }
            redirectToEntraLogin();
            return;
        }
        // Clear the loop guard once we have a good session.
        if (typeof window !== 'undefined') {
            window.sessionStorage.removeItem(REDIRECT_GUARD_KEY);
        }
        setIsLoading(false);
    }, [handleClaims]);

    const getToken = useCallback(async (): Promise<string> => {
        const token = getStoredToken();
        if (!token) return '';
        const claims = decodeJwtPayload<SessionClaims>(token);
        if (!claims || isClaimsExpired(claims)) {
            clearStoredToken();
            setUser(null);
            return '';
        }
        return token;
    }, []);

    const signIn = useCallback(async (): Promise<void> => {
        setError(null);
        // No in-app credential form anymore. Hand control to the OIDC flow.
        redirectToEntraLogin();
    }, []);

    const signOut = useCallback(() => {
        setError(null);
        clearStoredToken();
        setUser(null);
        if (typeof window !== 'undefined') {
            window.location.href = '/api/auth/logout';
        }
    }, []);

    const value: AuthContextValue = {
        user,
        isLoading,
        isAuthenticated: user !== null,
        getToken,
        signIn,
        signOut,
        error,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
    const ctx = useContext(AuthContext);
    if (!ctx) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return ctx;
}
