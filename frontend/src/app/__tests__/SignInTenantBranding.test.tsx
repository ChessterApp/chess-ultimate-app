// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import type { Organization } from '@/contexts/organization-types';

// Mock @clerk/nextjs SignIn to a transparent passthrough so we can test the
// surrounding markup without a Clerk runtime.
vi.mock('@clerk/nextjs', () => ({
  SignIn: () => <div data-testid="clerk-signin" />,
}));

// Mock next-intl: useTranslations returns a function that echoes the key.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => `[${key}]`,
}));

// Mock next/image so we don't hit Next's resolver in tests.
vi.mock('next/image', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
    return <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />;
  },
}));

// Drives the page's branding: replaced per-test via mockReturnValue below.
const mockBranding: { current: Organization; isWhiteLabel: boolean } = {
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
  isWhiteLabel: false,
};

vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => mockBranding.current,
  useOrganization: () => ({ org: mockBranding.isWhiteLabel ? mockBranding.current : null, isWhiteLabel: mockBranding.isWhiteLabel }),
}));

import SignInPage from '@/app/sign-in/[[...sign-in]]/page';

describe('Sign-in tenant branding', () => {
  beforeEach(() => {
    cleanup();
  });

  it('renders the Chesster logo + default heading on the apex (no org)', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Chesster',
      logoUrl: null,
    };
    mockBranding.isWhiteLabel = false;
    render(<SignInPage />);
    // Default Chesster logo wins when there's no org logo
    const img = screen.getByAltText('Chesster') as HTMLImageElement;
    expect(img).toBeTruthy();
    // Heading uses the translation key only (no tenant suffix)
    expect(screen.getByText('[auth.signInTitle]')).toBeTruthy();
  });

  it('renders the org logo + tenant heading on a white-label tenant', () => {
    mockBranding.current = {
      ...mockBranding.current,
      name: 'Acme Chess',
      logoUrl: 'https://cdn.example.com/acme/logo.png',
    };
    mockBranding.isWhiteLabel = true;
    render(<SignInPage />);
    const img = screen.getByAltText('Acme Chess') as HTMLImageElement;
    expect(img.src).toContain('cdn.example.com/acme/logo.png');
    expect(screen.getByText('[auth.signInTitle] · Acme Chess')).toBeTruthy();
  });
});
