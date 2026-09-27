'use client';

/**
 * Contextual upsell modal shown when a restricted (frozen/expired) member tries
 * to open a locked feature — from a nav lock (Task 3) or the `?locked=`
 * dashboard redirect (Task 5). The title names the feature; the body and CTA
 * depend on `reason`. Dismissible via the close button, backdrop, or Esc.
 */
import { useEffect } from 'react';
import Link from 'next/link';
import { Lock, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { RestrictionReason } from '@/lib/access-policy';

interface LockedFeatureModalProps {
  /** Feature key (e.g. `play`, `puzzles`) — names the feature in the title. */
  featureKey: string;
  reason: RestrictionReason;
  /** Primary CTA destination (`policy.upgradePath`). */
  upgradePath: string;
  onClose: () => void;
}

export default function LockedFeatureModal({
  featureKey,
  reason,
  upgradePath,
  onClose,
}: LockedFeatureModalProps) {
  const t = useTranslations('access');

  // Dismiss on Esc.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const featureName = t(`feature.${featureKey}`);
  const isExpired = reason === 'expired';
  const bodyKey = isExpired ? 'expiredBody' : 'frozenBody';
  const ctaKey = isExpired ? 'keepGoingCta' : 'continueCta';

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      data-testid="locked-feature-modal"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="locked-feature-title"
        className="relative w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-[#1a1a1a]"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label={t('close')}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-purple-100 text-purple-600 dark:bg-purple-900/40 dark:text-purple-300">
          <Lock className="h-6 w-6" />
        </div>

        <h2
          id="locked-feature-title"
          className="text-xl font-bold text-gray-900 dark:text-gray-100"
        >
          {t('lockedTitle', { feature: featureName })}
        </h2>
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          {t(bodyKey)}
        </p>

        <Link
          href={upgradePath}
          onClick={onClose}
          className="mt-6 inline-flex w-full items-center justify-center rounded-full bg-purple-600 px-6 py-3 text-base font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
        >
          {t(ctaKey)}
        </Link>

        {reason === 'frozen' && (
          <p className="mt-4 text-xs text-gray-400 dark:text-gray-500">
            {t('contactSchool')}
          </p>
        )}
      </div>
    </div>
  );
}
