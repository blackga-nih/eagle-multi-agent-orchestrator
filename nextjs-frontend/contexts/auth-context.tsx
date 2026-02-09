'use client';

import {
    createContext,
    useContext,
    useState,
    useEffect,
    useCallback,
    useRef,
    ReactNode,
} from 'react';
import {
    CognitoUserPool,
    CognitoUser,
    AuthenticationDetails,
    CognitoUserSession,
} from 'amazon-cognito-identity-js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
    userId: string;
    tenantId: string;
    email: string;
    tier: string;
    roles: string[];
    displayName: string;
}

interface AuthContextValue {
    /** The currently authenticated user, or null when signed out. */
    user: AuthUser | null;
    /** True while the initial session check is in progress. */
    isLoading: boolean;
    /** Convenience boolean derived from `user !== null`. */
    isAuthenticated: boolean;
    /** Returns the current ID token string, refreshing first if needed. */
    getToken: () => Promise<string>;
    /** Authenticate with email and password via Cognito. */
    signIn: (email: string, password: string) => Promise<void>;
    /** Sign out the current user and clear local state. */
    signOut: () => void;
    /** The most recent authentication error message, or null. */
    error: string | null;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const COGNITO_USER_POOL_ID = process.env.NEXT_PUBLIC_COGNITO_USER_POOL_ID ?? '';
const COGNITO_CLIENT_ID = process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID ?? '';
const COGNITO_REGION = process.env.NEXT_PUBLIC_COGNITO_REGION ?? 'us-east-1';

/**
 * When the pool ID is empty or explicitly set to a placeholder value we
 * treat the application as running in "dev mode" -- no real Cognito calls
 * are made and a synthetic mock user is provided instead.
 */
function isDevMode(): boolean {
    return !COGNITO_USER_POOL_ID || COGNITO_USER_POOL_ID.trim() === '';
}

// ---------------------------------------------------------------------------
// Cognito helpers
// ---------------------------------------------------------------------------

/**
 * Build a CognitoUserPool instance. Only call when NOT in dev mode.
 */
function getUserPool(): CognitoUserPool {
    return new CognitoUserPool({
        UserPoolId: COGNITO_USER_POOL_ID,
        ClientId: COGNITO_CLIENT_ID,
    });
}

/**
 * Decode a JWT token payload (the middle Base64-URL segment) and return the
 * parsed claims object. No signature verification is performed here because
 * the Cognito SDK already validates the token before handing it to us.
 */
function decodeJwtPayload(token: string): Record<string, unknown> {
    const payload = token.split('.')[1];
    if (!payload) {
        throw new Error('Invalid JWT: missing payload segment');
    }

    // Base64-URL -> Base64 -> binary string -> JSON
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const jsonString = atob(base64);
    return JSON.parse(jsonString);
}

/**
 * Map raw JWT ID token claims to the application's `AuthUser` shape.
 */
function claimsToUser(claims: Record<string, unknown>): AuthUser {
    const email = (claims['email'] as string) ?? '';
    const groups = (claims['cognito:groups'] as string[]) ?? [];

    return {
        userId: (claims['sub'] as string) ?? '',
        tenantId: (claims['custom:tenant_id'] as string) ?? '',
        email,
        tier: (claims['custom:tier'] as string) ?? 'standard',
        roles: Array.isArray(groups) ? groups : [],
        displayName: email.split('@')[0] || email,
    };
}

/**
 * Extract an AuthUser from a valid CognitoUserSession by decoding the ID
 * token's JWT payload.
 */
function userFromSession(session: CognitoUserSession): AuthUser {
    const idToken = session.getIdToken().getJwtToken();
    const claims = decodeJwtPayload(idToken);
    return claimsToUser(claims);
}

// ---------------------------------------------------------------------------
// Dev-mode mock user
// ---------------------------------------------------------------------------

const DEV_USER: AuthUser = {
    userId: 'dev-user',
    tenantId: 'dev-tenant',
    email: 'dev@example.com',
    tier: 'premium',
    roles: ['admin'],
    displayName: 'dev',
};

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const AuthContext = createContext<AuthContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<AuthUser | null>(null);
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);

    // Keep a ref to the refresh timer so we can clear it on unmount or
    // sign-out without depending on state.
    const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // -------------------------------------------------------------------
    // Token refresh scheduling
    // -------------------------------------------------------------------

    /**
     * Schedule a silent token refresh shortly before the current session's
     * ID token expires. We aim to refresh 5 minutes before expiry to give
     * plenty of buffer.
     */
    const scheduleTokenRefresh = useCallback((session: CognitoUserSession) => {
        // Clear any previously scheduled refresh.
        if (refreshTimerRef.current) {
            clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = null;
        }

        const expiresAt = session.getIdToken().getExpiration(); // seconds since epoch
        const nowSeconds = Math.floor(Date.now() / 1000);
        const BUFFER_SECONDS = 5 * 60; // refresh 5 minutes early
        const delayMs = Math.max((expiresAt - nowSeconds - BUFFER_SECONDS) * 1000, 0);

        refreshTimerRef.current = setTimeout(() => {
            const pool = getUserPool();
            const cognitoUser = pool.getCurrentUser();
            if (!cognitoUser) return;

            cognitoUser.getSession(
                (err: Error | null, refreshedSession: CognitoUserSession | null) => {
                    if (err || !refreshedSession) {
                        // Token refresh failed -- force sign-out so the UI
                        // can prompt the user to re-authenticate.
                        setUser(null);
                        setError('Session expired. Please sign in again.');
                        return;
                    }
                    setUser(userFromSession(refreshedSession));
                    scheduleTokenRefresh(refreshedSession);
                },
            );
        }, delayMs);
    }, []);

    /**
     * Cancel any pending refresh timer.
     */
    const cancelRefreshTimer = useCallback(() => {
        if (refreshTimerRef.current) {
            clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = null;
        }
    }, []);

    // -------------------------------------------------------------------
    // Initial session restoration
    // -------------------------------------------------------------------

    useEffect(() => {
        if (isDevMode()) {
            // Dev mode -- immediately provide the mock user.
            setUser(DEV_USER);
            setIsLoading(false);
            return;
        }

        const pool = getUserPool();
        const cognitoUser = pool.getCurrentUser();

        if (!cognitoUser) {
            setIsLoading(false);
            return;
        }

        cognitoUser.getSession(
            (err: Error | null, session: CognitoUserSession | null) => {
                if (err || !session || !session.isValid()) {
                    setIsLoading(false);
                    return;
                }
                setUser(userFromSession(session));
                scheduleTokenRefresh(session);
                setIsLoading(false);
            },
        );

        // Cleanup the refresh timer when the component unmounts.
        return () => {
            cancelRefreshTimer();
        };
    }, [scheduleTokenRefresh, cancelRefreshTimer]);

    // -------------------------------------------------------------------
    // getToken
    // -------------------------------------------------------------------

    const getToken = useCallback(async (): Promise<string> => {
        if (isDevMode()) {
            return '';
        }

        const pool = getUserPool();
        const cognitoUser = pool.getCurrentUser();

        if (!cognitoUser) {
            throw new Error('No authenticated user');
        }

        return new Promise<string>((resolve, reject) => {
            cognitoUser.getSession(
                (err: Error | null, session: CognitoUserSession | null) => {
                    if (err) {
                        reject(err);
                        return;
                    }
                    if (!session || !session.isValid()) {
                        reject(new Error('Session is invalid'));
                        return;
                    }
                    resolve(session.getIdToken().getJwtToken());
                },
            );
        });
    }, []);

    // -------------------------------------------------------------------
    // signIn
    // -------------------------------------------------------------------

    const signIn = useCallback(
        async (email: string, password: string): Promise<void> => {
            setError(null);

            if (isDevMode()) {
                setUser(DEV_USER);
                return;
            }

            const pool = getUserPool();

            const cognitoUser = new CognitoUser({
                Username: email,
                Pool: pool,
            });

            const authDetails = new AuthenticationDetails({
                Username: email,
                Password: password,
            });

            return new Promise<void>((resolve, reject) => {
                cognitoUser.authenticateUser(authDetails, {
                    onSuccess: (session: CognitoUserSession) => {
                        setUser(userFromSession(session));
                        scheduleTokenRefresh(session);
                        resolve();
                    },
                    onFailure: (err: Error) => {
                        const message =
                            err.message || 'Authentication failed. Please try again.';
                        setError(message);
                        reject(err);
                    },
                    // If Cognito requires a new password challenge, surface it
                    // as an error. A full implementation would present a
                    // "change password" UI here.
                    newPasswordRequired: () => {
                        const msg = 'A new password is required. Please contact support.';
                        setError(msg);
                        reject(new Error(msg));
                    },
                });
            });
        },
        [scheduleTokenRefresh],
    );

    // -------------------------------------------------------------------
    // signOut
    // -------------------------------------------------------------------

    const signOut = useCallback(() => {
        setError(null);
        cancelRefreshTimer();

        if (!isDevMode()) {
            const pool = getUserPool();
            const cognitoUser = pool.getCurrentUser();
            if (cognitoUser) {
                cognitoUser.signOut();
            }
        }

        setUser(null);
    }, [cancelRefreshTimer]);

    // -------------------------------------------------------------------
    // Context value
    // -------------------------------------------------------------------

    const value: AuthContextValue = {
        user,
        isLoading,
        isAuthenticated: user !== null,
        getToken,
        signIn,
        signOut,
        error,
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Access the auth context. Must be called within an `<AuthProvider>`.
 */
export function useAuth(): AuthContextValue {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
