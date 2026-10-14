'use client';

import React, { useCallback, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import FeedbackSheet from './FeedbackSheet';

type Rating = 1 | -1 | 0;

interface FeedbackButtonsProps {
  /** Turn correlation id of the completed answer this feedback refers to. */
  turnId: string;
  sessionId: string | null;
  surface?: 'text' | 'voice' | 'review';
}

/**
 * 👍/👎 under a completed coach answer. Optimistic: the chosen thumb highlights
 * immediately and the verdict POSTs to `/api/coach/feedback`. Clicking the same
 * thumb retracts (rating 0); clicking the other switches. A network failure
 * silently reverts — feedback is a LOG-ONLY signal and must never interrupt the
 * chat flow (no error toast). A 👎 also opens «Что не так?» (FeedbackSheet):
 * its optional comment re-sends the 👎 with `comment` (Hermes upserts the turn).
 */
export default function FeedbackButtons({
  turnId,
  sessionId,
  surface = 'text',
}: FeedbackButtonsProps) {
  const t = useTranslations('coach');
  // Verdict shown in the UI (optimistic). 0 = no verdict.
  const [rating, setRating] = useState<Rating>(0);
  const [askWhy, setAskWhy] = useState(false);

  const send = useCallback(
    async (next: Rating, previous: Rating, comment?: string) => {
      try {
        const res = await fetch('/api/coach/feedback', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            turn_id: turnId,
            session_id: sessionId ?? undefined,
            rating: next,
            surface,
            ...(comment ? { comment } : {}),
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      } catch {
        // Silent revert — never interrupt the chat with a feedback error.
        setRating(previous);
      }
    },
    [turnId, sessionId, surface]
  );

  const vote = useCallback(
    (choice: 1 | -1) => {
      const previous = rating;
      // Re-click the active thumb → retract; otherwise set/switch.
      const next: Rating = rating === choice ? 0 : choice;
      setRating(next); // optimistic
      void send(next, previous);
      if (next === -1) setAskWhy(true);
    },
    [rating, send]
  );

  const closeSheet = useCallback(() => setAskWhy(false), []);
  const sendComment = useCallback(
    (comment: string) => {
      setAskWhy(false);
      void send(-1, -1, comment);
    },
    [send]
  );

  // 44px targets; the icons keep their 14px look.
  const base =
    'flex h-11 w-11 items-center justify-center rounded-full transition-colors text-(--coach-muted) hover:text-(--coach-text) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)';
  const active = 'text-(--coach-accent-text) hover:text-(--coach-accent-text)';

  return (
    <div
      className="-ml-3 flex items-center"
      data-testid="feedback-buttons"
    >
      <button
        type="button"
        onClick={() => vote(1)}
        aria-label={t('feedbackGood')}
        aria-pressed={rating === 1}
        title={t('feedbackGood')}
        data-testid="feedback-up"
        className={`${base} ${rating === 1 ? active : ''}`}
      >
        <ThumbsUp size={14} />
      </button>
      <button
        type="button"
        onClick={() => vote(-1)}
        aria-label={t('feedbackBad')}
        aria-pressed={rating === -1}
        title={t('feedbackBad')}
        data-testid="feedback-down"
        className={`${base} ${rating === -1 ? active : ''}`}
      >
        <ThumbsDown size={14} />
      </button>
      {askWhy && <FeedbackSheet onSend={sendComment} onClose={closeSheet} />}
    </div>
  );
}
