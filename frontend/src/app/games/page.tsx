'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

interface GameCard {
  href: string;
  poster: string;
  titleKey: 'wheel' | 'tugOfWar';
  gradient: string;
}

const games: GameCard[] = [
  {
    href: '/games/wheel',
    poster: '/games/wheel-poster.webp',
    titleKey: 'wheel',
    gradient: 'from-purple-950/95 via-purple-900/60',
  },
  {
    href: '/games/tug-of-war',
    poster: '/games/tug-of-war-poster.webp',
    titleKey: 'tugOfWar',
    gradient: 'from-orange-950/95 via-orange-900/60',
  },
];

export default function GamesPage() {
  const t = useTranslations('gamesHub');

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white">{t('title')}</h1>
        <p className="mt-1 text-gray-500 dark:text-gray-400">{t('subtitle')}</p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {games.map((game) => (
          <Link
            key={game.href}
            href={game.href}
            aria-label={t(`${game.titleKey}.title`)}
            className="group relative block aspect-[3/4] overflow-hidden rounded-2xl shadow-md border-2 border-purple-200 dark:border-purple-900/50 transition-all duration-200 hover:shadow-xl hover:-translate-y-1 hover:border-purple-400 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-purple-500/60"
          >
            <Image
              src={game.poster}
              alt=""
              fill
              sizes="(max-width: 640px) 100vw, 50vw"
              className="object-cover transition-transform duration-300 group-hover:scale-105"
              priority
            />
            <div className={`absolute inset-x-0 bottom-0 bg-gradient-to-t ${game.gradient} to-transparent pt-24 pb-5 px-5`}>
              <h2 className="text-2xl font-bold text-white drop-shadow">{t(`${game.titleKey}.title`)}</h2>
              <p className="mt-1 text-sm text-white/85 line-clamp-2">{t(`${game.titleKey}.description`)}</p>
              <span className="mt-3 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-white/95 text-gray-900 text-sm font-semibold transition-colors group-hover:bg-white">
                {t('play')}
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
