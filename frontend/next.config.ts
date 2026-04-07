import createNextIntlPlugin from 'next-intl/plugin';
import crypto from 'crypto';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

// Generate a unique build-time hash for cache-busting static assets.
// This changes on every build, forcing browsers to refetch piece images
// even if they have stale cached responses from before CORP headers were added.
const ASSET_VERSION = crypto.randomBytes(8).toString('hex');

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: process.env.VERCEL ? undefined : ('standalone' as const),
    productionBrowserSourceMaps: process.env.ENABLE_SOURCE_MAPS === 'true',
    env: {
        // Expose build hash to client-side code for cache-busting query params
        NEXT_PUBLIC_ASSET_VERSION: ASSET_VERSION,
    },
    async rewrites() {
        const backendUrl = process.env.VERCEL
            ? 'https://api.chesster.io'
            : 'http://localhost:5001';
        return [
            { source: '/api/openings/:path*', destination: `${backendUrl}/api/openings/:path*` },
            { source: '/api/chat/analysis', destination: `${backendUrl}/api/chat/analysis` },
            { source: '/api/chat/analysis/stream', destination: `${backendUrl}/api/chat/analysis/stream` },
            { source: '/api/chat/history/:path*', destination: `${backendUrl}/api/chat/history/:path*` },
            { source: '/api/courses/:path*', destination: `${backendUrl}/api/courses/:path*` },
            { source: '/api/learn/:path*', destination: `${backendUrl}/api/learn/:path*` },
            { source: '/api/puzzles/:path*', destination: `${backendUrl}/api/puzzles/:path*` },
            { source: '/api/opponent/:path*', destination: `${backendUrl}/api/opponent/:path*` },
            { source: '/api/user/:path*', destination: `${backendUrl}/api/user/:path*` },
            { source: '/api/scoresheet/:path*', destination: `${backendUrl}/api/scoresheet/:path*` },
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
                // Global security headers for all routes
                source: '/:path*',
                headers: SECURITY_HEADERS,
            },
            {
                // ISR pages - Cache for 1 hour with stale-while-revalidate
                source: '/',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'public, s-maxage=3600, stale-while-revalidate=7200',
                    },
                ],
            },
            {
                // COEP only on pages that use SharedArrayBuffer (chess engine)
                source: '/game/:path*',
                headers: ENGINE_HEADERS,
            },
            {
                source: '/position/:path*',
                headers: ENGINE_HEADERS,
            },
            {
                source: '/puzzle/:path*',
                headers: ENGINE_HEADERS,
            },
            {
                source: '/debut/:path*',
                headers: ENGINE_HEADERS,
            },
            {
                source: '/play/:path*',
                headers: ENGINE_HEADERS,
            },
            {
                // Worker is a separate browsing context under COEP — needs both COEP + CORP
                source: '/maia-worker.js',
                headers: [
                    {
                        key: 'Cross-Origin-Embedder-Policy',
                        value: 'require-corp',
                    },
                    {
                        key: 'Cross-Origin-Resource-Policy',
                        value: 'same-origin',
                    },
                ],
            },
            {
                // ORT runtime files — the threaded .mjs spawns sub-workers (pthreads)
                // which are also browsing contexts needing COEP, plus CORP for COEP parent
                source: '/ort/:path*',
                headers: [
                    {
                        key: 'Cross-Origin-Embedder-Policy',
                        value: 'require-corp',
                    },
                    {
                        key: 'Cross-Origin-Resource-Policy',
                        value: 'same-origin',
                    },
                ],
            },
            {
                // Maia model files need CORP header when COEP is enabled
                source: '/maia3/:path*',
                headers: [
                    {
                        key: 'Cross-Origin-Resource-Policy',
                        value: 'same-origin',
                    },
                ],
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
                // Lottie animations need CORP header when COEP is enabled
                source: '/animations/:path*',
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

const SECURITY_HEADERS = [
    {
        key: 'X-Frame-Options',
        value: 'DENY',
    },
    {
        key: 'X-Content-Type-Options',
        value: 'nosniff',
    },
    {
        key: 'Content-Security-Policy',
        value: [
            "default-src 'self'",
            "script-src 'self' 'unsafe-eval' 'unsafe-inline' *.clerk.accounts.dev https://clerk.chesster.io https://challenges.cloudflare.com https://*.posthog.com",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob: https://lichess1.org https://images.clerk.dev https://img.clerk.com",
            "font-src 'self' data:",
            "connect-src 'self' https://chesster.io https://*.chesster.io https://qtzujwiqzbgyhdgulvcd.supabase.co https://*.supabase.co https://*.clerk.accounts.dev https://clerk.chesster.io https://img.clerk.com https://www.chessdb.cn wss://*.supabase.co https://*.posthog.com",
            "frame-src 'self' https://*.clerk.accounts.dev https://challenges.cloudflare.com https://www.youtube.com https://www.youtube-nocookie.com",
            "worker-src 'self' blob:",
            "child-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ].join('; '),
    },
];

export default withNextIntl(nextConfig);
