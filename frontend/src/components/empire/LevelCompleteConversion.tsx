'use client';

/**
 * Endowed-progress conversion screen. Shown once when a restricted
 * (frozen/expired) member completes the last lesson of their current level —
 * the peak motivation moment (Duolingo pattern: let them finish, convert at the
 * peak). Celebrates the level, teases the locked next level, and routes the
 * primary CTA to the audience-specific upgrade page.
 *
 * Non-restricted members never see this — the lesson page keeps its normal
 * celebration + redirect. The once-per-course guard lives in the caller.
 */
import { useState } from 'react';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import { useTranslations } from 'next-intl';
import type { RestrictionReason } from '@/lib/access-policy';

interface LevelCompleteConversionProps {
  reason: RestrictionReason;
  /** Primary CTA destination (`policy.upgradePath`). */
  upgradePath: string;
  /** 1-based number of the level the member just completed. */
  level: number;
  /** Title of the next (locked) level, if any. */
  nextLevelTitle?: string | null;
  /** Secondary action — return to the Learn path. */
  onBackToLearn: () => void;
}

const CONFETTI_COLORS = ['#8B5CF6', '#22C55E', '#F59E0B', '#EF4444', '#3B82F6', '#EC4899'];

export default function LevelCompleteConversion({
  reason,
  upgradePath,
  level,
  nextLevelTitle,
  onBackToLearn,
}: LevelCompleteConversionProps) {
  const t = useTranslations('access');
  const isExpired = reason === 'expired';
  const ctaKey = isExpired ? 'keepGoingCta' : 'continueCta';

  // Tasteful confetti burst — computed once on mount (this overlay only ever
  // renders client-side, after a lesson completion, so no hydration concern).
  const [confetti] = useState(() =>
    Array.from({ length: 40 }, (_, i) => ({
      id: i,
      x: Math.random() * 100,
      delay: Math.random() * 0.5,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
    })),
  );

  return (
    <div
      data-testid="level-complete-conversion"
      className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden bg-black/50 p-4"
    >
      {/* Confetti */}
      <div className="pointer-events-none absolute inset-0" aria-hidden="true">
        {confetti.map((piece) => (
          <div
            key={piece.id}
            className="absolute top-0 h-2 w-2 animate-confetti rounded-sm"
            style={{
              left: `${piece.x}%`,
              backgroundColor: piece.color,
              animationDelay: `${piece.delay}s`,
            }}
          />
        ))}
      </div>

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="level-complete-title"
        className="relative w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-xl dark:bg-[#1a1a1a]"
      >
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-purple-100 text-3xl dark:bg-purple-900/40">
          🎉
        </div>

        <h2
          id="level-complete-title"
          className="text-2xl font-bold text-gray-900 dark:text-gray-100"
        >
          {t('levelComplete.title', { level })}
        </h2>
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          {t('levelComplete.subtitle')}
        </p>

        {nextLevelTitle && (
          <div className="mt-6 flex items-center gap-3 rounded-2xl border border-dashed border-gray-300 bg-gray-50 p-4 text-left dark:border-gray-700 dark:bg-gray-800/50">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gray-200 text-gray-500 dark:bg-gray-700">
              <Lock className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                {t('levelComplete.nextUp')}
              </p>
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                {t('levelComplete.nextLevel', {
                  level: level + 1,
                  title: nextLevelTitle,
                })}
              </p>
            </div>
          </div>
        )}

        <Link
          href={upgradePath}
          className="mt-6 inline-flex w-full items-center justify-center rounded-full bg-purple-600 px-6 py-3 text-base font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95"
        >
          {t(ctaKey)}
        </Link>

        <button
          type="button"
          onClick={onBackToLearn}
          className="mt-4 text-sm font-medium text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        >
          {t('levelComplete.backToLearn')}
        </button>
      </div>
    </div>
  );
}
