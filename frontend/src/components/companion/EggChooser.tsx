'use client';

import { useTranslations } from 'next-intl';
import { EGG_VARIANTS } from '@/lib/companion/state';

interface EggChooserProps {
  onChoose: (species: string) => void;
  /** Variant id currently being persisted (disables the grid). */
  busy?: string | null;
}

/**
 * The kid-facing "choose your egg" onboarding step (Phase 1). A single screen —
 * four coloured eggs; tapping one persists it as the companion species. Mirrors
 * the lightweight step-in-UI approach rather than the 1350-line improver wizard
 * (plan A6). No coins, no gating.
 */
export default function EggChooser({ onChoose, busy }: EggChooserProps) {
  const t = useTranslations('companion');

  return (
    <div className="mx-auto max-w-lg px-4 py-8 text-center">
      <h1 className="mb-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
        {t('chooseEgg.title')}
      </h1>
      <p className="mb-8 text-gray-500 dark:text-gray-400">{t('chooseEgg.subtitle')}</p>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {EGG_VARIANTS.map((v) => (
          <button
            key={v.id}
            type="button"
            disabled={!!busy}
            onClick={() => onChoose(v.id)}
            aria-label={t(`eggs.${v.id}`)}
            className="group flex flex-col items-center gap-3 rounded-2xl border border-gray-200 bg-white p-4 transition-colors hover:border-purple-400 hover:bg-purple-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#2a2a2a] dark:bg-[#1a1a1a] dark:hover:border-purple-500 dark:hover:bg-[#241a33]"
          >
            <svg width={72} height={72} viewBox="0 0 200 200" aria-hidden="true">
              <ellipse cx="100" cy="158" rx="50" ry="10" fill="rgba(0,0,0,0.08)" />
              <path
                d="M100 28c-34 0-56 48-56 86a56 56 0 0 0 112 0c0-38-22-86-56-86z"
                fill={v.color}
              />
              <circle cx="82" cy="104" r="6" fill="rgba(255,255,255,0.5)" />
            </svg>
            <span className="text-sm font-medium text-gray-800 dark:text-gray-200">
              {busy === v.id ? t('chooseEgg.saving') : t(`eggs.${v.id}`)}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
