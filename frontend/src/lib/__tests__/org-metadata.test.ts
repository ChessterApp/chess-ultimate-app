import { describe, it, expect } from 'vitest';
import { buildMetadata, CHESSTER_DEFAULT_METADATA } from '../org-metadata';
import type { Organization } from '@/contexts/organization-types';

const TENANT_ORG: Organization = {
  id: 'org-uuid',
  slug: 'acme',
  name: 'Acme Chess',
  logoUrl: 'https://cdn.example.com/acme/logo.png',
  faviconUrl: 'https://cdn.example.com/acme/favicon.ico',
  primaryColor: '#ff5500',
  secondaryColor: '#ffffff',
  accentColor: '#000000',
  customCss: null,
  landingPageConfig: {},
  contactEmail: null,
  status: 'active',
  deletionRequestedAt: null,
};

describe('buildMetadata', () => {
  it('returns Chesster defaults byte-for-byte when org is null', () => {
    const meta = buildMetadata(null);
    expect(meta).toBe(CHESSTER_DEFAULT_METADATA);
    expect(meta.title).toBe('Chesster - AI-Powered Chess Training');
    expect(meta.description).toContain('Plug-and-play chess training');
    expect(meta.openGraph?.siteName).toBe('Chesster');
    expect(meta.twitter?.card).toBe('summary_large_image');
    expect((meta.other as Record<string, string>)['theme-color']).toBe('#8209a3ff');
  });

  it('builds title/description/OG/Twitter/theme-color from org', () => {
    const meta = buildMetadata(TENANT_ORG);
    expect(meta.title).toBe('Acme Chess — Chess Training');
    expect(meta.description).toContain('Acme Chess');
    expect(meta.openGraph?.title).toBe('Acme Chess — Chess Training');
    expect(meta.openGraph?.siteName).toBe('Acme Chess');
    const ogImages = meta.openGraph?.images as Array<{ url: string }>;
    expect(ogImages[0].url).toBe(TENANT_ORG.logoUrl);
    const twitterImages = meta.twitter?.images as string[];
    expect(twitterImages[0]).toBe(TENANT_ORG.logoUrl);
    expect((meta.other as Record<string, string>)['theme-color']).toBe('#ff5500');
  });

  it('falls back to the Chesster OG image when the org has no logo', () => {
    const noLogo = { ...TENANT_ORG, logoUrl: null };
    const meta = buildMetadata(noLogo);
    const ogImages = meta.openGraph?.images as Array<{ url: string }>;
    expect(ogImages[0].url).toBe('/static/images/chesster-logo-og.png');
  });
});
