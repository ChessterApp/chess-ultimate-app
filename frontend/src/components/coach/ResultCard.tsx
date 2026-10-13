'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Flag, Handshake, Trophy } from 'lucide-react';
import type { GameStateView } from '@/lib/coach/boards-api';

const TERMINATION_KEY: Record<string, string> = {
  checkmate: 'termCheckmate',
  stalemate: 'termStalemate',
  resign: 'termResign',
  repetition: 'termRepetition',
  insufficient: 'termInsufficient',
  fifty_moves: 'termFiftyMoves',
  move_limit: 'termMoveLimit',
  draw: 'termDraw',
};

interface ResultCardProps {
  game: GameStateView;
  onReview: () => void;
  onRematch: () => void;
  onClose: () => void;
}

/** Game over: result and reason, then review / rematch / close. */
export default function ResultCard({ game, onReview, onRematch, onClose }: ResultCardProps) {
  const t = useTranslations('coach');
  const head = game.winner === 'student' ? t('gameWon') : game.winner === 'engine' ? t('gameLost') : t('gameDraw');
  const reason = game.termination ? t(TERMINATION_KEY[game.termination] ?? 'termDraw') : null;
  const Icon = game.winner === 'student' ? Trophy : game.winner === 'engine' ? Flag : Handshake;
  const tone =
    game.winner === 'student'
      ? 'text-(--coach-success) bg-(--coach-success-soft)'
      : game.winner === 'engine'
        ? 'text-(--coach-danger) bg-(--coach-danger-soft)'
        : 'text-(--coach-muted) bg-white/5';

  return (
    <section
      className="animate-fade-in w-full rounded-xl border border-(--coach-border) bg-(--coach-surface) p-3"
      data-testid="result-card"
      aria-labelledby="coach-result-title"
    >
      <div className="flex items-center gap-3">
        <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${tone}`}>
          <Icon size={22} aria-hidden />
        </span>
        <div className="min-w-0">
          <h2 id="coach-result-title" className="text-base font-semibold text-(--coach-text)">
            {head}
          </h2>
          <p className="text-sm text-(--coach-muted)">
            {reason ? `${reason} · ${game.result ?? ''}` : game.result}
          </p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <button
          type="button"
          onClick={onReview}
          className="min-h-11 truncate rounded-lg bg-(--coach-accent) px-2 text-sm font-medium text-white transition-colors hover:brightness-110 active:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent)"
        >
          {t('resultReview')}
        </button>
        <button
          type="button"
          onClick={onRematch}
          className="min-h-11 truncate rounded-lg bg-white/10 px-2 text-sm text-(--coach-text) transition-colors hover:bg-white/15 active:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
        >
          {t('resultRematch')}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="min-h-11 truncate rounded-lg px-2 text-sm text-(--coach-muted) transition-colors hover:bg-white/5 hover:text-(--coach-text) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
        >
          {t('gameClose')}
        </button>
      </div>
    </section>
  );
}
