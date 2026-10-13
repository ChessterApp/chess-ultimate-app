'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { CheckCircle2, Lightbulb, MessageCircle, RotateCcw, X, XCircle } from 'lucide-react';
import { canCheck, type StepFlowState } from '@/lib/coach/step-flow';

export interface StepFeedback {
  /** The move to show in the verdict line ("Отлично! 13.Nc7+"). */
  san?: string;
  explanation?: string;
  /** Motif chip, e.g. «вилка». */
  motif?: string;
  /** XP earned; the chip shows only when the XP is really credited. */
  xp?: number;
  /** A question chip that goes to the chat. */
  followUp?: { label: string; message: string };
}

interface StepFlowProps {
  title: string;
  state: StepFlowState;
  /** The question for the current step. */
  prompt: string;
  /** What to show once the step was checked (correct / wrong). */
  feedback?: StepFeedback | null;
  onHint?: () => void;
  onUndo?: () => void;
  onCheck: () => void;
  onRetry: () => void;
  onNext: () => void;
  onFollowUp?: (message: string) => void;
  onClose?: () => void;
}

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent)';

/**
 * A guided step (question → move on the board → «Проверить» → feedback →
 * «Дальше»). Generic: puzzles use it now, game-review moments later. The host
 * owns the board and feeds `state` from useStepFlow.
 */
