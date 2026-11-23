'use client';

import { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  CBGoToStartIcon,
  CBPreviousMoveIcon,
  CBNextMoveIcon,
  CBGoToEndIcon,
  CBPlayIcon,
  CBPauseIcon,
} from '@/components/icons/ChessBaseNavIcons';

/**
 * The next key-moment ply strictly after `currentPly`, wrapping to the first
 * one when none remain; null only when there are no key moments at all.
 * Key moments arrive sorted from the backend; we defensively sort a copy.
 */
export function nextKeyMoment(keyMoments: number[], currentPly: number): number | null {
  const sorted = [...keyMoments].sort((a, b) => a - b);
  return sorted.find((ply) => ply > currentPly) ?? sorted[0] ?? null;
}

export interface PlaybackControlsProps {
  currentPly: number;
  maxPly: number;
  keyMoments: number[];
  /** Absolute jump (used by first/last and the key-moment Next). */
  onJump: (ply: number) => void;
  /** Relative step, clamped by the store (used by prev/next). */
  onStep: (delta: number) => void;
}

const seg: React.CSSProperties = {
  flex: 1,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  height: 44,
  border: 'none',
  borderRight: '1px solid var(--review-card-border)',
  background: 'transparent',
  color: 'var(--review-text)',
  cursor: 'pointer',
};

/**
 * first / prev / play-through / next / last + a "Next key moment" jump.
 * Rendered flush under the board as a full-width rounded segment row that
 * matches the ChessBase analysis-board control bar (shared CB SVG icons).
 * Play-through auto-advances ~1 move/sec and stops at the final ply; the play
 * button glows accent while auto-playing. Keyboard ←/→ is wired at the page
 * level and keeps working alongside these.
 */
export default function PlaybackControls({
  currentPly,
  maxPly,
  keyMoments,
  onJump,
  onStep,
}: PlaybackControlsProps) {
  const t = useTranslations('gameReview');
  const [playing, setPlaying] = useState(false);
  const atStart = currentPly <= 0;
  const atEnd = currentPly >= maxPly;
  const upcomingKeyMoment = nextKeyMoment(keyMoments, currentPly);
  // At the end there is nothing to advance to, so playback naturally idles.
  const showPlaying = playing && !atEnd;

  // Auto-advance timer. The step callback is read through a ref so a fresh
  // identity each render doesn't reset the running timer.
  const stepRef = useRef(onStep);
  useEffect(() => {
    stepRef.current = onStep;
  });
  useEffect(() => {
    if (!playing || currentPly >= maxPly) return;
    const timer = setTimeout(() => stepRef.current(1), 1000);
    return () => clearTimeout(timer);
  }, [playing, currentPly, maxPly]);

  return (
    <div
      data-testid="playback-controls"
      style={{
        display: 'flex',
        alignItems: 'stretch',
        width: '100%',
        borderRadius: 12,
        border: '1px solid var(--review-card-border)',
        background: 'var(--review-card)',
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        aria-label={t('playback.firstMove')}
        data-testid="pb-first"
        style={{ ...seg, opacity: atStart ? 0.35 : 1 }}
        disabled={atStart}
        onClick={() => onJump(0)}
      >
        <CBGoToStartIcon sx={{ width: 18, height: 14 }} />
      </button>
      <button
        type="button"
        aria-label={t('playback.previousMove')}
        data-testid="pb-prev"
        style={{ ...seg, opacity: atStart ? 0.35 : 1 }}
        disabled={atStart}
        onClick={() => onStep(-1)}
      >
        <CBPreviousMoveIcon sx={{ width: 14, height: 15 }} />
      </button>
      <button
        type="button"
        aria-label={showPlaying ? t('playback.pause') : t('playback.play')}
        data-testid="pb-play"
        style={{
          ...seg,
          flex: 1.4,
          color: showPlaying ? 'var(--review-accent)' : 'var(--review-text)',
          opacity: atEnd && !playing ? 0.35 : 1,
        }}
        onClick={() => setPlaying((p) => !p)}
        disabled={atEnd && !playing}
      >
        {showPlaying ? (
          <CBPauseIcon sx={{ width: 15, height: 16 }} />
        ) : (
          <CBPlayIcon sx={{ width: 15, height: 16 }} />
        )}
      </button>
      <button
        type="button"
        aria-label={t('playback.nextMove')}
        data-testid="pb-next"
        style={{ ...seg, opacity: atEnd ? 0.35 : 1 }}
        disabled={atEnd}
        onClick={() => onStep(1)}
      >
        <CBNextMoveIcon sx={{ width: 14, height: 15 }} />
      </button>
      <button
        type="button"
        aria-label={t('playback.lastMove')}
        data-testid="pb-last"
        style={{ ...seg, opacity: atEnd ? 0.35 : 1 }}
        disabled={atEnd}
        onClick={() => onJump(maxPly)}
      >
        <CBGoToEndIcon sx={{ width: 18, height: 14 }} />
      </button>
      <button
        type="button"
        aria-label={t('playback.nextKeyMoment')}
        data-testid="pb-keymoment"
        style={{
          ...seg,
          flex: 1.6,
          borderRight: 'none',
          gap: 6,
          fontSize: 13,
          fontWeight: 700,
          color: 'var(--review-accent)',
          opacity: upcomingKeyMoment == null ? 0.35 : 1,
        }}
        disabled={upcomingKeyMoment == null}
        onClick={() => upcomingKeyMoment != null && onJump(upcomingKeyMoment)}
      >
        {t('playback.next')}
      </button>
    </div>
  );
}
