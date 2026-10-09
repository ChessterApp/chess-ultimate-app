/**
 * `/g/<slug>` — short, shareable master-database game link with OG previews.
 *
 * The slug is the same opaque codec used on /database (see `@/lib/gameSlug`),
 * so the data-source name never appears in the URL. This server component
 * renders Open Graph + Twitter card tags into the HTML response so messenger
 * crawlers (which don't run JS) unfurl a rich preview, then bounces real
 * browsers to `/database?g=<slug>` via a tiny client component — NOT an HTTP
 * redirect, which would serve crawlers a 3xx before the tags.
 */
import type { Metadata } from 'next';
import type { CSSProperties } from 'react';
import { getTranslations } from 'next-intl/server';
import { decodeGameSlug } from '@/lib/gameSlug';
import { fetchGameMeta, buildShareTitle, buildShareDescription } from '@/lib/gameShareMeta';
import GameRedirect from './GameRedirect';

const SITE_URL = 'https://chesster.io';
const OG_IMAGE = '/static/images/chesster-logo-og.png';

interface PageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const t = await getTranslations('debut.shareGame');
  const watchSuffix = t('ogWatchSuffix');

  // Defaults — used when the slug is undecodable or the meta fetch fails.
  let title = t('ogGenericTitle');
  let description = watchSuffix;
  let url = SITE_URL;

  const target = decodeGameSlug(slug);
  if (target) {
    url = `${SITE_URL}/g/${slug}`;
    const meta = await fetchGameMeta(target.source, target.id);
    const builtTitle = buildShareTitle(meta);
    if (builtTitle) title = builtTitle;
    if (meta) description = buildShareDescription(meta, watchSuffix);
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
      images: [OG_IMAGE],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [OG_IMAGE],
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

export default async function GameSharePage({ params }: PageProps) {
  const { slug } = await params;
  const target = decodeGameSlug(slug);
  const t = await getTranslations('debut.shareGame');

  if (!target) {
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
    <GameRedirect
      slug={slug}
      openingLabel={t('opening')}
      manualLabel={t('openManually')}
    />
  );
}
