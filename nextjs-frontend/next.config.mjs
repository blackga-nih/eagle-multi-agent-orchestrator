import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone',
    trailingSlash: true,
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
            {
                source: '/api/health',
                destination: `${backendUrl}/api/health`,
            },
        ];
    },
};

export default nextConfig;
