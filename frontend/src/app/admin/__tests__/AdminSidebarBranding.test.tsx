// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import type { Organization } from '@/contexts/organization-types';

vi.mock('next/navigation', () => ({
  usePathname: () => '/admin/dashboard',
}));

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, ...props }: { children: React.ReactNode }) => (
    <a {...props}>{children}</a>
  ),
}));

const mockBranding: { current: Organization } = {
  current: {
    id: '',
    slug: '',
    name: 'Chesster',
    logoUrl: null,
    logoMarkUrl: null,
    faviconUrl: null,
    primaryColor: '#1a73e8',
    secondaryColor: '#ffffff',
    accentColor: '#ffd700',
    customCss: null,
    landingPageConfig: {},
    contactEmail: null,
    status: 'active',
    deletionRequestedAt: null,
  },
};

vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => mockBranding.current,
}));

import AdminSidebar from '../AdminSidebar';

describe('AdminSidebar logo mark (32px)', () => {
  beforeEach(() => {
    cleanup();
  });

  // navBody renders in both the desktop and mobile <aside>, so the logo
  // appears twice — assert on the first rendered instance.
  it('prefers the logo mark over the full logo', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: 'https://cdn.example.com/chess-empire/logo.png',
      logoMarkUrl: 'https://cdn.example.com/chess-empire/mark.png',
    };
    render(<AdminSidebar currentRole="owner" />);
    const logo = screen.getAllByAltText('Chess Empire')[0] as HTMLImageElement;
    expect(logo.src).toContain('chess-empire/mark.png');
    expect(logo.className).toContain('object-contain');
  });

  it('falls back to logoUrl when no mark is set', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: 'https://cdn.example.com/chess-empire/logo.png',
      logoMarkUrl: null,
    };
    render(<AdminSidebar currentRole="owner" />);
    const logo = screen.getAllByAltText('Chess Empire')[0] as HTMLImageElement;
    expect(logo.src).toContain('chess-empire/logo.png');
  });

  it('shows the initial-letter placeholder when neither mark nor logo is set', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: null,
      logoMarkUrl: null,
    };
    render(<AdminSidebar currentRole="owner" />);
    expect(screen.queryByAltText('Chess Empire')).toBeNull();
    expect(screen.getAllByText('C').length).toBeGreaterThan(0);
  });
});
