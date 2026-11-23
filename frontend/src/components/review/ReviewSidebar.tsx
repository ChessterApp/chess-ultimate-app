'use client';

import { useLocale, useTranslations } from 'next-intl';
import type { ReviewResult } from './types';
import CoachIntro from './CoachIntro';
import AccuracyCard from './AccuracyCard';
import PlayersAccuracyRow from './PlayersAccuracyRow';
import TallyTable from './TallyTable';
import GameRating from './GameRating';
import PhaseStats from './PhaseStats';
import ReviewPanel from './ReviewPanel';
import type { CoachArrow } from '@/lib/coach/review-markup';
import { translateOpeningName } from '@/lib/openings/openingNamesI18n';

export interface SidebarPlayer {
  name: string;
  rating?: number;
}

export interface ReviewSidebarProps {
  data: ReviewResult;
  mode: 'highlights' | 'review';
  white: SidebarPlayer;
  black: SidebarPlayer;
  /** The colour the user played, when known; scopes the coach greeting to it. */
  userColor?: 'w' | 'b';
  onStartReview: () => void;
  /** Review-mode wiring (Phase 4). */
  currentPly: number;
  onSetPly: (ply: number) => void;
  onExitReview: () => void;
  onCoachShapes?: (arrows: CoachArrow[], squares: string[]) => void;
}

/** Minimal shape of the `gameReview` translator used by {@link coachCopy}. */
type CoachTranslate = (key: string, values?: Record<string, string | number>) => string;

/**
 * Build a short, deterministic coach greeting from the aggregates. With the
 * user's colour known it speaks only about the user's side; without it the
 * copy stays neutral so the opponent's (often the bot's) numbers are never
 * presented as the user's.
 */
export function coachCopy(
  t: CoachTranslate,
  data: ReviewResult,
  userColor?: 'w' | 'b',
): { headline: string; message: string } {
  const tally = userColor
    ? data.tally[userColor]
    : {
        brilliant: data.tally.w.brilliant + data.tally.b.brilliant,
        blunder: data.tally.w.blunder + data.tally.b.blunder,
      };
  const values: Record<string, string | number> = userColor
    ? { accuracy: data.accuracy[userColor].toFixed(1) }
    : { white: data.accuracy.w.toFixed(1), black: data.accuracy.b.toFixed(1) };
  const suffix = userColor ? '' : 'Neutral';
  if (tally.brilliant > 0) {
    return {
      headline: t('coach.headlines.brilliant'),
      message: t(`coach.messages.brilliant${suffix}`, { count: tally.brilliant }),
    };
  }
  if (tally.blunder === 0) {
    return {
      headline: t('coach.headlines.clean'),
      message: t(`coach.messages.clean${suffix}`, values),
    };
  }
  return {
    headline: t('coach.headlines.review'),
    message: t(`coach.messages.review${suffix}`, values),
  };
}

/**
 * Highlights-mode sidebar. The Start Review CTA flips the store to "review"
 * mode; the move-by-move stepper itself lands in Phase 4 (placeholder here).
 */
export default function ReviewSidebar({
  data,
  mode,
  white,
  black,
  userColor,
  onStartReview,
  currentPly,
  onSetPly,
  onExitReview,
  onCoachShapes,
}: ReviewSidebarProps) {
  const t = useTranslations('gameReview');
  const locale = useLocale();
  if (mode === 'review') {
    return (
      <ReviewPanel
        data={data}
        currentPly={currentPly}
        onSetPly={onSetPly}
        onExitReview={onExitReview}
        onCoachShapes={onCoachShapes}
      />
    );
  }

  const copy = coachCopy(t, data, userColor);

  return (
    <aside
      data-testid="review-sidebar"
      data-mode="highlights"
      style={{ width: 430, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <CoachIntro
        openingName={data.opening?.name ? translateOpeningName(data.opening.name, locale) : undefined}
        headline={copy.headline}
        message={copy.message}
      />

      <div className="review-accuracy-row" style={{ display: 'flex' }}>
        <AccuracyCard label={white.name} value={data.accuracy.w} color="var(--review-accent)" />
        <AccuracyCard label={black.name} value={data.accuracy.b} color="var(--review-text-dim)" />
      </div>

      <PlayersAccuracyRow
        white={{ name: white.name, rating: white.rating, color: 'w', accuracy: data.accuracy.w }}
        black={{ name: black.name, rating: black.rating, color: 'b', accuracy: data.accuracy.b }}
      />

      <TallyTable tally={data.tally} />

      <GameRating
        whiteRating={data.estRating.w}
        blackRating={data.estRating.b}
        whiteName={white.name}
        blackName={black.name}
      />

      <PhaseStats phases={data.phases} />

      <button
        type="button"
        data-testid="start-review-cta"
        className="review-cta"
        onClick={onStartReview}
        style={{ padding: '14px', fontSize: 16 }}
      >
        {t('panel.startReview')}
      </button>
    </aside>
  );
}
