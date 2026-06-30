import type { Metadata } from 'next';
import type { Organization } from '@/contexts/organization-types';

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
    'chessempire',
  ],

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
    other: {
      'theme-color': org.primaryColor,
    },
  };
}
