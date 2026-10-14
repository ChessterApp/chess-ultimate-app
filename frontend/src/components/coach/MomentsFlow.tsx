'use client';

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { RotateCcw } from 'lucide-react';
import type { Key } from 'chessground/types';
import type { ReviewMomentsSummary } from '@/lib/coach/tool-summary';
import {
  currentMoment,
  initialMomentsFlow,
  momentsBoard,
  momentsFlow,
  numberedMove,
  type MomentsBoard,
  type MomentsFlowEvent,
  type MomentsFlowState,
} from '@/lib/coach/moments-flow';
import { stepXp } from '@/lib/coach/step-flow';
import { creditStepXp } from '@/hooks/useStepFlow';
import { useHaptic } from '@/hooks/useHaptic';
import CoachAvatar from './CoachAvatar';
import StepFlow, { type StepFeedback } from './StepFlow';

export interface MomentsControls {
  state: MomentsFlowState;
  /** What the board shows; null once the review is over. */
  board: MomentsBoard | null;
  flash: { result: 'correct' | 'wrong'; key: number } | null;
  /** XP really credited for the last checked moment (0: nothing shown). */
  xp: number;
  move: (from: Key, to: Key, promotion?: 'q' | 'r' | 'b' | 'n') => void;
  check: () => void;
  send: (event: Exclude<MomentsFlowEvent, { type: 'move' } | { type: 'check' }>) => void;
}

/** The «Моменты» state machine (lib/coach/moments-flow.ts) for one review, with XP and haptics on a check. */
export function useMomentsFlow(review: ReviewMomentsSummary | null): MomentsControls {
  const haptic = useHaptic();
  const [state, setState] = useState(() => initialMomentsFlow(review?.moments ?? []));
  const [flash, setFlash] = useState<MomentsControls['flash']>(null);
  const [xp, setXp] = useState(0);

  // A new review starts over (state reset while rendering, not in an effect).
  const [forReview, setForReview] = useState(review);
  if (forReview !== review) {
    setForReview(review);
    setState(initialMomentsFlow(review?.moments ?? []));
    setFlash(null);
    setXp(0);
  }

  const send = useCallback((event: MomentsFlowEvent) => setState((s) => momentsFlow(s, event)), []);

  const check = useCallback(() => {
    const next = momentsFlow(state, { type: 'check' });
    if (next === state || !next.checked) return;
    const { correct } = next.checked;
    const attempts = next.step.attempts;
    // The one XP path (as PuzzleFlow): only what is really credited is shown.
    setXp(creditStepXp({ correct, attempts, xp: correct ? stepXp(attempts) : 0 }));
    setState(next);
    setFlash({ result: correct ? 'correct' : 'wrong', key: Date.now() });
    if (correct) haptic.onPuzzleCorrect();
    else haptic.onPuzzleWrong();
  }, [state, haptic]);

  return {
    state,
    board: momentsBoard(state),
    flash,
    xp,
    move: useCallback((from, to, promotion) => send({ type: 'move', from, to, promotion }), [send]),
    check,
    send,
  };
}

const MOTIF_KEYS: Record<string, string> = {
  mate: 'motifMate',
  fork: 'motifFork',
  discovered_attack: 'motifDiscoveredAttack',
  pin: 'motifPin',
  skewer: 'motifSkewer',
  hanging_piece: 'motifHangingPiece',
};

interface MomentsFlowProps {
  controls: MomentsControls;
  /** A question about the moment goes to the chat («Спросить», «Почему не …?»). */
  onAsk: (message: string) => void;
  /** Back to the chat; the board shows the study position again. */
  onExit: () => void;
}

/** The game review's guided steps: StepFlow per moment, then the summary. */
export default function MomentsFlow({ controls, onAsk, onExit }: MomentsFlowProps) {
  const t = useTranslations('coach');
  const { state, send } = controls;
  const moment = currentMoment(state);
  const total = state.moments.length;

  if (state.step.phase === 'done' || !moment) {
    return <MomentsDone found={state.firstTry} total={total} onAgain={() => send({ type: 'restart', moments: state.moments })} onExit={onExit} />;
  }

  const n = state.step.index + 1;
  const checked = state.checked;
  let feedback: StepFeedback | null = null;
  if (checked) {
    // Correct: the better move, and why not the game's. Wrong: the student's move, and why not it.
    const whyNot = checked.correct ? moment.played : checked.move.san;
    feedback = {
      san: numberedMove(moment, checked.correct ? moment.best : checked.move.san),
      explanation: moment.explanation,
      motif: moment.motif && MOTIF_KEYS[moment.motif] ? t(MOTIF_KEYS[moment.motif]) : undefined,
      xp: checked.correct ? controls.xp : 0,
      followUp: {
        label: t('momentsWhyNotChip', { move: numberedMove(moment, whyNot) }),
        message: t('momentsWhyNotMessage', {
          n,
          move: numberedMove(moment, whyNot),
          best: numberedMove(moment, moment.best),
        }),
      },
    };
  }

  return (
    <StepFlow
      title={t('momentsTitle')}
      stepLabel={t('momentsStepOf', { n, total })}
      state={state.step}
      prompt={moment.question}
      feedback={feedback}
      onHint={() => send({ type: 'hint' })}
      onAsk={() => onAsk(t('momentsAskMessage', { n, move: numberedMove(moment, moment.played) }))}
      onUndo={() => send({ type: 'undo' })}
      onCheck={controls.check}
      onRetry={() => send({ type: 'retry' })}
      onNext={() => send({ type: 'next' })}
      onFollowUp={onAsk}
      onClose={onExit}
      closeLabel={t('momentsExit')}
    />
  );
}

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent)';

function MomentsDone({ found, total, onAgain, onExit }: { found: number; total: number; onAgain: () => void; onExit: () => void }) {
  const t = useTranslations('coach');
  return (
    <section
      className="animate-fade-in w-full rounded-xl border border-(--coach-border) bg-(--coach-surface) p-3"
      data-testid="moments-done"
      aria-labelledby="moments-done-title"
    >
      <div className="flex items-center gap-3">
        <CoachAvatar size={40} />
        <div className="min-w-0">
          <h2 id="moments-done-title" className="text-base font-semibold text-(--coach-text)">
            {t('momentsDoneTitle')}
          </h2>
          <p className="text-sm text-(--coach-muted)" data-testid="moments-done-score">
            {t('momentsDoneScore', { found, total })}
          </p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onAgain}
          aria-label={t('momentsDoneAgain')}
          title={t('momentsDoneAgain')}
          className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-(--coach-border) text-(--coach-muted) transition-colors hover:bg-white/5 hover:text-(--coach-text) active:bg-white/10 ${focusRing}`}
        >
          <RotateCcw size={18} aria-hidden />
        </button>
        <button
          type="button"
          autoFocus
          onClick={onExit}
          className={`min-h-12 flex-1 truncate rounded-xl bg-(--coach-accent) px-4 text-base font-semibold text-white transition hover:brightness-110 active:brightness-95 ${focusRing}`}
        >
          {t('momentsDoneBack')}
        </button>
      </div>
    </section>
  );
}
