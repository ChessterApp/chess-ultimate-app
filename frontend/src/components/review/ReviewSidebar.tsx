'use client';

import { useTranslations } from 'next-intl';
import type { ReviewResult } from './types';
import CoachIntro from './CoachIntro';
import AccuracyCard from './AccuracyCard';
import PlayersAccuracyRow from './PlayersAccuracyRow';
import TallyTable from './TallyTable';
import GameRating from './GameRating';
import PhaseStats from './PhaseStats';
import ReviewPanel from './ReviewPanel';
import type { CoachArrow } from '@/lib/coach/review-markup';

export interface SidebarPlayer {
  name: string;
  rating?: number;
}

export interface ReviewSidebarProps {
  data: ReviewResult;
  mode: 'highlights' | 'review';
  white: SidebarPlayer;
  black: SidebarPlayer;
  onStartReview: () => void;
  /** Review-mode wiring (Phase 4). */
  currentPly: number;
  onSetPly: (ply: number) => void;
  onExitReview: () => void;
  onCoachShapes?: (arrows: CoachArrow[], squares: string[]) => void;
}

/** Minimal shape of the `gameReview` translator used by {@link coachCopy}. */
type CoachTranslate = (key: string, values?: Record<string, string | number>) => string;

/** Build a short, deterministic coach greeting from the aggregates. */
function coachCopy(t: CoachTranslate, data: ReviewResult): { headline: string; message: string } {
  const brilliancies = data.tally.w.brilliant + data.tally.b.brilliant;
  const blunders = data.tally.w.blunder + data.tally.b.blunder;
  const best = Math.max(data.accuracy.w, data.accuracy.b).toFixed(1);
  if (brilliancies > 0) {
    return {
      headline: t('coach.headlines.brilliant'),
      message: t('coach.messages.brilliant', { count: brilliancies }),
    };
  }
  if (blunders === 0) {
    return {
      headline: t('coach.headlines.clean'),
      message: t('coach.messages.clean', { best }),
    };
  }
  return {
    headline: t('coach.headlines.review'),
    message: t('coach.messages.review', { best }),
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
  onStartReview,
  currentPly,
  onSetPly,
  onExitReview,
  onCoachShapes,
}: ReviewSidebarProps) {
  const t = useTranslations('gameReview');
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

  const copy = coachCopy(t, data);

  return (
    <aside
      data-testid="review-sidebar"
      data-mode="highlights"
      style={{ width: 430, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 14 }}
    >
      <CoachIntro
        openingName={data.opening?.name || undefined}
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
