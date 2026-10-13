'use client';

import React, { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Flag, Lightbulb, MessageCircle, Undo2, User } from 'lucide-react';
import type { GameStateView } from '@/lib/coach/boards-api';
import { eloLevel } from '@/lib/coach/play';
import CoachAvatar from './CoachAvatar';
import CoachDialog from './CoachDialog';
import ResultCard from './ResultCard';

const LEVEL_KEY = {
  novice: 'levelNovice',
  amateur: 'levelAmateur',
  club: 'levelClub',
  expert: 'levelExpert',
  master: 'levelMaster',
} as const;

interface PlayStripProps {
  game: GameStateView;
  thinking: boolean;
  /** The coach's latest remark, one line, for the speech bubble. */
  comment: string | null;
  /** Whether the chat composer is shown (the Chat button toggles it). */
  chatOpen: boolean;
  /** Board width in px: the rows line up with the board. */
  width: number;
  /** The board itself, rendered between the coach row and the student row. */
  children: React.ReactNode;
  onHint: () => void;
  onTakeback: () => void;
  onResign: () => void;
  onToggleChat: () => void;
  onReview: () => void;
  onRematch: () => void;
  onClose: () => void;
}

/**
 * The game against the coach: coach row with a speech bubble, the board, the
 * student row, and an action bar (or the result card once the game is over).
 * Self-contained — the host only places it.
 */
export default function PlayStrip({
  game,
  thinking,
  comment,
  chatOpen,
  width,
  children,
  onHint,
  onTakeback,
  onResign,
  onToggleChat,
  onReview,
  onRematch,
  onClose,
}: PlayStripProps) {
  const t = useTranslations('coach');
  const [confirmResign, setConfirmResign] = useState(false);
  const finished = game.status === 'finished';
  const coachToMove = !finished && (thinking || !game.student_to_move);

  let status: string;
  if (finished) status = '';
  else if (thinking) status = t('gameCoachThinking');
  else status = game.student_to_move ? t('gameYourMove') : t('playCoachTurn');
  if (!finished && !thinking && game.in_check) status += ` · ${t('gameCheck')}`;

  return (
    <div className="flex flex-col gap-2" style={{ width }} data-testid="play-strip">
      {/* Coach row */}
      <div className="flex items-start gap-2 px-1">
        <CoachAvatar size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5 text-sm">
            <span className="font-semibold text-(--coach-text)">{t('coachLabel')}</span>
            <span className="text-(--coach-muted)">
              {game.engine_elo} · {t(LEVEL_KEY[eloLevel(game.engine_elo)])}
            </span>
            {coachToMove && (
              <span className="ml-auto h-2 w-2 shrink-0 animate-pulse rounded-full bg-(--coach-accent)" aria-hidden />
            )}
          </div>
          {comment && (
            <p
              // Speech bubble with a tail pointing at the avatar.
              className="animate-fade-in relative mt-1 w-fit max-w-full rounded-2xl rounded-tl-sm bg-(--coach-text) px-3 py-1.5 text-sm leading-snug text-(--coach-bg) line-clamp-2"
              aria-live="polite"
              data-testid="coach-bubble"
              key={comment}
            >
              {comment}
            </p>
          )}
        </div>
      </div>

      {children}

      {/* Student row */}
      <div className="flex items-center gap-2 px-1 text-sm">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-(--coach-surface-2) text-(--coach-muted)">
          <User size={16} aria-hidden />
        </span>
        <span className="font-semibold text-(--coach-text)">{t('youLabel')}</span>
        {status && (
          <span className={coachToMove ? 'text-(--coach-muted)' : 'text-(--coach-success)'} data-testid="play-status">
            · {status}
          </span>
        )}
      </div>

      {finished ? (
        <ResultCard game={game} onReview={onReview} onRematch={onRematch} onClose={onClose} />
      ) : (
        <div role="toolbar" aria-label={t('playActions')} className="grid grid-cols-4 gap-2">
          <ActionButton icon={Lightbulb} label={t('gameHint')} onClick={onHint} disabled={thinking} />
          <ActionButton
            icon={Undo2}
            label={t('playTakebackShort')}
            onClick={onTakeback}
            disabled={thinking || game.ply === 0}
          />
          <ActionButton icon={Flag} label={t('gameResign')} onClick={() => setConfirmResign(true)} disabled={thinking} />
          <ActionButton icon={MessageCircle} label={t('playChat')} onClick={onToggleChat} pressed={chatOpen} />
        </div>
      )}

      <CoachDialog
        open={confirmResign}
        title={t('gameResignConfirm')}
        confirmLabel={t('gameResign')}
        danger
        onCancel={() => setConfirmResign(false)}
        onConfirm={() => {
          setConfirmResign(false);
          onResign();
        }}
      />
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  onClick,
  disabled,
  pressed,
}: {
  icon: React.ComponentType<{ size?: number; 'aria-hidden'?: boolean }>;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      className={`flex min-h-14 min-w-0 flex-col items-center justify-center gap-1 rounded-xl border px-1 text-xs transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) disabled:cursor-not-allowed disabled:opacity-40 ${
        pressed
          ? 'border-(--coach-accent) bg-(--coach-accent-soft) text-(--coach-text)'
          : 'border-(--coach-border) bg-(--coach-surface) text-(--coach-muted) hover:bg-(--coach-surface-2) hover:text-(--coach-text) active:bg-(--coach-surface)'
      }`}
    >
      <Icon size={20} aria-hidden />
      <span className="max-w-full truncate">{label}</span>
    </button>
  );
}
