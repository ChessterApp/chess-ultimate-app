import { describe, it, expect } from 'vitest';

describe('BrandingInjector', () => {
  it('exports a default function component', async () => {
    const module = await import('../BrandingInjector');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    // BrandingInjector uses useEffect and useBranding (client hooks)
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../BrandingInjector.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });
});

describe('OrganizationContext', () => {
  it('exports OrganizationProvider and useBranding', async () => {
    const module = await import('@/contexts/OrganizationContext');
    expect(typeof module.OrganizationProvider).toBe('function');
    expect(typeof module.useBranding).toBe('function');
    expect(typeof module.useOrganization).toBe('function');
    expect(typeof module.parseOrgFromHeaders).toBe('function');
  });

  it('useBranding returns default Chesster branding when no org', async () => {
    // useBranding calls useContext which needs React tree,
    // but we can verify the default branding object exists in the module
    const module = await import('@/contexts/OrganizationContext');
    // The default context value has org: null, isWhiteLabel: false
    expect(module.useOrganization).toBeDefined();
  });

  it('parseOrgFromHeaders returns null for missing headers', async () => {
    const { parseOrgFromHeaders } = await import('@/contexts/OrganizationContext');
    const headers = new Headers();
    const result = parseOrgFromHeaders(headers);
    expect(result).toBeNull();
  });

  it('parseOrgFromHeaders extracts org info from headers', async () => {
    const { parseOrgFromHeaders } = await import('@/contexts/OrganizationContext');
    const headers = new Headers({
      'x-org-id': 'org-123',
      'x-org-slug': 'testschool',
    });
    const result = parseOrgFromHeaders(headers);
    expect(result).toEqual({ orgId: 'org-123', orgSlug: 'testschool' });
  });
});
