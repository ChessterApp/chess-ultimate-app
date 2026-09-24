'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import type { GameCommentMode, GameStateView } from '@/lib/coach/boards-api';

/** Opponent strengths offered in the start dialog (Stockfish Elo). */
export const GAME_STRENGTHS = [600, 800, 1000, 1200, 1500, 1800, 2000, 2200, 2500];

export interface GameStartOptions {
  color: 'white' | 'black' | 'random';
  elo: number;
  comment_mode: GameCommentMode;
}

interface GameStartDialogProps {
  defaultElo?: number;
  onStart: (options: GameStartOptions) => void;
  onCancel: () => void;
  busy?: boolean;
}

/** "Play the coach": colour, strength and how talkative the coach should be. */
export function GameStartDialog({ defaultElo = 1200, onStart, onCancel, busy }: GameStartDialogProps) {
  const t = useTranslations('coach');
  const [color, setColor] = useState<GameStartOptions['color']>('white');
  const [elo, setElo] = useState<number>(
    GAME_STRENGTHS.reduce((best, s) => (Math.abs(s - defaultElo) < Math.abs(best - defaultElo) ? s : best), GAME_STRENGTHS[0]),
  );
  const [commentMode, setCommentMode] = useState<GameCommentMode>('mistakes');

  return (
    <div role="dialog" aria-label={t('gameDialogTitle')} className="absolute inset-0 z-20 flex items-center justify-center bg-black/60">
      <div className="w-[320px] rounded-xl border border-white/10 bg-[#1b1b24] p-4 shadow-xl space-y-3">
        <h2 className="text-white font-semibold">{t('gameDialogTitle')}</h2>

        <label className="block text-xs text-gray-400">
          {t('gameColor')}
          <div className="mt-1 flex gap-1">
            {(['white', 'black', 'random'] as const).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setColor(c)}
                className={`flex-1 rounded px-2 py-1 text-sm ${color === c ? 'bg-white/20 text-white' : 'bg-white/5 text-gray-300 hover:bg-white/10'}`}
              >
                {c === 'white' ? t('colorWhite') : c === 'black' ? t('colorBlack') : t('colorRandom')}
              </button>
            ))}
          </div>
        </label>

        <label className="block text-xs text-gray-400">
          {t('gameStrength')}
          <select
            value={elo}
            onChange={(e) => setElo(Number(e.target.value))}
            className="mt-1 w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-sm text-gray-100"
            data-testid="game-elo"
          >
            {GAME_STRENGTHS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-xs text-gray-400">
          {t('gameComments')}
          <select
            value={commentMode}
            onChange={(e) => setCommentMode(e.target.value as GameCommentMode)}
            className="mt-1 w-full rounded bg-white/5 border border-white/10 px-2 py-1 text-sm text-gray-100"
            data-testid="game-comments"
          >
            <option value="quiet">{t('commentsQuiet')}</option>
            <option value="mistakes">{t('commentsMistakes')}</option>
            <option value="every">{t('commentsEvery')}</option>
          </select>
        </label>

        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded px-3 py-2 text-sm text-gray-300 bg-white/5 hover:bg-white/10"
          >
            {t('cancel')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onStart({ color, elo, comment_mode: commentMode })}
            className="flex-1 rounded px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-500 disabled:opacity-50"
          >
            {t('startGame')}
          </button>
        </div>
      </div>
    </div>
  );
}

interface GamePanelProps {
  game: GameStateView;
  thinking: boolean;
  onHint: () => void;
  onTakeback: () => void;
  onResign: () => void;
  onReview: () => void;
  onNewGame: () => void;
  onClose: () => void;
}

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

/** Status line and controls of the live game under the board. */
export default function GamePanel({ game, thinking, onHint, onTakeback, onResign, onReview, onNewGame, onClose }: GamePanelProps) {
  const t = useTranslations('coach');
  const finished = game.status === 'finished';
  const verdict = game.student?.verdict;
  const showVerdict = verdict && verdict !== 'ok';

  let outcome: string | null = null;
  if (finished) {
    const head = game.winner === 'student' ? t('gameWon') : game.winner === 'engine' ? t('gameLost') : t('gameDraw');
    const term = game.termination ? t(TERMINATION_KEY[game.termination] ?? 'termDraw') : '';
    outcome = term ? `${head} — ${term} (${game.result})` : `${head} (${game.result})`;
  }

  return (
    <div className="w-full mt-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm" data-testid="game-panel">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-gray-300">
        <span>
          {t('gameYouPlay', {
            color: game.student_color === 'white' ? t('colorWhite').toLowerCase() : t('colorBlack').toLowerCase(),
            elo: game.engine_elo,
          })}
        </span>
        {!finished && (
          <span className={thinking ? 'text-yellow-300 animate-pulse' : 'text-green-300'}>
            {thinking ? t('gameCoachThinking') : game.student_to_move ? t('gameYourMove') : t('gameCoachThinking')}
            {!thinking && game.in_check ? ` · ${t('gameCheck')}` : ''}
          </span>
        )}
        {outcome && <span className="text-white font-medium">{outcome}</span>}
      </div>
      {showVerdict && game.student && (
        <div className="mt-1 text-xs text-orange-300" data-testid="game-verdict">
          {game.student.san}: {t(verdict === 'blunder' ? 'verdictBlunder' : verdict === 'mistake' ? 'verdictMistake' : 'verdictInaccuracy')}
          {game.student.best ? `, ${t('gameBetterWas', { move: game.student.best })}` : ''}
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {!finished ? (
          <>
            <button type="button" onClick={onHint} disabled={thinking} className="rounded px-2 py-1 text-xs bg-white/10 hover:bg-white/20 text-gray-100 disabled:opacity-40">
              {t('gameHint')}
            </button>
            <button type="button" onClick={onTakeback} disabled={thinking || game.ply === 0} className="rounded px-2 py-1 text-xs bg-white/10 hover:bg-white/20 text-gray-100 disabled:opacity-40">
              {t('gameTakeback')}
            </button>
            <button
              type="button"
              onClick={() => {
                if (window.confirm(t('gameResignConfirm'))) onResign();
              }}
              disabled={thinking}
              className="rounded px-2 py-1 text-xs bg-red-500/20 hover:bg-red-500/30 text-red-300 disabled:opacity-40"
            >
              {t('gameResign')}
            </button>
          </>
        ) : (
          <>
            <button type="button" onClick={onReview} className="rounded px-2 py-1 text-xs bg-blue-600/40 hover:bg-blue-600/60 text-white">
              {t('gameReview')}
            </button>
            <button type="button" onClick={onNewGame} className="rounded px-2 py-1 text-xs bg-white/10 hover:bg-white/20 text-gray-100">
              {t('gameNew')}
            </button>
            <button type="button" onClick={onClose} className="rounded px-2 py-1 text-xs bg-white/5 hover:bg-white/10 text-gray-400">
              {t('gameClose')}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
