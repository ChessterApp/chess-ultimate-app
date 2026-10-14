'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Puzzle } from 'lucide-react';
import type { PuzzleSummary } from '@/lib/coach/tool-summary';
import MiniBoard from './MiniBoard';
import { cardAction, cardShell, cardTitle } from './card-styles';

interface PuzzleCardProps {
  summary: PuzzleSummary;
  /** «Решить»: starts the puzzle's step flow on the board. */
  onSolve?: () => void;
  disabled?: boolean;
}

/**
 * A puzzle: mini-board thumbnail, rating, «Решить». The summary's themes are
 * Lichess keys with no translation in the app yet, so they are not shown.
 */
export default function PuzzleCard({ summary, onSolve, disabled }: PuzzleCardProps) {
  const t = useTranslations('coach');
  return (
    <section className={`${cardShell} flex gap-3`} data-testid="card-puzzle" aria-label={t('cardPuzzleTitle')}>
      <MiniBoard fen={summary.fen} size={96} label={t('cardPuzzleBoardLabel')} />
      <div className="flex min-w-0 flex-1 flex-col">
        <h3 className={cardTitle}>{t('cardPuzzleTitle')}</h3>
        {summary.rating && (
          <p className="mt-0.5 text-[14px] tabular-nums text-(--coach-text)">{t('cardPuzzleRating', { rating: summary.rating })}</p>
        )}
        {onSolve && (
          <div className="mt-auto pt-2">
            <button type="button" onClick={onSolve} disabled={disabled} className={cardAction} data-testid="card-puzzle-solve">
              <Puzzle size={15} aria-hidden />
              {t('cardPuzzleSolve')}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
