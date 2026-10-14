'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';

/** Quick reasons, sent as a stable code in front of the free text. */
export const FEEDBACK_REASONS = [
  { code: 'wrong', key: 'feedbackReasonWrong' },
  { code: 'unclear', key: 'feedbackReasonUnclear' },
  { code: 'off_topic', key: 'feedbackReasonOffTopic' },
] as const;

/** Hermes keeps the first 500 characters of a comment (coach_feedback.COMMENT_MAX). */
export const COMMENT_MAX = 500;

export type FeedbackReason = (typeof FEEDBACK_REASONS)[number]['code'];

/** «wrong: the bishop is on c4» — the reason code, then the student's words; '' when neither. */
export function feedbackComment(reason: FeedbackReason | null, text: string): string {
  const words = text.trim();
  return [reason, words].filter(Boolean).join(': ').slice(0, COMMENT_MAX);
}

interface FeedbackSheetProps {
  onSend: (comment: string) => void;
  onClose: () => void;
}

/**
 * «Что не так?» after a 👎: three quick reasons and an optional line of text.
 * A bottom sheet on phones, a centred card on desktop; Esc / the backdrop / ✕
 * close it without sending. Portalled to <body> (the coach sheet may be
 * transformed), so it carries the coach theme itself.
 */
export default function FeedbackSheet({ onSend, onClose }: FeedbackSheetProps) {
  const t = useTranslations('coach');
  const [reason, setReason] = useState<FeedbackReason | null>(null);
  const [text, setText] = useState('');
  const firstRef = useRef<HTMLButtonElement>(null);
  const comment = feedbackComment(reason, text);

  useEffect(() => {
    firstRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const chip =
    'min-h-11 rounded-full border px-3.5 text-[13.5px] font-medium transition-colors hover:border-(--coach-accent) active:bg-(--coach-accent-soft) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)';

  return createPortal(
    <div className="coach-theme fixed inset-0 z-[70] flex items-end justify-center lg:items-center" data-testid="feedback-sheet">
      <div className="animate-fade-in absolute inset-0 bg-black/60" onClick={onClose} aria-hidden />
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-sheet-title"
        onSubmit={(e) => {
          e.preventDefault();
          if (comment) onSend(comment);
        }}
        className="animate-fade-in relative w-full max-w-md rounded-t-2xl border border-(--coach-border) bg-(--coach-surface) px-4 pt-2 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-2xl lg:rounded-2xl lg:pt-4 lg:pb-4"
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-(--coach-grabber) lg:hidden" aria-hidden />
        <div className="flex items-center justify-between">
          <h2 id="feedback-sheet-title" className="text-lg font-semibold text-(--coach-text)">
            {t('feedbackSheetTitle')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('cancel')}
            className="-mr-2 flex h-11 w-11 items-center justify-center rounded-full text-(--coach-muted) hover:bg-white/5 hover:text-(--coach-text) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
          >
            <X size={20} aria-hidden />
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label={t('feedbackSheetTitle')}>
          {FEEDBACK_REASONS.map((r, i) => {
            const on = reason === r.code;
            return (
              <button
                key={r.code}
                ref={i === 0 ? firstRef : undefined}
                type="button"
                aria-pressed={on}
                onClick={() => setReason(on ? null : r.code)}
                data-testid={`feedback-reason-${r.code}`}
                className={`${chip} ${
                  on
                    ? 'border-(--coach-accent) bg-(--coach-accent-soft) text-(--coach-accent-text)'
                    : 'border-(--coach-border) bg-(--coach-surface-2) text-(--coach-text)'
                }`}
              >
                {t(r.key)}
              </button>
            );
          })}
        </div>
        <label className="mt-4 block text-sm text-(--coach-muted)" htmlFor="feedback-comment">
          {t('feedbackCommentLabel')}
        </label>
        <textarea
          id="feedback-comment"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={COMMENT_MAX}
          rows={3}
          placeholder={t('feedbackCommentPlaceholder')}
          data-testid="feedback-comment"
          // 16px on phones: iOS Safari zooms into smaller fields.
          className="mt-1.5 w-full resize-none rounded-xl border border-(--coach-border) bg-(--coach-surface-2) px-3 py-2 text-base text-(--coach-text) placeholder:text-(--coach-muted) focus:border-(--coach-accent) focus:outline-none sm:text-sm"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 rounded-full px-4 text-sm text-(--coach-muted) hover:bg-white/5 hover:text-(--coach-text) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
          >
            {t('feedbackSkip')}
          </button>
          <button
            type="submit"
            disabled={!comment}
            data-testid="feedback-send"
            className="min-h-11 rounded-full bg-(--coach-accent) px-5 text-sm font-semibold text-white transition-opacity hover:opacity-90 active:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent) disabled:opacity-40"
          >
            {t('feedbackSend')}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
