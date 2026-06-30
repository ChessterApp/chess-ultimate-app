// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import type { Organization } from '@/contexts/organization-types';

// next/navigation — only usePathname is consumed.
vi.mock('next/navigation', () => ({
  usePathname: () => '/dashboard',
}));

// usehooks-ts — useLocalStorage returns [value, setter].
vi.mock('usehooks-ts', () => ({
  useLocalStorage: (_key: string, initial: unknown) => [initial, vi.fn()],
}));

// next-intl — both useTranslations + useLocale are used.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => `[${key}]`,
  useLocale: () => 'en',
}));

// Clerk — sidebar mounts UserButton + uses useAuth.
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ isSignedIn: false }),
  UserButton: () => <div data-testid="clerk-userbutton" />,
}));

// next/image — passthrough to a plain img so we can assert alt text.
vi.mock('next/image', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />;
  },
}));

// PrefetchLink — render a plain anchor; we don't care about navigation here.
vi.mock('@/components/PrefetchLink', () => ({
  __esModule: true,
  default: ({ children, ...rest }: { children: React.ReactNode; href: string }) => (
    <a {...rest}>{children}</a>
  ),
}));

// LanguageSwitcher — stub.
vi.mock('@/components/LanguageSwitcher', () => ({
  __esModule: true,
  default: () => <div data-testid="lang-switcher" />,
}));

// Drives branding values per-test.
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

import DesktopSidebar from '@/components/ui/DesktopSidebar';

describe('DesktopSidebar tenant branding', () => {
  beforeEach(() => {
    cleanup();
  });

  it('renders the default Chesster brand when no org is provided (apex non-regression)', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chesster',
      logoUrl: null,
    };
    render(<DesktopSidebar />);
    // Brand label appears with the default name.
    expect(screen.getByText('Chesster')).toBeTruthy();
    // Default Chesster logo is used (next/image stub renders an <img alt>).
    const logo = screen.getByAltText('Chesster') as HTMLImageElement;
    expect(logo.src).toContain('chesster-logo-v3.png');
  });

  it('renders the tenant name + tenant logoUrl when org branding is present', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: 'https://cdn.example.com/chess-empire/logo.png',
    };
    render(<DesktopSidebar />);
    expect(screen.getByText('Chess Empire')).toBeTruthy();
    const logo = screen.getByAltText('Chess Empire') as HTMLImageElement;
    expect(logo.src).toContain('cdn.example.com/chess-empire/logo.png');
  });

  it('falls back to the default Chesster logo when org has no logoUrl', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chess Empire',
      logoUrl: null,
    };
    render(<DesktopSidebar />);
    // Tenant name still shows, but the logo is the bundled Chesster default.
    expect(screen.getByText('Chess Empire')).toBeTruthy();
    const logo = screen.getByAltText('Chess Empire') as HTMLImageElement;
    expect(logo.src).toContain('chesster-logo-v3.png');
  });
});
