'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { ArrowUp } from 'lucide-react';
import type { BoardAction, CoachMessage, GameResult } from '@/types/coach';
import type { ToolSummary } from '@/lib/coach/tool-summary';
import { engineLineActions, gameToOpen, puzzleAction, resultToGame } from '@/lib/coach/card-actions';
import EngineLineCard from './EngineLineCard';
import GameList from './GameList';
import OpeningCard from './OpeningCard';
import PuzzleCard from './PuzzleCard';

export interface CardHandlers {
  /** The position the study board shows (the engine line is drawn on it). */
  boardFen: string;
  disabled: boolean;
  onBoardActions?: (actions: BoardAction[]) => void;
  /** Bring the board into view (phones: the sheet drops to peek). */
  onShowBoard?: () => void;
  onOpenGame?: (game: GameResult) => void;
  onSend: (prompt: string) => void;
}

/** The latest summary of each kind, in the order the kinds first came. */
function latestByKind(summaries: ToolSummary[] | undefined): ToolSummary[] {
  const byKind = new Map<string, ToolSummary>();
  for (const s of summaries ?? []) byKind.set(s.kind, s);
  return [...byKind.values()];
}

/** «Показано на доске ↑»: this turn changed the board; tap brings it into view. */
export function ShownOnBoardChip({ onShowBoard }: { onShowBoard?: () => void }) {
  const t = useTranslations('coach');
  const content = (
    <>
      {t('shownOnBoard')}
      <ArrowUp size={14} aria-hidden />
    </>
  );
  const base = 'inline-flex items-center gap-1 rounded-full text-xs text-(--coach-muted)';
  if (!onShowBoard) {
    return (
      <span className={`${base} mt-1.5`} data-testid="shown-on-board">
        {content}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onShowBoard}
      data-testid="shown-on-board"
      className={`${base} mt-0.5 -ml-2 min-h-11 px-2 transition-colors hover:text-(--coach-text) active:text-(--coach-accent-text) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)`}
    >
      {content}
    </button>
  );
}

/** The rich cards of one assistant message, under its text. Old messages without data render nothing. */
export default function MessageCards({ message, ...h }: { message: CoachMessage } & CardHandlers) {
  const t = useTranslations('coach');
  const summaries = latestByKind(message.summaries);
  const results = message.gameResults ?? [];
  const listSummary = summaries.find((s) => s.kind === 'game_list');
  // game_results (with PGNs and sources) win over the summary's list: one list per turn.
  const games = results.length ? results.map(resultToGame) : listSummary?.kind === 'game_list' ? listSummary.games : [];
  const showBoardChip = !!message.boardActions?.length;
  if (!summaries.length && !games.length && !showBoardChip) return null;

  const openGame = (game: Parameters<typeof gameToOpen>[0]) => {
    const card = h.onOpenGame ? gameToOpen(game, results) : null;
    return card ? () => h.onOpenGame?.(card) : null;
  };

  return (
    <>
      {showBoardChip && <ShownOnBoardChip onShowBoard={h.onShowBoard} />}
      <div className="mt-3 space-y-2.5 empty:hidden" data-testid="message-cards">
        {summaries.map((s) => {
          switch (s.kind) {
            case 'engine_line': {
              const actions = h.onBoardActions ? engineLineActions(s, h.boardFen) : [];
              return (
                <EngineLineCard
                  key={s.kind}
                  summary={s}
                  disabled={h.disabled}
                  onShow={
                    actions.length
                      ? () => {
                          h.onBoardActions?.(actions);
                          h.onShowBoard?.();
                        }
                      : undefined
                  }
                />
              );
            }
            case 'opening':
              return (
                <OpeningCard
                  key={s.kind}
                  summary={s}
                  disabled={h.disabled}
                  onLearn={() => h.onSend(t('cardOpeningLearnPrompt', { name: s.name }))}
                />
              );
            case 'puzzle': {
              const action = puzzleAction(s, message.boardActions);
              return (
                <PuzzleCard
                  key={s.kind}
                  summary={s}
                  disabled={h.disabled}
                  onSolve={() => {
                    if (action && h.onBoardActions) {
                      h.onBoardActions([action]);
                      h.onShowBoard?.();
                    } else {
                      h.onSend(t('cardPuzzleSolvePrompt', { id: s.puzzle_id }));
                    }
                  }}
                />
              );
            }
            default:
              // game_list renders below; critical_moments gets its card with «Моменты» (P3b).
              return null;
          }
        })}
        {games.length > 0 && <GameList games={games} source={results[0]?.source} onOpen={openGame} />}
      </div>
    </>
  );
}
