'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import type { ReviewResult } from './types';
import CoachBubble from './CoachBubble';
import CoachDrawer from './CoachDrawer';
import GameRecap from './GameRecap';
import MoveList from './MoveList';
import ReviewSounds from './ReviewSounds';
import { useReviewCoach } from '@/hooks/useReviewCoach';
import type { CoachArrow } from '@/lib/coach/review-markup';

export interface ReviewPanelProps {
  data: ReviewResult;
  /** 1-based current ply (0 = start position). */
  currentPly: number;
  onSetPly: (ply: number) => void;
  /** Return to the Highlights summary. */
  onExitReview: () => void;
  /** The current move's Explain arrows/highlights, for the review board. */
  onCoachShapes?: (arrows: CoachArrow[], squares: string[]) => void;
}

/**
 * Review-mode sidebar: Highlights/Coach row → coach bubble → annotated
 * move list, plus the sound player. The playback replay bar now lives under
 * the board (page.tsx), not here. One layout, both themes via the review CSS
 * vars.
 */
export default function ReviewPanel({
  data,
  currentPly,
  onSetPly,
  onExitReview,
  onCoachShapes,
}: ReviewPanelProps) {
  const t = useTranslations('gameReview');
  const params = useParams<{ id: string }>();
  const gameId = params?.id ?? '';
  const currentMove = currentPly >= 1 ? data.moves[currentPly - 1] : null;
  const prevMove = currentPly >= 2 ? data.moves[currentPly - 2] : null;

  // F5 Coach Drawer (v1.1) — on-demand chat/voice coach. Zero space at rest;
  // the default analysis below stays mounted and visible when it's open.
  const [coachOpen, setCoachOpen] = useState(false);

  // Review Coach v1 (F1 Explain + F3 recap).
  const coach = useReviewCoach();
  const openingInfo = { name: data.opening?.name, lastBookPly: data.opening?.lastBookPly };
  const currentCoach = currentMove
    ? coach.explainByKey[coach.explainKeyFor(currentMove)]
    : undefined;

  // The explanation's [[arrows: …]] marks are drawn on the review board.
  const coachArrows = currentCoach?.arrows;
  const coachSquares = currentCoach?.squares;
  useEffect(() => {
    onCoachShapes?.(coachArrows ?? [], coachSquares ?? []);
  }, [onCoachShapes, coachArrows, coachSquares]);
  useEffect(() => () => onCoachShapes?.([], []), [onCoachShapes]);

  return (
    <aside
      data-testid="review-sidebar"
      data-mode="review"
      style={{ width: 430, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <button
          type="button"
          data-testid="exit-review"
          onClick={onExitReview}
          className="review-ghost-btn"
          style={{ padding: '6px 12px', fontSize: 13 }}
        >
          {t('panel.highlights')}
        </button>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            data-testid="coach-drawer-toggle"
            aria-expanded={coachOpen}
            onClick={() => setCoachOpen((o) => !o)}
            style={{
              padding: '6px 14px',
              fontSize: 13,
              fontWeight: 800,
              borderRadius: 999,
              color: '#ffffff',
              background: '#14b8a6',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            ♞ {t('coach.drawer.open')}
          </button>
        </div>
      </div>

      <GameRecap recap={coach.recap} onRecap={() => coach.recapGame(data)} />

      <CoachBubble
        move={currentMove}
        prev={prevMove}
        opening={openingInfo}
        coach={currentCoach}
        onExplain={
          currentMove
            ? () => coach.explainMove(currentMove, prevMove, openingInfo)
            : undefined
        }
      />

      <MoveList moves={data.moves} currentPly={currentPly} onSelect={onSetPly} />

      <ReviewSounds currentPly={currentPly} move={currentMove} muted={false} />

      <CoachDrawer
        open={coachOpen}
        onClose={() => setCoachOpen(false)}
        gameId={gameId}
        move={currentMove}
      />
    </aside>
  );
}
