'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Chess } from 'chess.js';
import type { Key } from 'chessground/types';
import type { ResultTile, ReviewAttempt } from '@/lib/puzzle-rush/runReducer';
import {
  isRetrySolved,
  nextMistakeIndex,
  recordOutcome,
  retryHint,
  retryReducer,
  type RetryAction,
  type RetryOutcomes,
  type RetryState,
} from '@/lib/puzzle-rush/retryReducer';
import type { EndReason, RushMode } from '@/lib/puzzle-rush/types';
import { ResultsGrid } from './RunTiles';
import styles from './PuzzleRush.module.css';

/** How long the ✕ stays on a rejected retry move before the piece snaps back. */
export const WRONG_HOLD_MS = 600;
/** Solution auto-play pace. */
export const SOLUTION_PLY_MS = 500;

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

interface Session {
  retry: RetryState | null;
  outcomes: RetryOutcomes;
}
const EMPTY_SESSION: Session = { retry: null, outcomes: {} };

/**
 * Post-run Retry mode, offline: the solutions are already in the run's pack
 * (`reviewAttempts`). Opening a puzzle makes it playable on the main board;
 * the per-run outcome map feeds the ✓/✕ grid. Never touches the run's
 * score or submitted result. `runId` resets everything per run.
 */
export function useRetry(runId: string | null, attempts: ReviewAttempt[], tiles: ResultTile[]) {
  const [session, setSession] = useState<Session>(EMPTY_SESSION);
  const [step, setStep] = useState(1);
  const [autoplay, setAutoplay] = useState(false);

  // New run → drop the previous run's retry state (reset during render, not in an effect).
  const [forRun, setForRun] = useState(runId);
  if (forRun !== runId) {
    setForRun(runId);
    setSession(EMPTY_SESSION);
  }

  const dispatch = useCallback((action: RetryAction) => {
    setSession((s) => {
      const retry = retryReducer(s.retry, action);
      return retry === s.retry ? s : { retry, outcomes: recordOutcome(s.outcomes, retry) };
    });
  }, []);

  const { retry, outcomes } = session;
  const selected = retry?.index ?? null;
  const attempt = selected === null ? null : attempts.find((a) => a.index === selected) ?? null;
  const line = useMemo(() => (attempt ? buildReviewLine(attempt) : null), [attempt]);
  const maxStep = line ? line.fens.length - 1 : 0;
  const status = retry?.status ?? null;

  const open = useCallback((index: number) => {
    const a = attempts.find((x) => x.index === index);
    if (!a || !a.solution.length) return;
    dispatch({ type: 'start', attempt: a });
    setAutoplay(false);
  }, [attempts, dispatch]);

  const close = useCallback(() => {
    setSession((s) => ({ ...s, retry: null }));
    setAutoplay(false);
  }, []);

  const move = useCallback((from: Key, to: Key, promotion?: string) => {
    dispatch({ type: 'move', uci: `${from}${to}${promotion ?? ''}` });
  }, [dispatch]);

  const hint = useCallback(() => dispatch({ type: 'hint' }), [dispatch]);

  const restart = useCallback(() => {
    dispatch({ type: 'retry' });
    setAutoplay(false);
  }, [dispatch]);

  const showSolution = useCallback(() => {
    if (!retry || status === 'solved' || status === 'revealed') return;
    dispatch({ type: 'showSolution' });
    // Play on from the current position.
    const from = Math.min(retry.ply, maxStep);
    setStep(from);
    setAutoplay(from < maxStep);
  }, [retry, status, maxStep, dispatch]);

  const stepBy = useCallback((delta: number) => {
    setStep((s) => Math.min(Math.max(s + delta, 1), Math.max(maxStep, 1)));
  }, [maxStep]);

  const next = nextMistakeIndex(tiles, outcomes, selected);
  const hasMisses = tiles.some((tile) => !tile.solved);
  const allReviewed = hasMisses && next === null;
  const nextMistake = useCallback(() => {
    if (next !== null) open(next);
  }, [next, open]);

  // Rejected move: hold the ✕, then snap the piece back.
  const lastWrong = retry?.lastWrong ?? null;
  useEffect(() => {
    if (!lastWrong) return;
    const id = setTimeout(() => dispatch({ type: 'clearWrong' }), WRONG_HOLD_MS);
    return () => clearTimeout(id);
  }, [lastWrong, dispatch]);

  // Solution auto-play, one ply at a time, then hand over to the ‹ › stepper.
  useEffect(() => {
    if (!autoplay || status !== 'revealed') return;
    const id = setTimeout(() => {
      setStep((s) => s + 1);
      if (step + 1 >= maxStep) setAutoplay(false);
    }, SOLUTION_PLY_MS);
    return () => clearTimeout(id);
  }, [autoplay, status, step, maxStep]);

  // ← / → step through a revealed solution; Esc leaves Retry mode.
  useEffect(() => {
    if (selected === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      else if (status === 'revealed' && !autoplay && e.key === 'ArrowLeft') stepBy(-1);
      else if (status === 'revealed' && !autoplay && e.key === 'ArrowRight') stepBy(1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected, status, autoplay, stepBy, close]);

  let board: {
    fen: string;
    lastMove: [Key, Key] | null;
    orientation: 'white' | 'black';
    movable: boolean;
    badge: { square: Key; kind: 'ok' | 'fail' } | null;
    hintSquare: Key | null;
    hintMove: [Key, Key] | null;
  } | null = null;
  if (retry && line) {
    const h = retryHint(retry);
    const base = { orientation: line.orientation, movable: false, badge: null, hintSquare: h.square, hintMove: h.move };
    if (retry.status === 'revealed') {
      board = { ...base, fen: line.fens[step], lastMove: line.lastMoves[step] };
    } else if (retry.lastWrong) {
      const w = retry.lastWrong;
      board = { ...base, fen: w.fen, lastMove: [w.from, w.square], badge: { square: w.square, kind: 'fail' } };
    } else {
      board = {
        ...base,
        fen: retry.fen,
        lastMove: retry.lastMove,
        movable: retry.status === 'playing',
        badge: retry.status === 'solved' && retry.lastMove ? { square: retry.lastMove[1], kind: 'ok' } : null,
      };
    }
  }

  return {
    selected, retry, outcomes, attempt, line, step, maxStep, autoplay, board,
    open, close, move, hint, restart, showSolution, stepBy, nextMistake,
    hasNext: next !== null, allReviewed,
  };
}

export type Retry = ReturnType<typeof useRetry>;

/** Above the board: the task, then ✕ / ✓ feedback, with the puzzle rating. */
export function RetryBanner({ review }: { review: Retry }) {
  const t = useTranslations('puzzleRush.retry');
  const { retry, attempt, line } = review;
  if (!retry || !attempt) return null;
  const status = retry.lastWrong ? 'wrong' : retry.status;
  const text = {
    playing: t(line?.orientation === 'black' ? 'findBlack' : 'findWhite'),
    wrong: t('incorrect'),
    solved: t('solved'),
    revealed: t('revealed'),
  }[status];
  return (
    <div className={styles.retryBanner} data-tone={status} role="status" data-testid="retry-banner">
      <span className={styles.retryBannerText}>
        {status === 'wrong' && <span aria-hidden="true">✕ </span>}
        {status === 'solved' && <span aria-hidden="true">✓ </span>}
        {text}
      </span>
      <span className={styles.retryBannerRating}>{t('rating', { rating: attempt.rating })}</span>
    </div>
  );
}

/** Under the board: what was played in the run, then Hint / Solution / Retry / Next mistake / Exit. */
export function RetryControls({ review, onPlayAgain }: { review: Retry; onPlayAgain: () => void }) {
  const t = useTranslations('puzzleRush');
  const { retry, attempt } = review;
  if (!retry || !attempt) return null;
  const live = retry.status === 'playing' || retry.status === 'wrong';
  const played = attempt.result !== 'solved' && attempt.user_moves.length > 0 ? userSans(attempt).join(' ') : null;

  return (
    <div className={styles.retryControls}>
      <p className={styles.retryPlayed}>{played ? t('retry.youPlayed', { moves: played }) : ' '}</p>
      <div className={styles.retryBar} role="toolbar" aria-label={t('retry.actions')}>
        <button type="button" className={styles.retryAction} onClick={review.hint} disabled={retry.status !== 'playing' || retry.hintLevel === 2}>
          <span aria-hidden="true">💡</span>{t('retry.hint')}
        </button>
        <button type="button" className={styles.retryAction} onClick={review.showSolution} disabled={!live}>
          <span aria-hidden="true">👁</span>{t('retry.solution')}
        </button>
        <button type="button" className={styles.retryAction} onClick={review.restart}>
          <span aria-hidden="true">↻</span>{t('retry.retry')}
        </button>
        <button type="button" className={`${styles.retryAction} ${styles.retryActionMain}`} onClick={review.nextMistake} disabled={!review.hasNext}>
          <span aria-hidden="true">→</span>{t('retry.nextMistake')}
        </button>
        <button type="button" className={styles.retryAction} onClick={review.close}>
          <span aria-hidden="true">✕</span>{t('retry.exit')}
        </button>
      </div>
      {review.allReviewed && (
        <div className={styles.retryDone} data-testid="retry-done">
          <span>✓ {t('retry.allReviewed')}</span>
          <button type="button" className={`${styles.cta} ${styles.retryDoneCta}`} onClick={onPlayAgain}>
            {t('results.playAgain')}
          </button>
        </div>
      )}
    </div>
  );
}

/** Side panel while retrying: which puzzle, how it went, and the solution stepper once revealed. */
function RetryPanel({ review }: { review: Retry }) {
  const t = useTranslations('puzzleRush');
  const { selected, retry, attempt, outcomes, line, step, maxStep, autoplay, stepBy } = review;
  if (selected === null || !retry) return null;
  const outcome = outcomes[selected];
  let tag: { text: string; cls: string } | null = null;
  if (attempt?.result === 'solved') tag = { text: t('summary.solvedTag'), cls: styles.tagOk };
  else if (isRetrySolved(outcome)) tag = { text: t(outcome === 'solved' ? 'retry.retriedTag' : 'retry.retriedHelpTag'), cls: styles.tagRetry };
  else if (attempt) tag = { text: t('summary.missedTag'), cls: styles.tagFail };

  return (
    <section className={styles.drawer} aria-label={t('summary.puzzle', { n: selected + 1 })} data-testid="rush-review">
      <div className={styles.drawerHead}>
        <h3 className={styles.drawerTitle}>
          {t('summary.puzzle', { n: selected + 1 })}
          {attempt ? ` · ${attempt.rating}` : ''}
        </h3>
        {tag && <span className={`${styles.tag} ${tag.cls}`}>{tag.text}</span>}
      </div>
      {retry.status === 'revealed' && line ? (
        <>
          <p className={styles.drawerLine}>{t('summary.solution')}</p>
          <div className={styles.moves}>
            {line.sans.map((san, i) => (
              <span key={i} className={`${styles.moveChip} ${i + 1 === step ? styles.moveChipOn : ''}`}>{san}</span>
            ))}
          </div>
          {!autoplay && (
            <div className={styles.stepper}>
              <button type="button" className={styles.stepButton} onClick={() => stepBy(-1)} disabled={step <= 1} aria-label={t('summary.prev')}>‹</button>
              <span className={styles.stepCount}>{t('summary.step', { n: step, total: maxStep })}</span>
              <button type="button" className={styles.stepButton} onClick={() => stepBy(1)} disabled={step >= maxStep} aria-label={t('summary.next')}>›</button>
            </div>
          )}
        </>
      ) : (
        <p className={styles.drawerLine}>{t('retry.panelHint')}</p>
      )}
    </section>
  );
}

interface Props {
  mode: RushMode;
  score: number;
  tiles: ResultTile[];
  endReason: EndReason | null;
  review: Retry;
  onPlayAgain: () => void;
  onNewRush: () => void;
}

/** S10: score, clickable ✓/✕ grid (retry outcomes included), Retry panel, Play Again / New Rush. */
export default function RunSummary({ mode, score, tiles, endReason, review, onPlayAgain, onNewRush }: Props) {
  const t = useTranslations('puzzleRush');

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
        selected={review.selected}
        outcomes={review.outcomes}
        onSelect={review.open}
        puzzleLabel={(n, state) => t(`summary.tile.${state}`, { n })}
        helpTitle={t('retry.helpMark')}
      />

      <RetryPanel review={review} />

      <div className={styles.buttonRow}>
        <button type="button" className={styles.cta} onClick={onPlayAgain}>{t('results.playAgain')}</button>
        <button type="button" className={styles.ghostButton} onClick={onNewRush}>{t('results.newRush')}</button>
      </div>
    </div>
  );
}
