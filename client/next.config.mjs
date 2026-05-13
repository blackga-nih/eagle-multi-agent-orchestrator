import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  eslint: { ignoreDuringBuilds: true },
  trailingSlash: false,
  // Feedback screenshots can exceed the default 1MB body limit
  serverActions: { bodySizeLimit: '5mb' },
  images: {
    unoptimized: true,
  },
  outputFileTracingRoot: __dirname,
  async rewrites() {
    const backendUrl = process.env.FASTAPI_URL || 'http://localhost:8000';
    return [
      {
        source: '/ws/:path*',
        destination: `${backendUrl}/ws/:path*`,
      },
      // Auth router lives on FastAPI (Entra OIDC + local session JWT).
      // No Next.js Route Handlers cover /api/auth/*, so proxy directly.
      {
        source: '/api/auth/:path*',
        destination: `${backendUrl}/api/auth/:path*`,
      },
    ];
  },
};

export default nextConfig;
