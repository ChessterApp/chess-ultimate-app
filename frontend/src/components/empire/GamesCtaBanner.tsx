'use client';

/**
 * Full-width "Games" CTA banner for the Empire student home page — a
 * purple/indigo sibling of {@link ./TournamentCtaBanner} that sits directly
 * below it.
 *
 * The entire card is a single `next/link` to `/games`, so the whole banner is
 * clickable; the "Play" pill on the right is purely visual. The same pure-CSS
 * diagonal shimmer (see `.tournament-cta-shimmer` in globals.css) sweeps across
 * it and is disabled under `prefers-reduced-motion`.
 */
import Link from 'next/link';
import { useTranslations } from 'next-intl';

export default function GamesCtaBanner({ className = '' }: { className?: string }) {
  const t = useTranslations('empire');

  return (
    <Link
      href="/games"
      data-testid="empire-games-cta"
      className={`relative overflow-hidden block rounded-2xl shadow-sm bg-gradient-to-r from-indigo-600 to-purple-500 text-white transition hover:shadow-md ${className}`}
    >
      {/* Diagonal shimmer sweep — decorative, never intercepts the click. */}
      <span
        aria-hidden="true"
        className="tournament-cta-shimmer pointer-events-none absolute inset-y-0 -left-1/3 w-1/3 -skew-x-12 bg-gradient-to-r from-transparent via-white/40 to-transparent"
      />
      <div className="relative p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center gap-4">
        <div
          className="w-12 h-12 rounded-xl grid place-items-center bg-white/25 shrink-0"
          aria-hidden="true"
        >
          <svg
            width={26}
            height={26}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="6" y1="12" x2="10" y2="12" />
            <line x1="8" y1="10" x2="8" y2="14" />
            <line x1="15" y1="13" x2="15.01" y2="13" />
            <line x1="18" y1="11" x2="18.01" y2="11" />
            <rect width="20" height="12" x="2" y="6" rx="2" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-lg font-bold tracking-tight leading-tight">
            {t('gamesCtaTitle')}
          </div>
          <div className="mt-0.5 text-sm font-medium text-white/90">
            {t('gamesCtaSubtitle')}
          </div>
        </div>
        <span
          data-testid="empire-games-cta-button"
          className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-semibold shrink-0"
        >
          {t('gamesCtaButton')}
          <svg
            width={14}
            height={14}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            aria-hidden="true"
          >
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </Link>
  );
}
