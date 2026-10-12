'use client';

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import type { ResultTile } from '@/lib/puzzle-rush/runReducer';
import type { RetryOutcomes } from '@/lib/puzzle-rush/retryReducer';
import type { EndReason, ModeBests, RushMode, RushResults } from '@/lib/puzzle-rush/types';
import { formatClock, ResultsGrid } from './RunTiles';
import styles from './PuzzleRush.module.css';

/** Below this a non-PB run gets the red "Tough One" header (chess.com S9). */
export const LOW_SCORE = 10;

export type ResultTone = 'pb' | 'great' | 'tough';

const TABS = ['summary', 'puzzles'] as const;
type Tab = (typeof TABS)[number];

export function resultTone(score: number, isPb: boolean): ResultTone {
  if (isPb) return 'pb';
  return score >= LOW_SCORE ? 'great' : 'tough';
}

interface Props {
  mode: RushMode;
  score: number;
  /** The run's ✓/✕ tiles, for the Puzzles tab. */
  tiles: ResultTile[];
  /** Retry-mode outcomes so far (✕ tiles solved on retry render amber). */
  outcomes?: RetryOutcomes;
  results: RushResults | null;
  endReason: EndReason | null;
  isPb: boolean;
  isGuest: boolean;
  /** Guests: on-device bests for this mode, already including this run. */
  guestBests?: ModeBests | null;
  /** Signed-in: `/runs/finish` is in flight, ranks fill in when it returns. */
  ranksPending?: boolean;
  onPlayAgain: () => void;
  onNewRush: () => void;
  onClose: () => void;
  /** Leave the modal for puzzle `index` (a tile, or the first miss via Retry mistakes). */
  onOpenPuzzle: (index: number) => void;
  signInHref: string;
}

/**
 * S9: end-of-run card, rendered from local state the moment the run ends.
 * Signed-in: ranks (and the PB title) animate in when `/runs/finish` returns.
 * Guests: the tiles show on-device bests, never ranks. Enter = Play Again,
 * Esc = close (§1 Keyboard). Summary | Puzzles tabs; the Puzzles tab's ✓/✕
 * tiles (and Retry mistakes) hand off to `onOpenPuzzle`.
 */
