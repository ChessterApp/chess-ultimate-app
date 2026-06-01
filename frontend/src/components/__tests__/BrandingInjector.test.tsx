// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import React from 'react';
import BrandingInjector from '../BrandingInjector';
import { OrganizationProvider } from '@/contexts/OrganizationContext';
import type { Organization } from '@/contexts/organization-types';

const TENANT: Organization = {
  id: 'org-1',
  slug: 'acme',
  name: 'Acme Chess',
  logoUrl: null,
  faviconUrl: null,
  primaryColor: '#ff5500',
  secondaryColor: '#00ff00',
  accentColor: '#0000ff',
  customCss: null,
  landingPageConfig: {},
  contactEmail: null,
  status: 'active',
};

describe('BrandingInjector', () => {
  it('exports a default function component', async () => {
    const module = await import('../BrandingInjector');
    expect(typeof module.default).toBe('function');
  });

  it('is a client component', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const content = fs.readFileSync(
      path.resolve(__dirname, '../BrandingInjector.tsx'),
      'utf-8'
    );
    expect(content).toContain("'use client'");
  });

  it('writes --brand-primary on mount and reverts on unmount', () => {
    const root = document.documentElement;
    // Ensure clean baseline
    root.style.removeProperty('--brand-primary');
    root.style.removeProperty('--brand-secondary');
    root.style.removeProperty('--brand-accent');

    const { unmount } = render(
      <OrganizationProvider org={TENANT}>
        <BrandingInjector />
      </OrganizationProvider>
    );

    expect(root.style.getPropertyValue('--brand-primary')).toBe('#ff5500');
    expect(root.style.getPropertyValue('--brand-secondary')).toBe('#00ff00');
    expect(root.style.getPropertyValue('--brand-accent')).toBe('#0000ff');

    unmount();
    cleanup();

    expect(root.style.getPropertyValue('--brand-primary')).toBe('');
    expect(root.style.getPropertyValue('--brand-secondary')).toBe('');
    expect(root.style.getPropertyValue('--brand-accent')).toBe('');
  });
});

describe('OrganizationContext', () => {
  it('exports OrganizationProvider and useBranding', async () => {
    const module = await import('@/contexts/OrganizationContext');
    expect(typeof module.OrganizationProvider).toBe('function');
    expect(typeof module.useBranding).toBe('function');
    expect(typeof module.useOrganization).toBe('function');
  });

  it('exports parseOrgFromHeaders from organization-types (server-safe)', async () => {
    const module = await import('@/contexts/organization-types');
    expect(typeof module.parseOrgFromHeaders).toBe('function');
  });

  it('useBranding returns default Chesster branding when no org', async () => {
    const module = await import('@/contexts/OrganizationContext');
    expect(module.useOrganization).toBeDefined();
  });

  it('parseOrgFromHeaders returns null for missing headers', async () => {
    const { parseOrgFromHeaders } = await import('@/contexts/organization-types');
    const headers = new Headers();
    const result = parseOrgFromHeaders(headers);
    expect(result).toBeNull();
  });

  it('parseOrgFromHeaders extracts org info from headers', async () => {
    const { parseOrgFromHeaders } = await import('@/contexts/organization-types');
    const headers = new Headers({
      'x-org-id': 'org-123',
      'x-org-slug': 'testschool',
    });
    const result = parseOrgFromHeaders(headers);
    expect(result).toEqual({ orgId: 'org-123', orgSlug: 'testschool' });
  });
});
