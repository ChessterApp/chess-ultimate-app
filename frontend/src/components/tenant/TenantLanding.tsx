'use client';

import { useUser } from '@clerk/nextjs';
import Link from 'next/link';
import type { Organization } from '@/contexts/organization-types';

// PRD §11.2 #1 — Public tenant landing page renderer.
//
// Consumes `organizations.landing_page_config` (JSONB) and the org branding
// fields. Renders a hero + CTA branded with the org's --brand-* CSS vars
// (already injected by <BrandingInjector>). Falls back to a sensible default
// when landing_page_config is null/empty.

export interface LandingPageConfig {
  hero_title?: string;
  hero_subtitle?: string;
  hero_headline?: string; // alias for hero_title
  cta_text?: string;
  cta_href?: string;
  secondary_cta_text?: string;
  secondary_cta_href?: string;
  body_text?: string;
}

export interface TenantLandingProps {
  org: Pick<
    Organization,
    | 'name'
    | 'slug'
    | 'logoUrl'
    | 'logoMarkUrl'
    | 'primaryColor'
    | 'secondaryColor'
    | 'accentColor'
  >;
  config?: LandingPageConfig | null;
  /** Render mode — "page" applies viewport min-height; "preview" caps height for the wizard preview. */
  variant?: 'page' | 'preview';
  /** Skip the signed-in redirect island (used by the preview iframe / SSR snapshot). */
  hideAuthIsland?: boolean;
}

export function resolveLandingPageConfig(
  raw: Record<string, unknown> | null | undefined,
  org: Pick<Organization, 'name'>,
): Required<Pick<LandingPageConfig, 'hero_title' | 'hero_subtitle' | 'cta_text' | 'cta_href'>> &
  LandingPageConfig {
  const cfg = (raw || {}) as LandingPageConfig;
  const title = cfg.hero_title || cfg.hero_headline || `Welcome to ${org.name}`;
  const subtitle =
    cfg.hero_subtitle ||
    `Learn chess with personalized coaching, courses, and puzzles built for our students.`;
  const cta = cfg.cta_text || 'Sign in';
  const ctaHref = cfg.cta_href || '/sign-in';
  return { ...cfg, hero_title: title, hero_subtitle: subtitle, cta_text: cta, cta_href: ctaHref };
}

export function TenantLanding({
  org,
  config,
  variant = 'page',
  hideAuthIsland = false,
}: TenantLandingProps) {
  const resolved = resolveLandingPageConfig(
    (config ?? null) as Record<string, unknown> | null,
    org,
  );
  const heightClass = variant === 'preview' ? 'min-h-[420px]' : 'min-h-screen';

  return (
    <div
      data-testid="tenant-landing"
      className={`${heightClass} flex flex-col`}
      style={
        {
          backgroundColor: 'var(--brand-secondary, #ffffff)',
          color: 'var(--brand-text, #0f172a)',
        } as React.CSSProperties
      }
    >
      {!hideAuthIsland && <TenantSignedInRedirect />}

      <header
        className="px-6 py-4 flex items-center justify-between border-b"
        style={{
          backgroundColor: 'var(--brand-primary)',
          color: 'var(--brand-secondary, #fff)',
          borderColor: 'rgba(255,255,255,0.15)',
        }}
      >
        <div className="flex items-center gap-3">
          {org.logoMarkUrl || org.logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={org.logoMarkUrl || org.logoUrl || ''}
              alt={`${org.name} logo`}
              className="h-9 w-9 rounded-md object-contain bg-white"
            />
          ) : (
            <div className="h-9 w-9 rounded-md bg-white/20 flex items-center justify-center text-sm font-semibold">
              {org.name.slice(0, 1).toUpperCase()}
            </div>
          )}
          <span className="font-semibold text-lg">{org.name}</span>
        </div>
        <Link
          href={resolved.cta_href}
          className="text-sm font-medium px-3 py-1.5 rounded-md hover:bg-white/10"
        >
          {resolved.cta_text}
        </Link>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-16">
        <div className="max-w-2xl text-center">
          <h1
            className="text-3xl md:text-5xl font-bold mb-4 leading-tight"
            style={{ color: 'var(--brand-primary)' }}
          >
            {resolved.hero_title}
          </h1>
          <p className="text-base md:text-lg text-gray-700 mb-8">
            {resolved.hero_subtitle}
          </p>
          {resolved.body_text && (
            <p className="text-sm text-gray-600 mb-8 whitespace-pre-line">
              {resolved.body_text}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link
              href={resolved.cta_href}
              className="inline-block px-5 py-3 rounded-lg font-semibold text-white shadow-sm"
              style={{
                backgroundColor: 'var(--brand-primary)',
              }}
            >
              {resolved.cta_text}
            </Link>
            {resolved.secondary_cta_text && (
              <Link
                href={resolved.secondary_cta_href || '/sign-up'}
                className="inline-block px-5 py-3 rounded-lg font-semibold border"
                style={{
                  borderColor: 'var(--brand-accent)',
                  color: 'var(--brand-accent)',
                }}
              >
                {resolved.secondary_cta_text}
              </Link>
            )}
          </div>
        </div>
      </main>

      <footer className="px-6 py-4 border-t border-gray-200 text-xs text-gray-500 text-center">
        Powered by Chesster
      </footer>
    </div>
  );
}

function TenantSignedInRedirect() {
  // Match the apex landing's behaviour: signed-in users skip the marketing
  // page and land directly on the dashboard.
  const { isSignedIn, isLoaded } = useUser();
  if (isLoaded && isSignedIn && typeof window !== 'undefined') {
    window.location.replace('/dashboard');
  }
  return null;
}
