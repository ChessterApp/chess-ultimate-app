'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Target } from 'lucide-react';
import type { ReviewMomentsSummary } from '@/lib/coach/tool-summary';
import { cardShell } from './card-styles';

interface MomentsCardProps {
  summary: ReviewMomentsSummary;
  /** «Начать»: the review's moments are replayed on the board (MomentsFlow). */
  onStart?: () => void;
  disabled?: boolean;
}

/** A game review as «Моменты»: how many, whose game, and «Начать». */
export default function MomentsCard({ summary, onStart, disabled }: MomentsCardProps) {
  const t = useTranslations('coach');
  const { game, moments } = summary;
  const players = `${game.white === '?' ? t('momentsWhite') : game.white} – ${game.black === '?' ? t('momentsBlack') : game.black}`;
  return (
    <section className={`${cardShell} flex items-center gap-3`} data-testid="card-moments" aria-label={t('momentsTitle')}>
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-(--coach-accent-soft) text-(--coach-accent-text)">
        <Target size={20} aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="text-[15px] font-semibold leading-snug text-(--coach-text)">
          {t('momentsCardTitle', { count: moments.length })}
        </h3>
        <p className="truncate text-[13px] text-(--coach-muted)">
          {players}
          {game.result ? ` · ${game.result}` : ''}
        </p>
      </div>
      {onStart && (
        <button
          type="button"
          onClick={onStart}
          disabled={disabled}
          data-testid="card-moments-start"
          className="min-h-11 shrink-0 rounded-full bg-(--coach-accent) px-5 text-sm font-semibold text-white transition hover:brightness-110 active:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent) disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:brightness-100"
        >
          {t('momentsStart')}
        </button>
      )}
    </section>
  );
}
