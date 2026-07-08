import type { MetadataRoute } from 'next';
import { headers } from 'next/headers';

import { orgFromHost, type BrandFromHost } from '@/lib/org-name-from-host';

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

const DEFAULT_ICON = '/static/images/chesster-logo.png';

// Chess Empire's maskable icons are uploaded as `.../icon-maskable-512.png`
// with a `-192` sibling in the same storage folder. When pwaIconUrl follows
// that convention we can declare the smaller entry too so launchers don't
// downscale the 512 for the home-screen icon.
const MASKABLE_512_SUFFIX = 'icon-maskable-512.png';

// Declare each icon's `type` from the asset's real extension so we don't
// advertise image/png for a .jpg — the previous bug, which made Chrome reject
// the icon because its bytes didn't match the declared MIME type.
function mimeFromUrl(url: string): string {
  const path = url.split('?')[0].toLowerCase();
  if (path.endsWith('.jpg') || path.endsWith('.jpeg')) return 'image/jpeg';
  if (path.endsWith('.webp')) return 'image/webp';
  if (path.endsWith('.svg')) return 'image/svg+xml';
  if (path.endsWith('.ico')) return 'image/x-icon';
  if (path.endsWith('.gif')) return 'image/gif';
  return 'image/png';
}

function buildIcons(org: BrandFromHost | null): MetadataRoute.Manifest['icons'] {
  // Dedicated PWA icon: emit both `any` and `maskable` purposes so Android
  // renders it edge-to-edge inside its adaptive mask.
  if (org?.pwaIconUrl) {
    const src = org.pwaIconUrl;
    const type = mimeFromUrl(src);
    const icons = [
      { src, sizes: '512x512', type, purpose: 'any' as const },
      { src, sizes: '512x512', type, purpose: 'maskable' as const },
    ];
    if (src.endsWith(MASKABLE_512_SUFFIX)) {
      const src192 = src.slice(0, -MASKABLE_512_SUFFIX.length) + 'icon-maskable-192.png';
      icons.unshift(
        { src: src192, sizes: '192x192', type: 'image/png', purpose: 'any' as const },
        { src: src192, sizes: '192x192', type: 'image/png', purpose: 'maskable' as const },
      );
    }
    return icons;
  }

  // No dedicated icon: fall back to the org logo (or the bundled default) and
  // declare its actual content type rather than a hardcoded image/png.
  const src = org?.logoUrl || DEFAULT_ICON;
  const type = mimeFromUrl(src);
  return [
    { src, sizes: '192x192', type },
    { src, sizes: '512x512', type },
  ];
}

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const h = await headers();
  const host = h.get('x-forwarded-host') || h.get('host');
  const org = await orgFromHost(host);

  const name = org?.name || 'Chesster';
  const themeColor = org?.primaryColor || '#9333ea';
  const backgroundColor = org?.secondaryColor || '#ffffff';

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
    icons: buildIcons(org),
  };
}
