'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/auth-context';

interface AuthGuardProps {
    children: React.ReactNode;
}

/**
 * AuthGuard wraps protected routes and redirects unauthenticated users to the
 * login page.  While the auth state is being resolved it renders a centered
 * loading spinner so the underlying page never flashes in an unprotected state.
 */
export default function AuthGuard({ children }: AuthGuardProps) {
    const { isLoading, isAuthenticated } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!isLoading && !isAuthenticated) {
            router.push('/login/');
        }
    }, [isLoading, isAuthenticated, router]);

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-screen bg-gray-50">
                <div className="flex flex-col items-center gap-3">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-blue-600" />
                    <p className="text-sm text-gray-500">Loading...</p>
                </div>
            </div>
        );
    }

    if (!isAuthenticated) {
        // Redirect is handled by the useEffect above.  Render nothing while the
        // navigation transition is in progress to prevent a flash of the
        // protected content.
        return null;
    }

    return <>{children}</>;
}
