import type { Metadata } from 'next';
import './globals.css';
import { Providers } from './providers';
import { ErrorBoundary } from '@/components/error-boundary';
import { GlobalErrorListener } from '@/components/global-error-listener';

export const metadata: Metadata = {
  title: 'EAGLE - NCI Acquisition Assistant',
  description: 'AI-powered acquisition intake workflow for the Office of Acquisitions',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="antialiased bg-gray-50">
        <GlobalErrorListener />
        <Providers>
          <ErrorBoundary>{children}</ErrorBoundary>
        </Providers>
      </body>
    </html>
  );
}
