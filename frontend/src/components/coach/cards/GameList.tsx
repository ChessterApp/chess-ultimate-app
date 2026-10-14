'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { ChevronRight } from 'lucide-react';
import type { SummaryGame } from '@/lib/coach/tool-summary';

const SOURCE_KEY = { user: 'sourceUser', lichess: 'sourceLichess', chesscom: 'sourceChesscom' } as const;

interface GameListProps {
  games: SummaryGame[];
  /** Where own / imported games come from (master games say nothing). */
  source?: string;
  /** Tap → open the game in a board tab; absent for a game that cannot be opened. */
  onOpen: (game: SummaryGame) => ((() => void) | null);
}

function resultClass(result: string) {
  if (result === '1-0') return 'text-(--coach-success)';
  if (result === '0-1') return 'text-(--coach-danger)';
  return 'text-(--coach-muted)';
}

function Player({ name, elo }: { name: string; elo?: number }) {
  return (
    <span className="flex min-w-0 items-baseline gap-1.5">
      <span className="truncate text-[14px] text-(--coach-text)">{name}</span>
      {elo && <span className="shrink-0 text-[12px] tabular-nums text-(--coach-muted)">{elo}</span>}
    </span>
  );
}

/** Game cards in one list: players, result, ECO and year; tap opens the game in a board tab. */
export default function GameList({ games, source, onOpen }: GameListProps) {
  const t = useTranslations('coach');
  const sourceKey = source && source in SOURCE_KEY ? SOURCE_KEY[source as keyof typeof SOURCE_KEY] : null;
  return (
    <section className="animate-fade-in overflow-hidden rounded-xl border border-(--coach-border) bg-(--coach-surface-2)" data-testid="card-game-list">
      {sourceKey && (
        <div className="border-b border-(--coach-border) px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-(--coach-muted)">
          {t(sourceKey)}
        </div>
      )}
      <ul className="divide-y divide-(--coach-border)">
        {games.map((game, i) => {
          const open = onOpen(game);
          const meta = [game.eco, game.year].filter(Boolean).join(' · ');
          const body = (
            <>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <Player name={game.white} elo={game.white_elo} />
                <Player name={game.black} elo={game.black_elo} />
              </span>
              <span className="flex shrink-0 flex-col items-end gap-0.5">
                <span className={`text-[14px] font-semibold tabular-nums ${resultClass(game.result)}`}>{game.result}</span>
                {meta && <span className="text-[12px] tabular-nums text-(--coach-muted)">{meta}</span>}
              </span>
            </>
          );
          return (
            <li key={`${game.id ?? 'g'}-${i}`}>
              {open ? (
                <button
                  type="button"
                  onClick={open}
                  aria-label={t('cardOpenGame', { white: game.white, black: game.black })}
                  className="flex min-h-14 w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-white/5 active:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--coach-accent)"
                  data-testid="card-game"
                >
                  {body}
                  <ChevronRight size={16} aria-hidden className="shrink-0 text-(--coach-muted)" />
                </button>
              ) : (
                <div className="flex min-h-14 items-center gap-3 px-3 py-2" data-testid="card-game">
                  {body}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
