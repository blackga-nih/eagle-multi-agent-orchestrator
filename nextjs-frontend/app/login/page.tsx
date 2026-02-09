'use client';

import { useState, useEffect, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/auth-context';

// ---------------------------------------------------------------------------
// NCI EAGLE Login Page
// ---------------------------------------------------------------------------

export default function LoginPage() {
  const router = useRouter();
  const { signIn, isAuthenticated, isLoading, error: authError } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Redirect to home if user is already authenticated.
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push('/');
    }
  }, [isLoading, isAuthenticated, router]);

  // Surface auth-context errors in the form.
  useEffect(() => {
    if (authError) {
      setFormError(authError);
    }
  }, [authError]);

  // Handle form submission.
  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);

    if (!email.trim() || !password.trim()) {
      setFormError('Please enter both email and password.');
      return;
    }

    setIsSubmitting(true);
    try {
      await signIn(email.trim(), password);
      router.push('/');
    } catch (err: unknown) {
      // The auth context already sets its own `error` state, but we also
      // capture the thrown error so the form can display it immediately
      // without waiting for a re-render cycle.
      if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Sign-in failed. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // -----------------------------------------------------------------
  // Loading state while auth is being checked
  // -----------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="flex flex-col items-center gap-4">
          {/* EAGLE logo mark */}
          <div className="w-14 h-14 rounded-xl bg-gradient-to-br from-[#004971] to-[#003149] flex items-center justify-center shadow-lg">
            <span className="text-white text-2xl font-bold tracking-tight">E</span>
          </div>
          <div className="flex items-center gap-2">
            <svg
              className="animate-spin h-5 w-5 text-[#003149]"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span className="text-sm text-gray-500">Checking authentication...</span>
          </div>
        </div>
      </div>
    );
  }

  // Don't render the login form if the user is already authenticated
  // (the useEffect above will redirect them).
  if (isAuthenticated) {
    return null;
  }

  // -----------------------------------------------------------------
  // Login form
  // -----------------------------------------------------------------

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <div className="w-full max-w-md">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">

          {/* Header band */}
          <div className="bg-[#0D2648] px-8 py-6">
            <div className="flex items-center gap-4">
              {/* EAGLE logo */}
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-[#004971] to-[#0B6ED7] flex items-center justify-center shadow-md flex-shrink-0">
                <span className="text-white text-xl font-bold tracking-tight">E</span>
              </div>
              <div>
                <h1 className="text-white text-xl font-bold tracking-tight">EAGLE</h1>
                <p className="text-blue-200 text-sm">Office of Acquisitions</p>
              </div>
            </div>
          </div>

          {/* Form body */}
          <div className="px-8 py-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Sign in to your account</h2>
            <p className="text-sm text-gray-500 mb-6">
              Enter your NCI credentials to continue.
            </p>

            {/* Error banner */}
            {formError && (
              <div
                className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-[#BB0E3D]"
                role="alert"
              >
                {formError}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Email field */}
              <div>
                <label
                  htmlFor="login-email"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  Email address
                </label>
                <input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isSubmitting}
                  placeholder="you@nih.gov"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-[#0B6ED7] focus:ring-2 focus:ring-[#0B6ED7]/20 focus:outline-none transition-colors disabled:bg-gray-50 disabled:cursor-not-allowed"
                />
              </div>

              {/* Password field */}
              <div>
                <label
                  htmlFor="login-password"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  Password
                </label>
                <input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                  placeholder="Enter your password"
                  className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-[#0B6ED7] focus:ring-2 focus:ring-[#0B6ED7]/20 focus:outline-none transition-colors disabled:bg-gray-50 disabled:cursor-not-allowed"
                />
              </div>

              {/* Submit button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full rounded-lg bg-[#003149] px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#004971] focus:outline-none focus:ring-2 focus:ring-[#0B6ED7]/40 focus:ring-offset-2 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg
                      className="animate-spin h-4 w-4 text-white"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    Signing in...
                  </span>
                ) : (
                  'Sign in'
                )}
              </button>
            </form>
          </div>

          {/* Footer */}
          <div className="border-t border-gray-100 bg-gray-50 px-8 py-4">
            <p className="text-xs text-gray-400 text-center">
              National Cancer Institute &mdash; Office of Acquisitions
            </p>
          </div>
        </div>

        {/* Below-card notice */}
        <p className="mt-6 text-center text-xs text-gray-400">
          This is a U.S. Government information system. Unauthorized access is prohibited.
        </p>
      </div>
    </div>
  );
}
