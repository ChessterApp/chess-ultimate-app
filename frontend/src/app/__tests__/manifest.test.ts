import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { BrandFromHost } from '@/lib/org-name-from-host';

// The PWA manifest is built per-request from tenant branding. These tests
// exercise the icon-selection rule (pwaIconUrl → maskable, else logoUrl with a
// correct MIME type) without spinning up Next. See logo-mark-brief.md Phase B/D.

const orgRef: { current: BrandFromHost | null } = { current: null };

vi.mock('next/headers', () => ({
  headers: async () => ({
    get: (k: string) => (k === 'host' ? 'chess-empire.chesster.io' : null),
  }),
}));

vi.mock('@/lib/org-name-from-host', () => ({
  orgFromHost: async () => orgRef.current,
}));

import manifest from '../manifest';

const BASE: BrandFromHost = {
  name: 'Chess Empire',
  slug: 'chess-empire',
  logoUrl: null,
  logoMarkUrl: null,
  pwaIconUrl: null,
  faviconUrl: null,
  primaryColor: '#9333ea',
  secondaryColor: '#ffffff',
};

type Icon = { src: string; sizes?: string; type?: string; purpose?: string };

const STORAGE_512 =
  'https://qtzujwiqzbgyhdgulvcd.supabase.co/storage/v1/object/public/org-branding/52b5682c/icon-maskable-512.png';

describe('manifest icons', () => {
  beforeEach(() => {
    orgRef.current = null;
  });

  it('uses pwaIconUrl with maskable + any purposes when set', async () => {
    orgRef.current = { ...BASE, logoUrl: 'https://x/logo.jpg', pwaIconUrl: STORAGE_512 };
    const m = await manifest();
    const icons = m.icons as Icon[];
    const purposes = icons.filter(i => i.src === STORAGE_512).map(i => i.purpose);
    expect(purposes).toContain('any');
    expect(purposes).toContain('maskable');
    // Every pwa-icon entry is declared as a PNG, matching the actual bytes.
    for (const icon of icons) expect(icon.type).toBe('image/png');
  });

  it('adds a 192 sibling entry when pwaIconUrl follows the maskable-512 convention', async () => {
    orgRef.current = { ...BASE, pwaIconUrl: STORAGE_512 };
    const m = await manifest();
    const icons = m.icons as Icon[];
    const src192 = STORAGE_512.replace('icon-maskable-512.png', 'icon-maskable-192.png');
    expect(icons.some(i => i.src === src192 && i.sizes === '192x192')).toBe(true);
    expect(icons.some(i => i.src === STORAGE_512 && i.sizes === '512x512')).toBe(true);
  });

  it('emits only the 512 entry when pwaIconUrl does not follow the convention', async () => {
    const custom = 'https://cdn.example.com/icon.png';
    orgRef.current = { ...BASE, pwaIconUrl: custom };
    const m = await manifest();
    const icons = m.icons as Icon[];
    expect(icons.every(i => i.sizes === '512x512')).toBe(true);
    expect(icons.some(i => i.sizes === '192x192')).toBe(false);
  });

  it('falls back to logoUrl and declares its ACTUAL mime type (jpg → image/jpeg)', async () => {
    orgRef.current = { ...BASE, logoUrl: 'https://cdn.example.com/logo.jpg' };
    const m = await manifest();
    const icons = m.icons as Icon[];
    // The old bug hardcoded image/png for a .jpg — assert that is fixed.
    for (const icon of icons) expect(icon.type).toBe('image/jpeg');
    expect(icons.map(i => i.sizes).sort()).toEqual(['192x192', '512x512']);
  });

  it('uses the bundled default icon (png) when there is no org logo', async () => {
    orgRef.current = { ...BASE, logoUrl: null };
    const m = await manifest();
    const icons = m.icons as Icon[];
    for (const icon of icons) {
      expect(icon.src).toBe('/static/images/chesster-logo.png');
      expect(icon.type).toBe('image/png');
    }
  });

  it('declares image/svg+xml for an svg logo', async () => {
    orgRef.current = { ...BASE, logoUrl: 'https://cdn.example.com/logo.svg' };
    const m = await manifest();
    const icons = m.icons as Icon[];
    for (const icon of icons) expect(icon.type).toBe('image/svg+xml');
  });
});
