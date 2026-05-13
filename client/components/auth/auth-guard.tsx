'use client';

import { useAuth } from '@/contexts/auth-context';

interface AuthGuardProps {
  children: React.ReactNode;
}

/**
 * AuthGuard wraps protected routes. Unauthenticated users never see the
 * children — the AuthProvider auto-redirects to `/api/auth/login` (which
 * 302s to Entra) on mount, preserving the originally requested path so we
 * land back on it after the OIDC round-trip.
 *
 * This component just renders a loading spinner while the auth state
 * resolves and stays out of the way once it has.
 */
export default function AuthGuard({ children }: AuthGuardProps) {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading || !isAuthenticated) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
          <p className="text-sm text-gray-500">Loading...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
