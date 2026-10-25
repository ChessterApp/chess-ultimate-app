'use client';

import React, { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, Flag, Lightbulb, MessageCircle, Undo2, User } from 'lucide-react';
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
  /** The coach's latest remark for the speech bubble. */
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
  /** Piece animation on the board in ms, the student's setting (26.10); 0 = instant. */
  animationMs?: number;
  onAnimationChange?: (ms: number) => void;
}

/** The animation speeds the setting offers, in ms. */
export const ANIMATION_CHOICES: Array<{ ms: number; key: 'animationOff' | 'animationFast' | 'animationNormal' | 'animationSlow' }> = [
  { ms: 0, key: 'animationOff' }, { ms: 150, key: 'animationFast' }, { ms: 300, key: 'animationNormal' }, { ms: 600, key: 'animationSlow' },
];

/**
 * The game against the coach: coach row with a speech bubble, the board, the
 * student row, and an action bar (or the result card once the game is over).
 * Self-contained — the host only places it. The mobile shell places the parts
 * itself (rows around the board, the action bar in the coach sheet).
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
  animationMs,
  onAnimationChange,
}: PlayStripProps) {
  return (
    <div className="flex flex-col gap-2" style={{ width }} data-testid="play-strip">
      <PlayCoachRow game={game} thinking={thinking} comment={comment} />
      {children}
      <PlayStudentRow game={game} thinking={thinking} />
      <PlayActionBar
        game={game}
        thinking={thinking}
        chatOpen={chatOpen}
        onHint={onHint}
        onTakeback={onTakeback}
        onResign={onResign}
        onToggleChat={onToggleChat}
        onReview={onReview}
        onRematch={onRematch}
        onClose={onClose}
        animationMs={animationMs}
        onAnimationChange={onAnimationChange}
      />
    </div>
  );
}

const coachToMoveOf = (game: GameStateView, thinking: boolean) =>
  game.status !== 'finished' && (thinking || !game.student_to_move);

/**
 * The coach: avatar, strength, a pulse while it moves, and its latest remark
 * as a speech bubble. With `onExpand` (the mobile shell) the row fills its box,
 * the bubble takes what is left and a tap on it opens the whole thread.
 */
export function PlayCoachRow({
  game,
  thinking,
  comment,
  onExpand,
}: Pick<PlayStripProps, 'game' | 'thinking' | 'comment'> & { onExpand?: () => void }) {
  const t = useTranslations('coach');
  const fill = onExpand !== undefined;
  return (
    <div className={`flex items-start gap-2 px-1 ${fill ? 'h-full' : ''}`}>
      <CoachAvatar size={fill ? 32 : 40} />
      <div className={`flex min-w-0 flex-1 flex-col ${fill ? 'min-h-0 self-stretch' : ''}`}>
        <div className="flex items-baseline gap-1.5 text-sm">
          <span className="font-semibold text-(--coach-text)">{t('coachLabel')}</span>
          <span className="text-(--coach-muted)">
            {game.engine_elo} · {t(LEVEL_KEY[eloLevel(game.engine_elo)])}
          </span>
          {coachToMoveOf(game, thinking) && (
            <span className="ml-auto h-2 w-2 shrink-0 animate-pulse rounded-full bg-(--coach-accent)" aria-hidden />
          )}
        </div>
        {comment && <CoachBubble key={comment} comment={comment} fill={fill} onExpand={onExpand} />}
      </div>
    </div>
  );
}

const FADE = 'linear-gradient(to bottom, black calc(100% - 28px), transparent)';

