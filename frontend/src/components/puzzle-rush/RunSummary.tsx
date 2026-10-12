'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Chess } from 'chess.js';
import type { Key } from 'chessground/types';
import type { ResultTile, ReviewAttempt } from '@/lib/puzzle-rush/runReducer';
import type { EndReason, RushMode } from '@/lib/puzzle-rush/types';
import { ResultsGrid } from './RunTiles';
import styles from './PuzzleRush.module.css';

interface ReviewLine {
  /** FEN after each ply; [0] is the position before the setup move. */
  fens: string[];
  sans: string[];
  lastMoves: ([Key, Key] | null)[];
  orientation: 'white' | 'black';
}

export function buildReviewLine(attempt: ReviewAttempt): ReviewLine | null {
  if (!attempt.solution.length) return null;
  const chess = new Chess(attempt.fen);
  // The user plays the side NOT to move in the stored FEN.
  const orientation = chess.turn() === 'w' ? 'black' : 'white';
  const fens = [chess.fen()];
  const sans: string[] = [];
  const lastMoves: ([Key, Key] | null)[] = [null];
  for (const uci of attempt.solution) {
    try {
      const m = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] || undefined });
      fens.push(chess.fen());
      sans.push(m.san);
      lastMoves.push([m.from as Key, m.to as Key]);
    } catch {
      break;
    }
  }
  return { fens, sans, lastMoves, orientation };
}

/** SAN for the user's own moves in a missed puzzle (played after the setup move). */
function userSans(attempt: ReviewAttempt): string[] {
  if (!attempt.solution.length) return attempt.user_moves;
  try {
    const chess = new Chess(attempt.fen);
    const line = [attempt.solution[0]];
    attempt.user_moves.forEach((m, i) => {
      line.push(m);
      if (i < attempt.user_moves.length - 1 && attempt.solution[2 * i + 2]) line.push(attempt.solution[2 * i + 2]);
    });
    const out: string[] = [];
    line.forEach((uci, i) => {
      const mv = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] || undefined });
      if (i % 2 === 1) out.push(mv.san);
    });
    return out;
  } catch {
    return attempt.user_moves;
  }
}

/**
 * In-page missed-puzzle review, offline: the solutions are already in the
 * run's pack (`reviewAttempts`). `runId` resets the selection per run.
 */
export function useRunReview(runId: string | null, attempts: ReviewAttempt[]) {
  const [selected, setSelected] = useState<number | null>(null);
  const [step, setStep] = useState(1);

  // New run → drop the previous run's selection (reset during render, not in an effect).
  const [forRun, setForRun] = useState(runId);
  if (forRun !== runId) {
    setForRun(runId);
    setSelected(null);
  }

  const select = useCallback((index: number) => {
    setSelected((cur) => (cur === index ? null : index));
    setStep(1);
  }, []);

  const attempt = selected === null ? null : attempts.find((a) => a.index === selected) ?? null;
  const line = useMemo(() => (attempt ? buildReviewLine(attempt) : null), [attempt]);
  const maxStep = line ? line.fens.length - 1 : 0;

  const stepBy = useCallback((delta: number) => {
    setStep((s) => Math.min(Math.max(s + delta, 1), Math.max(maxStep, 1)));
  }, [maxStep]);

  const close = useCallback(() => setSelected(null), []);

  // ← / → step through the solution while the drawer is open.
  useEffect(() => {
    if (selected === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') stepBy(-1);
      else if (e.key === 'ArrowRight') stepBy(1);
      else if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, stepBy, close]);

  const board = line
    ? { fen: line.fens[step], lastMove: line.lastMoves[step], orientation: line.orientation }
    : null;

  return { selected, select, close, attempt, line, step, maxStep, stepBy, board };
}

type Review = ReturnType<typeof useRunReview>;

interface Props {
  mode: RushMode;
  score: number;
  tiles: ResultTile[];
  endReason: EndReason | null;
  review: Review;
  onPlayAgain: () => void;
  onNewRush: () => void;
}

/** S10: score, clickable ✓/✕ grid, review drawer, Play Again / New Rush. */
export default function RunSummary({ mode, score, tiles, endReason, review, onPlayAgain, onNewRush }: Props) {
  const t = useTranslations('puzzleRush');
  const { selected, attempt, line, step, maxStep, stepBy, close } = review;

  return (
    <div data-testid="rush-summary">
      <div className={styles.summaryHead}>
        <div>
          <div className={styles.summaryScore}>{score}</div>
          <div className={styles.tileLabel}>{t('run.solved')}</div>
        </div>
        <div className={styles.summaryMeta}>
          {t(`modes.${mode}.title`)}
          {endReason && <div>{t(`results.end.${endReason}`)}</div>}
        </div>
      </div>

      {tiles.length > 0 && <p className={styles.summaryHint}>{t('summary.hint')}</p>}
      <ResultsGrid
        tiles={tiles}
        summary
        selected={selected}
        onSelect={review.select}
        puzzleLabel={(n) => t('summary.puzzle', { n })}
      />

      {selected !== null && (
        <section className={styles.drawer} aria-label={t('summary.puzzle', { n: selected + 1 })} data-testid="rush-review">
          <div className={styles.drawerHead}>
            <h3 className={styles.drawerTitle}>
              {t('summary.puzzle', { n: selected + 1 })}
              {attempt ? ` · ${attempt.rating}` : ''}
            </h3>
            {attempt && (
              <span className={`${styles.tag} ${attempt.result === 'solved' ? styles.tagOk : styles.tagFail}`}>
                {attempt.result === 'solved' ? t('summary.solvedTag') : t('summary.missedTag')}
              </span>
            )}
            <button type="button" className={styles.textButton} onClick={close} aria-label={t('summary.closeReview')}>✕</button>
          </div>
          {attempt && attempt.result !== 'solved' && attempt.user_moves.length > 0 && (
            <p className={styles.drawerLine}>{t('summary.yourMoves', { moves: userSans(attempt).join(' ') })}</p>
          )}
          {line && (
            <>
              <p className={styles.drawerLine}>{t('summary.solution')}</p>
              <div className={styles.moves}>
                {line.sans.map((san, i) => (
                  <span key={i} className={`${styles.moveChip} ${i + 1 === step ? styles.moveChipOn : ''}`}>{san}</span>
                ))}
              </div>
              <div className={styles.stepper}>
                <button type="button" className={styles.stepButton} onClick={() => stepBy(-1)} disabled={step <= 1} aria-label={t('summary.prev')}>‹</button>
                <span className={styles.stepCount}>{t('summary.step', { n: step, total: maxStep })}</span>
                <button type="button" className={styles.stepButton} onClick={() => stepBy(1)} disabled={step >= maxStep} aria-label={t('summary.next')}>›</button>
              </div>
            </>
          )}
        </section>
      )}

      <div className={styles.buttonRow}>
        <button type="button" className={styles.cta} onClick={onPlayAgain}>{t('results.playAgain')}</button>
        <button type="button" className={styles.ghostButton} onClick={onNewRush}>{t('results.newRush')}</button>
      </div>
    </div>
  );
}