export default function ResultsModal({
  mode, score, tiles, outcomes, results, endReason, isPb, isGuest, guestBests = null, ranksPending = false,
  onPlayAgain, onNewRush, onClose, onOpenPuzzle, signInHref,
}: Props) {
  const t = useTranslations('puzzleRush');
  const [copied, setCopied] = useState(false);
  const [tab, setTab] = useState<Tab>('summary');
  const tabRefs = useRef<Partial<Record<Tab, HTMLButtonElement | null>>>({});
  const misses = tiles.filter((tile) => !tile.solved);
  const tone = resultTone(score, isPb);
  const playAgainRef = useRef<HTMLButtonElement>(null);

  // Focus Play Again after the modal's first paint, not via autoFocus: focusing
  // during the commit forces a full layout in the run-ending frame (~40 ms).
  useEffect(() => {
    const id = requestAnimationFrame(() => playAgainRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'Enter' && !(e.target instanceof HTMLButtonElement || e.target instanceof HTMLAnchorElement)) {
        onPlayAgain();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, onPlayAgain]);

  const share = async () => {
    const text = t('results.shareText', { score, mode: t(`modes.${mode}.short`) });
    const url = `${window.location.origin}/games/puzzlerush`;
    try {
      if (navigator.share) {
        await navigator.share({ text, url });
        return;
      }
      await navigator.clipboard.writeText(`${text} ${url}`);
      setCopied(true);
    } catch {
      // Share sheet dismissed / clipboard blocked — nothing to do.
    }
  };

  // ←/→ (and Home/End) move between tabs, focus follows selection.
  const onTabKey = (e: ReactKeyboardEvent) => {
    const i = TABS.indexOf(tab);
    const next = {
      ArrowRight: TABS[(i + 1) % TABS.length],
      ArrowLeft: TABS[(i - 1 + TABS.length) % TABS.length],
      Home: TABS[0],
      End: TABS[TABS.length - 1],
    }[e.key];
    if (!next) return;
    e.preventDefault();
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  const rank = (n: number | null | undefined) => (n ? `#${n}` : ranksPending ? '…' : '—');
  const best = (n: number | null | undefined) => (n === null || n === undefined ? '—' : String(n));
  const ranks = results?.global_rank;
  const avg = results?.avg_ms_per_puzzle;
  const cells = isGuest
    ? [
      ['personal', best(guestBests?.top_score)],
      ['today', best(guestBests?.best_today)],
      ['allTime', best(guestBests?.top_score)],
    ]
    : [
      ['personal', rank(results?.personal_rank)],
      ['today', rank(ranks?.daily)],
      ['allTime', rank(ranks?.all)],
    ];

  return (
    <div className={`${styles.scrim} ${styles.sheetScrim}`} onClick={onClose}>
      <div
        className={`${styles.modal} ${styles.sheet}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="rush-result-title"
        onClick={(e) => e.stopPropagation()}
        data-testid="rush-results"
        data-tone={tone}
      >
        <div className={`${styles.resultHead} ${tone === 'tough' ? styles.resultHeadLow : styles.resultHeadPb}`}>
          <button type="button" className={styles.closeX} onClick={onClose} aria-label={t('results.close')}>✕</button>
          <h2 id="rush-result-title" className={styles.resultTitle}>{t(`results.${tone}`)}</h2>
          {endReason && <p className={styles.resultReason}>{t(`results.end.${endReason}`)} · {t(`modes.${mode}.title`)}</p>}
          <div className={styles.resultScore}>
            <span className={styles.resultScoreNum}>{score}</span>
            <span className={styles.resultScoreLabel}>{t('run.solved')}</span>
          </div>
        </div>

        <div className={`${styles.tabs} ${styles.resultTabs}`} role="tablist" onKeyDown={onTabKey}>
          {TABS.map((k) => (
            <button
              key={k}
              ref={(el) => { tabRefs.current[k] = el; }}
              type="button"
              role="tab"
              id={`rush-result-tab-${k}`}
              aria-selected={tab === k}
              aria-controls={`rush-result-panel-${k}`}
              tabIndex={tab === k ? 0 : -1}
              className={`${styles.tab} ${tab === k ? styles.tabActive : ''}`}
              onClick={() => setTab(k)}
            >
              {t(k === 'summary' ? 'results.tabSummary' : 'results.tabPuzzles')}
              {k === 'puzzles' && misses.length > 0 && (
                <span className={`${styles.tag} ${styles.tagFail} ${styles.tabBadge}`} data-testid="rush-miss-badge">
                  {t('results.missBadge', { n: misses.length })}
                </span>
              )}
            </button>
          ))}
        </div>

        <div
          role="tabpanel"
          id="rush-result-panel-summary"
          aria-labelledby="rush-result-tab-summary"
          hidden={tab !== 'summary'}
        >
          <div className={styles.ranks} data-testid="rush-ranks">
            {cells.map(([key, value]) => (
              <div key={key} className={styles.rankCell}>
                <div className={styles.rankLabel}>{t(`results.${key}`)}</div>
                {/* Re-keyed so a rank arriving from /runs/finish rises in. */}
                <div key={value} className={`${styles.rankValue} ${value === '…' ? styles.rankPending : styles.rankValueIn}`}>
                  {value}
                </div>
              </div>
            ))}
          </div>
          {isGuest && (
            <p className={styles.guestRanks}>
              <a className={styles.linkButton} href={signInHref}>{t('guest.signIn')}</a>
              {' — '}
              {t('results.guestRanks')}
            </p>
          )}

          <ul className={styles.stats}>
            <li className={styles.stat}>
              <span>{t('results.longestStreak')}</span>
              <b>{results?.longest_streak ?? 0}</b>
            </li>
            <li className={styles.stat}>
              <span>{t('results.highestSolved')}</span>
              <b>{results?.highest_solved_rating ?? '—'}</b>
            </li>
            <li className={styles.stat}>
              <span>{t('results.avgTime')}</span>
              <b>{avg ? formatClock(avg, 'down') : '—'}</b>
            </li>
          </ul>
        </div>

        <div
          role="tabpanel"
          id="rush-result-panel-puzzles"
          aria-labelledby="rush-result-tab-puzzles"
          hidden={tab !== 'puzzles'}
          className={styles.resultPuzzles}
        >
          {tiles.length > 0 && <p className={styles.summaryHint}>{t('summary.hint')}</p>}
          <ResultsGrid
            tiles={tiles}
            summary
            outcomes={outcomes}
            onSelect={onOpenPuzzle}
            puzzleLabel={(n, state) => t(`summary.tile.${state}`, { n })}
            helpTitle={t('retry.helpMark')}
            revealedTitle={t('retry.revealedMark')}
          />
        </div>

        <div className={styles.resultActions}>
          <div className={`${styles.buttonRow} ${misses.length > 0 ? styles.buttonRowStack : ''}`}>
            <button type="button" className={styles.cta} onClick={onPlayAgain} ref={playAgainRef}>
              {t('results.playAgain')}
            </button>
            {misses.length > 0 ? (
              <button type="button" className={`${styles.ghostButton} ${styles.retryButton}`} onClick={() => onOpenPuzzle(misses[0].index)}>
                {t('results.retryMistakes', { n: misses.length })}
              </button>
            ) : (
              <button type="button" className={styles.ghostButton} onClick={onNewRush}>
                {t('results.newRush')}
              </button>
            )}
          </div>
          <div className={styles.shareRow}>
            {/* With Retry mistakes taking its slot, New Rush drops to the link row. */}
            {misses.length > 0 && (
              <>
                <button type="button" className={styles.linkButton} onClick={onNewRush}>
                  {t('results.newRush')}
                </button>
                <span className={styles.shareSep} aria-hidden="true">·</span>
              </>
            )}
            <button type="button" className={styles.linkButton} onClick={share}>
              {copied ? t('results.copied') : t('results.share')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
