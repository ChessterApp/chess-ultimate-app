// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import {
  TenantLanding,
  resolveLandingPageConfig,
} from '../TenantLanding';

vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ isSignedIn: false, isLoaded: true }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, ...rest }: React.PropsWithChildren<{ href: string }>) =>
    React.createElement('a', { href, ...rest }, children),
}));

const ORG = {
  name: 'Almaty Chess Academy',
  slug: 'almaty',
  logoUrl: null,
  primaryColor: '#0066ff',
  secondaryColor: '#ffffff',
  accentColor: '#ffd700',
} as const;

describe('resolveLandingPageConfig', () => {
  it('falls back to defaults when config is empty', () => {
    const out = resolveLandingPageConfig({}, { name: 'Acme' });
    expect(out.hero_title).toBe('Welcome to Acme');
    expect(out.cta_text).toBe('Sign in');
    expect(out.cta_href).toBe('/sign-in');
  });

  it('respects explicit hero_title', () => {
    const out = resolveLandingPageConfig(
      { hero_title: 'Train like a GM' },
      { name: 'Acme' },
    );
    expect(out.hero_title).toBe('Train like a GM');
  });

  it('aliases hero_headline to hero_title', () => {
    const out = resolveLandingPageConfig(
      { hero_headline: 'Headline wins' },
      { name: 'Acme' },
    );
    expect(out.hero_title).toBe('Headline wins');
  });

  it('passes through cta_href + cta_text overrides', () => {
    const out = resolveLandingPageConfig(
      { cta_text: 'Join us', cta_href: '/join' },
      { name: 'Acme' },
    );
    expect(out.cta_text).toBe('Join us');
    expect(out.cta_href).toBe('/join');
  });
});

describe('TenantLanding renderer', () => {
  it('renders the org name in the header', () => {
    const { getByText } = render(
      <TenantLanding hideAuthIsland org={ORG} config={null} />,
    );
    expect(getByText('Almaty Chess Academy')).toBeTruthy();
  });

  it('renders the default hero when landing_page_config is null', () => {
    const { getByRole } = render(
      <TenantLanding hideAuthIsland org={ORG} config={null} />,
    );
    const h1 = getByRole('heading', { level: 1 });
    expect(h1.textContent).toBe('Welcome to Almaty Chess Academy');
  });

  it('renders a custom hero title from landing_page_config', () => {
    const { getByRole } = render(
      <TenantLanding
        hideAuthIsland
        org={ORG}
        config={{ hero_title: 'Become a master', hero_subtitle: 'Coaches!' }}
      />,
    );
    const h1 = getByRole('heading', { level: 1 });
    expect(h1.textContent).toBe('Become a master');
  });

  it('uses CSS variables so BrandingInjector cascades through', () => {
    const { getByTestId } = render(
      <TenantLanding hideAuthIsland org={ORG} config={null} />,
    );
    const root = getByTestId('tenant-landing');
    // The container should consume --brand-secondary as its background.
    expect(root.getAttribute('style') || '').toMatch(/--brand-secondary/);
  });

  it('renders a secondary CTA when configured', () => {
    const { getByText } = render(
      <TenantLanding
        hideAuthIsland
        org={ORG}
        config={{ secondary_cta_text: 'Tour the school' }}
      />,
    );
    expect(getByText('Tour the school')).toBeTruthy();
  });
});