export default function StepFlow({
  title,
  state,
  prompt,
  feedback,
  onHint,
  onUndo,
  onCheck,
  onRetry,
  onNext,
  onFollowUp,
  onClose,
}: StepFlowProps) {
  const t = useTranslations('coach');
  const { phase, total } = state;
  const step = Math.min(state.index, total - 1);
  const checked = phase === 'correct' || phase === 'wrong';

  return (
    <section
      className="w-full overflow-hidden rounded-xl border border-(--coach-border) bg-(--coach-surface)"
      aria-labelledby="step-flow-title"
      data-testid="step-flow"
      data-phase={phase}
    >
      {/* Header: title, «Шаг N из M», progress dots */}
      <div className="flex items-center gap-3 px-3 pt-3">
        <div className="min-w-0 flex-1">
          <h2 id="step-flow-title" className="truncate text-sm font-semibold text-(--coach-text)">
            {title}
          </h2>
          {total > 1 && (
            <p className="text-xs text-(--coach-muted)">{t('stepOf', { n: step + 1, total })}</p>
          )}
        </div>
        {total > 1 && <ProgressDots index={step} total={total} done={phase === 'correct'} label={t('stepProgress')} />}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={t('puzzleExit')}
            className={`-mr-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-(--coach-muted) hover:bg-white/5 hover:text-(--coach-text) ${focusRing}`}
          >
            <X size={18} aria-hidden />
          </button>
        )}
      </div>

      <p className="px-3 pt-2 text-base leading-snug text-(--coach-text)" data-testid="step-prompt">
        {prompt}
      </p>

      {checked && feedback ? (
        <FeedbackPanel correct={phase === 'correct'} feedback={feedback} onFollowUp={onFollowUp} onNext={onNext} onRetry={onRetry} />
      ) : (
        <div className="px-3 pt-2 pb-3">
          <p className="text-xs text-(--coach-muted)" aria-live="polite">
            {phase === 'checking' ? t('stepChecking') : phase === 'moved' ? t('stepMoved') : t('stepMakeMove')}
          </p>
          <div className="mt-2 flex gap-2">
            {onHint && (
              <button
                type="button"
                onClick={onHint}
                disabled={phase === 'checking'}
                className={`flex min-h-11 flex-1 items-center justify-center gap-1.5 truncate rounded-xl border border-(--coach-border) px-3 text-sm text-(--coach-text) transition-colors hover:bg-white/5 active:bg-white/10 disabled:opacity-40 ${focusRing}`}
              >
                <Lightbulb size={16} aria-hidden />
                {t('gameHint')}
              </button>
            )}
            {onUndo && phase === 'moved' && (
              <button
                type="button"
                onClick={onUndo}
                aria-label={t('stepUndo')}
                title={t('stepUndo')}
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-(--coach-border) text-(--coach-muted) transition-colors hover:bg-white/5 hover:text-(--coach-text) ${focusRing}`}
              >
                <RotateCcw size={16} aria-hidden />
              </button>
            )}
            <button
              type="button"
              onClick={onCheck}
              disabled={!canCheck(state)}
              className={`min-h-11 flex-1 truncate rounded-xl bg-(--coach-accent) px-3 text-sm font-semibold text-white transition hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-(--coach-muted) ${focusRing}`}
            >
              {t('stepCheck')}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function ProgressDots({ index, total, done, label }: { index: number; total: number; done: boolean; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={1}
      aria-valuemax={total}
      aria-valuenow={index + 1}
      className="flex shrink-0 items-center gap-1"
    >
      {Array.from({ length: Math.min(total, 12) }, (_, i) => (
        <span
          key={i}
          className={`h-1.5 rounded-full transition-all ${
            i < index || (i === index && done)
              ? 'w-1.5 bg-(--coach-accent)'
              : i === index
                ? 'w-4 bg-(--coach-accent)'
                : 'w-1.5 bg-white/15'
          }`}
        />
      ))}
    </div>
  );
}

function FeedbackPanel({
  correct,
  feedback,
  onFollowUp,
  onNext,
  onRetry,
}: {
  correct: boolean;
  feedback: StepFeedback;
  onFollowUp?: (message: string) => void;
  onNext: () => void;
  onRetry: () => void;
}) {
  const t = useTranslations('coach');
  const Icon = correct ? CheckCircle2 : XCircle;
  return (
    <div
      className={`animate-fade-in mt-3 px-3 pt-3 pb-3 ${correct ? 'bg-(--coach-success-soft)' : 'bg-(--coach-danger-soft)'}`}
      role="status"
      data-testid="step-feedback"
    >
      <p className={`flex items-center gap-2 text-base font-semibold ${correct ? 'text-(--coach-success)' : 'text-(--coach-danger)'}`}>
        <Icon size={20} aria-hidden />
        <span>
          {correct ? t('stepCorrect') : t('stepWrong')}
          {feedback.san ? ` ${feedback.san}` : ''}
        </span>
      </p>
      {feedback.explanation && <p className="mt-1 text-sm text-(--coach-text)">{feedback.explanation}</p>}
      {(feedback.motif || feedback.xp || feedback.followUp) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          {feedback.motif && (
            <span className="rounded-full bg-(--coach-accent-soft) px-2.5 py-1 text-(--coach-text)">{feedback.motif}</span>
          )}
          {!!feedback.xp && correct && (
            <span className="font-semibold text-(--coach-success)" data-testid="step-xp">
              {t('stepXp', { xp: feedback.xp })}
            </span>
          )}
          {feedback.followUp && onFollowUp && (
            <button
              type="button"
              onClick={() => onFollowUp(feedback.followUp!.message)}
              className={`flex min-h-11 items-center gap-1.5 rounded-full border border-(--coach-border) px-3 text-(--coach-text) transition-colors hover:bg-white/5 active:bg-white/10 ${focusRing}`}
            >
              <MessageCircle size={14} aria-hidden />
              {feedback.followUp.label}
            </button>
          )}
        </div>
      )}
      <button
        type="button"
        autoFocus
        onClick={correct ? onNext : onRetry}
        className={`mt-3 min-h-12 w-full rounded-xl px-4 text-base font-semibold transition hover:brightness-110 active:brightness-95 ${focusRing} ${
          correct ? 'bg-(--coach-success) text-white' : 'bg-white/10 text-(--coach-text)'
        }`}
      >
        {correct ? t('stepNext') : t('stepRetry')}
      </button>
    </div>
  );
}
