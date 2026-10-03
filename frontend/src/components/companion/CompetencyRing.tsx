'use client';

import { useLocale, useTranslations } from 'next-intl';

export interface RingCompetency {
  code: string;
  title_en: string;
  title_ru: string;
  title_kk: string;
  progress: number;
  demonstrated: boolean;
}

interface CompetencyRingProps {
  competencies: RingCompetency[];
  /** 0..1 fraction of competencies demonstrated. */
  hatchProgress: number;
  hatchReady: boolean;
}

/** Locale-aware title picker (ru/kk/en), matching the items.ts name pattern. */
function competencyTitle(c: RingCompetency, locale: string): string {
  if (locale === 'ru') return c.title_ru;
  if (locale === 'kz' || locale === 'kk') return c.title_kk;
  return c.title_en;
}

/**
 * The competency ring: an overall hatch-progress dial plus one segment per
 * seeded competency showing mastery progress. Read-only, always free to view —
 * nothing here is coin-gated (R1).
 */
export default function CompetencyRing({
  competencies,
  hatchProgress,
  hatchReady,
}: CompetencyRingProps) {
  const t = useTranslations('companion');
  const locale = useLocale();

  const pct = Math.round(hatchProgress * 100);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * Math.min(1, Math.max(0, hatchProgress));
  const done = competencies.filter((c) => c.demonstrated).length;

  return (
    <section className="mx-auto max-w-lg px-4 py-6">
      <div className="mb-6 flex flex-col items-center">
        <svg width={140} height={140} viewBox="0 0 140 140" role="img" aria-label={t('ring.title')}>
          <circle cx="70" cy="70" r={radius} fill="none" stroke="rgba(148,163,184,0.25)" strokeWidth="12" />
          <circle
            cx="70"
            cy="70"
            r={radius}
            fill="none"
            stroke={hatchReady ? '#22c55e' : '#a855f7'}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference}`}
            transform="rotate(-90 70 70)"
          />
          <text x="70" y="66" textAnchor="middle" className="fill-gray-900 dark:fill-gray-100" fontSize="22" fontWeight="700">
            {pct}%
          </text>
          <text x="70" y="88" textAnchor="middle" className="fill-gray-500 dark:fill-gray-400" fontSize="11">
            {t('ring.count', { done, total: competencies.length })}
          </text>
        </svg>
        <p className="mt-3 text-center text-sm font-medium text-gray-600 dark:text-gray-300">
          {hatchReady ? t('ring.hatchReady') : t('ring.keepGoing')}
        </p>
      </div>

      <ul className="space-y-2">
        {competencies.map((c) => (
          <li
            key={c.code}
            className="flex items-center gap-3 rounded-xl border border-gray-100 bg-white px-3 py-2 dark:border-[#2a2a2a] dark:bg-[#1a1a1a]"
          >
            <span
              aria-hidden="true"
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${
                c.demonstrated
                  ? 'bg-green-500 text-white'
                  : 'bg-gray-200 text-gray-400 dark:bg-[#2a2a2a]'
              }`}
            >
              {c.demonstrated ? '✓' : ''}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-gray-800 dark:text-gray-200">
                {competencyTitle(c, locale)}
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-[#2a2a2a]">
                <div
                  className={`h-full rounded-full ${c.demonstrated ? 'bg-green-500' : 'bg-purple-500'}`}
                  style={{ width: `${Math.round(Math.min(1, Math.max(0, c.progress)) * 100)}%` }}
                />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
