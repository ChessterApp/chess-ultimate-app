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

/** A puzzle: mini-board thumbnail, rating and themes, «Решить». */
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
        {summary.themes && (
          <ul className="mt-1 flex flex-wrap gap-1">
            {summary.themes.slice(0, 3).map((theme) => (
              <li key={theme} className="rounded-md bg-white/5 px-1.5 py-0.5 text-[11.5px] text-(--coach-muted)">
                {theme}
              </li>
            ))}
          </ul>
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