/** Speech bubble with a tail pointing at the avatar; scrolls, fading out (with «more») while text is left below. */
function CoachBubble({ comment, fill, onExpand }: { comment: string; fill: boolean; onExpand?: () => void }) {
  const t = useTranslations('coach');
  const ref = useRef<HTMLParagraphElement>(null);
  const [more, setMore] = useState(false);
  const check = useCallback(() => {
    const el = ref.current;
    if (el) setMore(el.scrollHeight - el.scrollTop - el.clientHeight > 1);
  }, []);
  useLayoutEffect(() => {
    check();
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(check);
    observer.observe(el);
    return () => observer.disconnect();
  }, [check]);

  return (
    <div className="animate-fade-in relative mt-1 flex min-h-0 max-w-full flex-col self-start">
      <p
        ref={ref}
        onScroll={check}
        onClick={onExpand}
        // Desktop: up to ~5 lines; the shell: whatever the row has left.
        className={`min-h-0 overflow-y-auto overscroll-contain rounded-2xl rounded-tl-sm bg-(--coach-text) px-3 py-1.5 text-sm leading-snug text-(--coach-bg) ${
          fill ? 'cursor-pointer' : 'max-h-[6.75rem]'
        }`}
        style={more ? { maskImage: FADE, WebkitMaskImage: FADE } : undefined}
        aria-live="polite"
        data-testid="coach-bubble"
        data-overflow={more || undefined}
      >
        {comment}
      </p>
      {more && onExpand && (
        <button
          type="button"
          onClick={onExpand}
          data-testid="coach-bubble-more"
          className="absolute right-2 bottom-1 flex items-center gap-0.5 rounded-full bg-(--coach-text) px-2 text-xs font-semibold text-(--coach-accent) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
        >
          {t('playCommentMore')}
          <ChevronDown size={12} aria-hidden />
        </button>
      )}
    </div>
  );
}

/** The student: whose move it is, check, and the move number. */
export function PlayStudentRow({ game, thinking }: Pick<PlayStripProps, 'game' | 'thinking'>) {
  const t = useTranslations('coach');
  const finished = game.status === 'finished';
  const coachToMove = coachToMoveOf(game, thinking);

  let status: string;
  if (finished) status = '';
  else if (thinking) status = t('gameCoachThinking');
  else status = game.student_to_move ? t('gameYourMove') : t('playCoachTurn');
  if (!finished && !thinking && game.in_check) status += ` · ${t('gameCheck')}`;

  return (
    <div className="flex items-center gap-2 px-1 text-sm">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-(--coach-surface-2) text-(--coach-muted)">
        <User size={14} aria-hidden />
      </span>
      <span className="font-semibold text-(--coach-text)">{t('youLabel')}</span>
      {status && (
        <span className={coachToMove ? 'text-(--coach-muted)' : 'text-(--coach-success)'} data-testid="play-status">
          · {status}
        </span>
      )}
      <span className="ml-auto shrink-0 text-xs text-(--coach-muted)" data-testid="play-move-number">
        {t('playMoveNumber', { number: Math.floor(game.ply / 2) + 1 })}
      </span>
    </div>
  );
}

/** Hint · takeback · resign (confirmed) · chat — or the result card once the game is over. */
export function PlayActionBar({
  game,
  thinking,
  chatOpen,
  onHint,
  onTakeback,
  onResign,
  onToggleChat,
  onReview,
  onRematch,
  onClose,
  animationMs,
  onAnimationChange,
}: Omit<PlayStripProps, 'comment' | 'width' | 'children'>) {
  const t = useTranslations('coach');
  const [confirmResign, setConfirmResign] = useState(false);
  const chosen = ANIMATION_CHOICES.reduce((best, c) => (Math.abs(c.ms - (animationMs ?? 250)) < Math.abs(best.ms - (animationMs ?? 250)) ? c : best), ANIMATION_CHOICES[0]);
  return (
    <>
      {game.status === 'finished' ? (
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
      {game.status !== 'finished' && onAnimationChange && (
        <label className="mt-1 flex items-center justify-end gap-2 text-xs text-(--coach-muted)">
          <span>{t('animationSpeed')}</span>
          <select
            aria-label={t('animationSpeed')}
            className="rounded border border-(--coach-border) bg-transparent px-1 py-0.5 text-xs text-(--coach-text)"
            value={chosen.ms}
            onChange={(e) => onAnimationChange(Number(e.target.value))}
          >
            {ANIMATION_CHOICES.map((c) => (
              <option key={c.ms} value={c.ms}>{t(c.key)}</option>
            ))}
          </select>
        </label>
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
    </>
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
