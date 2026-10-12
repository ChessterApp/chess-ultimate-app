'use client';

import { useEffect, useState } from 'react';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import type { ResultTile } from '@/lib/puzzle-rush/runReducer';
import { MAX_STRIKES } from '@/lib/puzzle-rush/runReducer';
import type { RetryOutcome, RetryOutcomes } from '@/lib/puzzle-rush/retryReducer';
import { MODE_SECONDS, type RushMode } from '@/lib/puzzle-rush/types';
import styles from './PuzzleRush.module.css';

export const LOGO_SRC = '/static/images/chesster-logo-v3.png';

/** m:ss — countdowns round up (never show 0:00 early), elapsed time rounds down. */
export function formatClock(ms: number, round: 'up' | 'down' = 'up'): string {
  const secs = Math.max(0, ms / 1000);
  const total = round === 'up' ? Math.ceil(secs) : Math.floor(secs);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function ScoreTile({ score }: { score: number }) {
  const t = useTranslations('puzzleRush.run');
  return (
    <div className={`${styles.tile} ${styles.tileScore}`}>
      {/* Re-keyed per score so the pulse replays on every solve. */}
      <div key={score} className={`${styles.tileScoreNum} ${score > 0 ? styles.pulse : ''}`} data-testid="rush-score">
        {score}
      </div>
      <div className={styles.tileLabel}>{t('solved')}</div>
    </div>
  );
}

interface TimerProps {
  mode: RushMode;
  startedAtMs: number | null;
  deadlineMs: number | null;
  running: boolean;
  /** Final value to show once the run is over (ms remaining / elapsed). */
  frozenMs?: number | null;
}

/** Timed modes count down to the run's deadline; Survival shows elapsed time. */
export function TimerTile({ mode, startedAtMs, deadlineMs, running, frozenMs = null }: TimerProps) {
  const t = useTranslations('puzzleRush.run');
  // Same monotonic clock as the run engine (startedAtMs / deadlineMs).
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(performance.now()), 250);
    return () => clearInterval(id);
  }, [running]);

  const full = (MODE_SECONDS[mode] ?? 0) * 1000;
  const survival = MODE_SECONDS[mode] === null;
  let ms: number;
  if (frozenMs !== null) ms = frozenMs;
  else if (survival) ms = startedAtMs ? Math.max(0, now - startedAtMs) : 0;
  else ms = deadlineMs ? Math.min(full, Math.max(0, deadlineMs - now)) : full;
  const low = !survival && running && ms <= 10_000;

  return (
    <div className={`${styles.tile} ${styles.tileTimer}`}>
      <div>
        <div className={styles.tileLabel}>{survival ? t('time') : t('timeLeft')}</div>
        <div className={`${styles.tileTimerNum} ${low ? styles.timerLow : ''}`} data-testid="rush-timer">
          {formatClock(ms, survival ? 'down' : 'up')}
        </div>
      </div>
      <span className={styles.tileEmoji} aria-hidden="true">⏱️</span>
    </div>
  );
}

export function StrikesTile({ strikes }: { strikes: number }) {
  const t = useTranslations('puzzleRush.run');
  const left = Math.max(0, MAX_STRIKES - strikes);
  return (
    <div className={`${styles.tile} ${styles.tileStrikes}`}>
      <div className={styles.tileLabel}>{t('strikes')}</div>
      <div className={styles.hearts} role="img" aria-label={t('heartsLeft', { left })}>
        {Array.from({ length: MAX_STRIKES }, (_, i) => {
          // Hearts are lost left to right.
          const gone = i < strikes;
          return (
            <span key={i} className={`${styles.heart} ${gone ? styles.heartGone : ''}`} data-testid={gone ? 'heart-gone' : 'heart'}>
              {gone ? '💔' : '❤️'}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** A tile's state for its accessible label: run result, or a ✕ solved in Retry mode. */
export type TileState = 'solved' | 'missed' | 'retried' | 'retriedHelp';

export function tileState(tile: ResultTile, outcome?: RetryOutcome): TileState {
  if (tile.solved) return 'solved';
  if (outcome === 'solved') return 'retried';
  return outcome === 'solved_with_help' ? 'retriedHelp' : 'missed';
}

interface GridProps {
  tiles: ResultTile[];
  /** Summary layout: 10 per row, every tile clickable. */
  summary?: boolean;
  selected?: number | null;
  /** Retry-mode outcomes: a ✕ solved on retry renders amber ↻✓. */
  outcomes?: RetryOutcomes;
  onSelect?: (index: number) => void;
  puzzleLabel?: (n: number, state: TileState) => string;
  /** Tooltip for the "hint / solution used" marker. */
  helpTitle?: string;
}

export function ResultsGrid({ tiles, summary = false, selected = null, outcomes, onSelect, puzzleLabel, helpTitle }: GridProps) {
  if (tiles.length === 0) return null;
  return (
    <div className={`${styles.grid} ${summary ? styles.gridSummary : ''}`} data-testid="rush-grid">
      {tiles.map((tile) => {
        const outcome = outcomes?.[tile.index];
        const state = tileState(tile, outcome);
        const retried = state === 'retried' || state === 'retriedHelp';
        const tone = tile.solved ? styles.cellOk : retried ? styles.cellRetry : styles.cellFail;
        const cls = `${styles.cell} ${tone} ${selected === tile.index ? styles.cellSelected : ''}`;
        const inner = (
          <>
            <span className={styles.cellMark}>{tile.solved ? '✓' : retried ? '↻✓' : '✕'}</span>
            <span className={styles.cellRating}>{tile.rating}</span>
            {state === 'retriedHelp' && (
              <span className={styles.cellHelp} title={helpTitle} aria-hidden="true" data-testid="cell-help" />
            )}
          </>
        );
        const data = { 'data-result': tile.solved ? 'solved' : 'failed', 'data-retry': retried ? outcome : undefined };
        return onSelect ? (
          <button
            key={tile.index}
            type="button"
            className={cls}
            onClick={() => onSelect(tile.index)}
            aria-pressed={selected === tile.index}
            aria-label={puzzleLabel?.(tile.index + 1, state)}
            {...data}
          >
            {inner}
          </button>
        ) : (
          <span key={tile.index} className={cls} {...data}>
            {inner}
          </span>
        );
      })}
    </div>
  );
}

export function CoachToast({ text }: { text: string }) {
  return (
    <div className={styles.coach} role="status" data-testid="rush-coach">
      <span className={styles.coachMark}>
        <Image src={LOGO_SRC} alt="" width={26} height={26} unoptimized />
      </span>
      <span className={styles.coachText}>{text}</span>
    </div>
  );
}
