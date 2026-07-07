import type { Metadata } from 'next';
import type { Organization } from '@/contexts/organization-types';

/** Icon shown on the main (non-tenant) Chesster site — served from `public/`. */
export const MAIN_FAVICON = '/favicon.ico';
/** Neutral fallback for a tenant that has neither a favicon nor a logo. */
export const TENANT_DEFAULT_FAVICON = '/static/images/default-favicon.ico';

/**
 * Resolve the effective favicon for a request.
 *
 * Fallback chain for a tenant: `faviconUrl` → `logoUrl` → neutral default.
 * With no org (the main Chesster site) we use the icon bundled in `public/`.
 */
export function effectiveFaviconUrl(org: Organization | null): string {
  if (!org) return MAIN_FAVICON;
  return org.faviconUrl || org.logoUrl || TENANT_DEFAULT_FAVICON;
}

export const CHESSTER_DEFAULT_METADATA: Metadata = {
  metadataBase: new URL('https://chesster.io'),
  title: 'Chesster - AI-Powered Chess Training',
  description:
    'Plug-and-play chess training with your choice of AI provider. Convert OpenAI, Claude, or Gemini model into chess-aware Chessbuddy and get personalized live chat training. Chesster integrates with Stockfish 17.1 engine, chess databases and to better align with position context, making LLMs chess aware.',

  openGraph: {
    title: 'Chesster - AI-Powered Chess Training',
    description:
      'Transform any AI model into your personal chessbuddy. Get live training with OpenAI, Claude, or Gemini integrated with Stockfish 17.1 engine.',
    url: 'https://chesster.io',
    siteName: 'Chesster',
    images: [
      {
        url: '/static/images/chesster-logo-og.png',
        width: 1200,
        height: 1200,
        alt: 'Chesster Logo',
      },
    ],
    locale: 'en_US',
    type: 'website',
  },

  twitter: {
    card: 'summary_large_image',
    title: 'Chesster - AI-Powered Chess Training',
    description:
      'Transform any AI model into your personal chess coach. Get live training with OpenAI, Claude, or Gemini integrated with Stockfish 17.1.',
    images: ['/static/images/chesster-logo-og.png'],
  },

  keywords: [
    'chess training',
    'AI chess coach',
    'OpenAI chess',
    'Claude chess',
    'Gemini chess',
    'Stockfish',
    'chess engine',
    'chess AI',
    'chess tutor',
    'chess learning',
  ],

  icons: {
    icon: MAIN_FAVICON,
  },

  other: {
    'theme-color': '#8209a3ff',
  },
};

/**
 * Build Next.js metadata from an org (white-label tenant) or fall back to the
 * Chesster defaults when `org` is null.
 *
 * Extracted as a pure function so it can be unit-tested without spinning Next.
 */
export function buildMetadata(org: Organization | null): Metadata {
  if (!org) return CHESSTER_DEFAULT_METADATA;

  const title = `${org.name} — Chess Training`;
  const description = `${org.name} — chess training powered by Chesster.`;
  const ogImage = org.logoUrl || '/static/images/default-og.png';

  return {
    metadataBase: new URL('https://chesster.io'),
    title,
    description,
    openGraph: {
      title,
      description,
      siteName: org.name,
      images: [{ url: ogImage, alt: `${org.name} Logo` }],
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [ogImage],
    },
    icons: {
      icon: effectiveFaviconUrl(org),
    },
    keywords: [
      'chess training',
      'AI chess coach',
      'Stockfish',
      'chess engine',
      'chess AI',
      'chess tutor',
      'chess learning',
      org.slug,
    ],
    other: {
      'theme-color': org.primaryColor,
    },
  };
}
