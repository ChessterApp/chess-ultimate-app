import type { MetadataRoute } from 'next';
import { headers } from 'next/headers';

import { orgFromHost } from '@/lib/org-name-from-host';

// PWA manifest is built per-request from tenant branding so installing the
// site as an app on `chess-empire.chesster.io` shows the partner brand, not
// Chesster. The route is served at `/manifest.webmanifest` by Next.js.
//
// Resolved from the Host header because middleware's matcher intentionally
// skips static-looking paths (including .webmanifest) — so the x-org-slug
// header pipeline isn't available here. We re-derive the org via the same
// 5-minute-cached backend lookup the rest of the white-label stack uses.
//
// Vary: Host + a short max-age are configured in next.config.ts so the same
// browser visiting multiple tenant subdomains doesn't get a poisoned cached
// manifest.

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const h = await headers();
  const host = h.get('x-forwarded-host') || h.get('host');
  const org = await orgFromHost(host);

  const name = org?.name || 'Chesster';
  const themeColor = org?.primaryColor || '#9333ea';
  const backgroundColor = org?.secondaryColor || '#ffffff';
  const iconSrc = org?.logoUrl || '/static/images/chesster-logo.png';

  return {
    name,
    short_name: name,
    description: org
      ? `${name} — chess training powered by Chesster.`
      : 'Learn chess with AI-powered lessons, puzzles, and personalized coaching',
    start_url: '/dashboard',
    display: 'standalone',
    background_color: backgroundColor,
    theme_color: themeColor,
    orientation: 'portrait',
    icons: [
      { src: iconSrc, sizes: '192x192', type: 'image/png' },
      { src: iconSrc, sizes: '512x512', type: 'image/png' },
    ],
  };
}
