import createNextIntlPlugin from 'next-intl/plugin';
import crypto from 'crypto';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

// Generate a unique build-time hash for cache-busting static assets.
// This changes on every build, forcing browsers to refetch piece images
// even if they have stale cached responses from before CORP headers were added.
const ASSET_VERSION = crypto.randomBytes(8).toString('hex');

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: 'standalone' as const,
    productionBrowserSourceMaps: process.env.ENABLE_SOURCE_MAPS === 'true',
    env: {
        // Expose build hash to client-side code for cache-busting query params
        NEXT_PUBLIC_ASSET_VERSION: ASSET_VERSION,
    },
    async rewrites() {
        return [
            {
                source: '/api/openings/:path*',
                destination: 'http://localhost:5001/api/openings/:path*',
            },
            {
                source: '/api/chat/analysis',
                destination: 'http://localhost:5001/api/chat/analysis',
            },
            {
                source: '/api/chat/history/:path*',
                destination: 'http://localhost:5001/api/chat/history/:path*',
            },
        ];
    },
    async redirects() {
        return [
            {
                source: '/analyze',
                destination: '/position',
                permanent: true,
            },
        ];
    },
    headers() {
        const headers = [
            {
                // Apply COEP headers to all routes EXCEPT sign-in and sign-up
                // (Clerk needs cross-origin resources that COEP blocks)
                source: '/((?!sign-in|sign-up).*)',
                headers: ENGINE_HEADERS,
            },
            {
                // Other static assets (engines, etc.) — long cache is fine
                source: '/static/:path*',
                headers: ENGINE_HEADERS.concat(
                    {
                        key: 'Cache-Control',
                        value: 'public, max-age=2592000',
                    },
                    {
                        key: 'Cross-Origin-Resource-Policy',
                        value: 'same-origin',
                    },
                ),
            },
            {
                // Static piece images — override the generic /static/* cache policy.
                // Use shorter max-age with must-revalidate instead of immutable,
                // so header changes (like adding CORP) take effect on revalidation.
                // This MUST come after /static/:path* to win the Cache-Control conflict.
                source: '/static/pieces/:path*',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'public, max-age=604800, must-revalidate',
                    },
                ],
            },
            {
                // All Next.js assets need CORP header when COEP is enabled
                source: '/_next/:path*',
                headers: [
                    {
                        key: 'Cross-Origin-Resource-Policy',
                        value: 'same-origin',
                    },
                ],
            },
            {
                // Service worker must never be cached (always fetch fresh copy)
                source: '/sw.js',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'no-store, no-cache, must-revalidate, max-age=0',
                    },
                ],
            },
        ];

        return headers;
    },
};

const ENGINE_HEADERS = [
    {
        key: 'Cross-Origin-Embedder-Policy',
        value: 'require-corp',
    },
    {
        key: 'Cross-Origin-Opener-Policy',
        value: 'same-origin',
    },
];



export default withNextIntl(nextConfig);
