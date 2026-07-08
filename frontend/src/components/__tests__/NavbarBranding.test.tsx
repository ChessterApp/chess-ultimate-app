// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import type { Organization } from '@/contexts/organization-types';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'en',
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ isSignedIn: false }),
  UserButton: () => <div data-testid="clerk-userbutton" />,
}));

vi.mock('next/image', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />;
  },
}));

vi.mock('@/components/LanguageSwitcher', () => ({
  __esModule: true,
  default: () => <div data-testid="lang-switcher" />,
}));

const mockBranding: { current: Organization } = {
  current: {
    id: '',
    slug: '',
    name: 'Chesster',
    logoUrl: null,
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
  useOrganization: () => ({ org: null, isWhiteLabel: false }),
}));

import NavBar from '@/components/Navbar';

describe('NavBar tenant branding', () => {
  beforeEach(() => {
    cleanup();
  });

  it('renders the default Chesster brand when no org is provided (apex non-regression)', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chesster',
      logoUrl: null,
    };
    render(<NavBar />);
    // Default brand name is in the click target.
    expect(screen.getByRole('button', { name: /Chesster/ })).toBeTruthy();
    const logo = screen.getByAltText('Chesster') as HTMLImageElement;
    expect(logo.src).toContain('chesster-logo-v3.png');
  });

  it('renders the tenant name + tenant logoUrl when org branding is present', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: 'https://cdn.example.com/chess-empire/logo.png',
    };
    render(<NavBar />);
    expect(screen.getByRole('button', { name: /Chess Empire/ })).toBeTruthy();
    const logo = screen.getByAltText('Chess Empire') as HTMLImageElement;
    expect(logo.src).toContain('cdn.example.com/chess-empire/logo.png');
  });

  it('falls back to the default Chesster logo when org has no logoUrl', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: null,
    };
    render(<NavBar />);
    expect(screen.getByRole('button', { name: /Chess Empire/ })).toBeTruthy();
    const logo = screen.getByAltText('Chess Empire') as HTMLImageElement;
    expect(logo.src).toContain('chesster-logo-v3.png');
  });

  it('prefers the logo mark over the full logo at this small (28px) site', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: 'https://cdn.example.com/chess-empire/logo.png',
      logoMarkUrl: 'https://cdn.example.com/chess-empire/mark.png',
    };
    render(<NavBar />);
    const logo = screen.getByAltText('Chess Empire') as HTMLImageElement;
    expect(logo.src).toContain('chess-empire/mark.png');
    // Small sites render with object-contain (not object-cover).
    expect(logo.className).toContain('object-contain');
  });

  it('falls back to logoUrl when no logo mark is set', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: 'https://cdn.example.com/chess-empire/logo.png',
      logoMarkUrl: null,
    };
    render(<NavBar />);
    const logo = screen.getByAltText('Chess Empire') as HTMLImageElement;
    expect(logo.src).toContain('chess-empire/logo.png');
  });
});
