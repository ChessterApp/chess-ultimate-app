/**
 * `/g/u/<token>` — short, shareable link to a user's OWN saved game.
 *
 * The token is an opaque, revocable share token minted by the game's owner
 * (see backend `/api/games/<id>/share`). This server component renders Open
 * Graph + Twitter tags from the PUBLIC meta endpoint so messenger crawlers
 * unfurl a rich preview, then bounces real browsers to `/database?gu=<token>`
 * via a tiny client component. The game itself stays gated: the recipient must
 * be signed in, and the authed `/api/games/shared/<token>` endpoint enforces it.
 */
import type { Metadata } from 'next';
import type { CSSProperties } from 'react';
import { getTranslations } from 'next-intl/server';
import { fetchSharedGameMeta, buildShareTitle, buildShareDescription, sharedThumbnailUrl } from '@/lib/gameShareMeta';
import TokenRedirect from './TokenRedirect';

const SITE_URL = 'https://chesster.io';
const OG_IMAGE = '/static/images/chesster-logo-og.png';

interface PageProps {
  params: Promise<{ token: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { token } = await params;
  // OG cards are crawled signed-out with no locale cookie, so next-intl would
  // resolve the Russian default. Pin the preview copy to English.
  const t = await getTranslations({ locale: 'en', namespace: 'debut.shareGame' });
  const watchSuffix = t('ogWatchSuffix');

  // Defaults — used when the token is unknown/revoked or the meta fetch fails.
  let title = t('ogGenericTitle');
  let description = watchSuffix;
  const url = `${SITE_URL}/g/u/${token}`;
  // Falls back to the generic logo card until the game resolves.
  let image = OG_IMAGE;

  const meta = await fetchSharedGameMeta(token);
  const builtTitle = buildShareTitle(meta);
  if (builtTitle) title = builtTitle;
  if (meta) {
    description = buildShareDescription(meta, watchSuffix);
    // Only show the board thumbnail once we know the token resolves — the
    // endpoint 404s for unknown/revoked tokens, which would unfurl broken.
    image = sharedThumbnailUrl(token);
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

export default async function SharedGameSharePage({ params }: PageProps) {
  const { token } = await params;
  const t = await getTranslations('debut.shareGame');

  // Unknown/revoked token → the meta endpoint 404s → null. Show the same
  // graceful not-found as the master-game `/g/<slug>` route.
  const meta = await fetchSharedGameMeta(token);
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
