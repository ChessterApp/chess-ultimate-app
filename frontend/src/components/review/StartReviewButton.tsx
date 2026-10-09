'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import type { ReviewSource } from './types';
import { startReview } from './reviewApi';

export interface ReviewGame {
  /** Full PGN of the game (built by the calling surface). */
  pgn: string;
  /** Bot / online games unlock Review only once finished. */
  isFinished?: boolean;
  /** Board orientation to open the review with. */
  orientation?: 'white' | 'black';
}

/**
 * Gating rule, in ONE place: database games are always reviewable; bot/online
 * games unlock only when finished (checkmate/resign/draw/timeout).
 */
export function canReview(game: Pick<ReviewGame, 'isFinished'>, source: ReviewSource): boolean {
  if (source === 'database') return true;
  return !!game.isFinished;
}

export interface StartReviewButtonProps {
  game: ReviewGame;
  source: ReviewSource;
  label?: string;
  disabledTooltip?: string;
  variant?: 'primary' | 'ghost';
  className?: string;
  style?: React.CSSProperties;
  onError?: (message: string) => void;
}

/**
 * Shared entry point across all three surfaces (bot / online / database).
 * Builds nothing itself — the caller passes a ready PGN — then POSTs to
 * /api/review and routes to /review/[id].
 */
export default function StartReviewButton({
  game,
  source,
  label,
  disabledTooltip,
  variant = 'primary',
  className,
  style,
  onError,
}: StartReviewButtonProps) {
  const t = useTranslations('gameReview');
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const allowed = canReview(game, source);
  const resolvedLabel = label ?? t('startButton.label');
  const resolvedTooltip = disabledTooltip ?? t('startButton.disabledTooltip');

  async function handleClick() {
    if (!allowed || loading) return;
    setLoading(true);
    try {
      const { review_id } = await startReview(game.pgn);
      const params = new URLSearchParams({ source });
      if (game.orientation) params.set('orientation', game.orientation);
      router.push(`/review/${review_id}?${params.toString()}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : t('startButton.couldNotStart');
      if (onError) onError(message);
      else console.error(message);
      setLoading(false);
    }
  }

  // Self-contained styling: this button renders in modals / the database viewer,
  // outside the review page's .review-root, so it can't rely on --review-* vars.
  const base: React.CSSProperties = {
    padding: '12px 18px',
    fontSize: 15,
    fontWeight: 800,
    borderRadius: 999,
    cursor: allowed && !loading ? 'pointer' : 'not-allowed',
    userSelect: 'none',
    opacity: allowed ? 1 : 0.5,
    fontFamily: 'inherit',
    transition: 'filter 0.15s ease',
  };
  const skin: React.CSSProperties =
    variant === 'primary'
      ? {
          background: 'linear-gradient(135deg,#14B8A6,#0d9488)',
          color: '#fff',
          border: 'none',
          boxShadow: allowed ? '0 4px 12px rgba(13,148,136,0.35)' : 'none',
        }
      : {
          background: 'transparent',
          color: '#0d9488',
          border: '2px solid #0d9488',
        };

  return (
    <button
      type="button"
      data-testid="start-review-button"
      className={className}
      disabled={!allowed || loading}
      title={!allowed ? resolvedTooltip : undefined}
      aria-disabled={!allowed || loading}
      onClick={handleClick}
      style={{ ...base, ...skin, ...style }}
    >
      {loading ? t('startButton.starting') : `⚡ ${resolvedLabel}`}
    </button>
  );
}
