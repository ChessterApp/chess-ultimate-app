/**
 * `/g/c/<token>` — short, shareable link to a user's OWN My Games COLLECTION.
 *
 * The token is an opaque, revocable share token minted by the collection's
 * owner (see backend `/api/games/collection/share`). This server component
 * renders Open Graph + Twitter tags from the PUBLIC meta endpoint so messenger
 * crawlers unfurl a rich preview, then bounces real browsers to
 * `/database?gc=<token>` via a tiny client component. The collection itself
 * stays gated: the recipient must be signed in, and the authed
 * `/api/games/collection/shared/<token>` endpoint enforces it.
 *
 * Mirrors the per-game `/g/u/<token>` route exactly.
 */
import type { Metadata } from 'next';
import type { CSSProperties } from 'react';
import { createTranslator } from 'next-intl';
import { getTranslations } from 'next-intl/server';
import enMessages from '../../../../../messages/en.json';
import {
  fetchSharedCollectionMeta,
  sharedCollectionThumbnailUrl,
} from '@/lib/collectionShareMeta';
import TokenRedirect from './TokenRedirect';

const SITE_URL = 'https://chesster.io';
const OG_IMAGE = '/static/images/chesster-logo-og.png';

interface PageProps {
  params: Promise<{ token: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { token } = await params;
  // OG cards are crawled signed-out with no locale cookie. The request config
  // resolves locale from the cookie alone, so getTranslations({locale: 'en'})
  // still gets the Russian-default messages — build from en.json directly.
  const t = createTranslator({ locale: 'en', messages: enMessages, namespace: 'debut.shareCollection' });

  // Defaults — used when the token is unknown/revoked or the meta fetch fails.
  let title = t('ogGenericTitle');
  const description = t('ogDescription');
  const url = `${SITE_URL}/g/c/${token}`;
  // Falls back to the generic logo card until the collection resolves.
  let image = OG_IMAGE;

  const meta = await fetchSharedCollectionMeta(token);
  if (meta && meta.owner_name) {
    title = t('ogTitle', { name: meta.owner_name, count: meta.game_count ?? 0 });
    // Only show the board thumbnail once we know the token resolves — the
    // endpoint 404s for unknown/revoked tokens, which would unfurl broken.
    image = sharedCollectionThumbnailUrl(token);
  }

  return {
    metadataBase: new URL(SITE_URL),
    title,
    description,
    openGraph: {
      title,
      description,
      url,
      siteName: 'Chesster',
      type: 'website',
      images: [image],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [image],
    },
  };
}

const PAGE_STYLE: CSSProperties = {
  minHeight: '60vh',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 12,
  fontFamily: 'system-ui, sans-serif',
  textAlign: 'center',
  padding: 24,
};

export default async function SharedCollectionSharePage({ params }: PageProps) {
  const { token } = await params;
  const t = await getTranslations('debut.shareCollection');

  // Unknown/revoked token → the meta endpoint 404s → null. Show the same
  // graceful not-found as the per-game `/g/u/<token>` route.
  const meta = await fetchSharedCollectionMeta(token);
  if (!meta) {
    return (
      <main style={PAGE_STYLE}>
        <h1 style={{ fontSize: 22, margin: 0 }}>{t('notFound')}</h1>
        <p style={{ color: '#666', margin: 0 }}>{t('notFoundBody')}</p>
        <a href="/database" style={{ color: '#8209a3', fontWeight: 600 }}>
          {t('goToDatabase')}
        </a>
      </main>
    );
  }

  return (
    <TokenRedirect
      token={token}
      openingLabel={t('opening')}
      manualLabel={t('openManually')}
    />
  );
}
