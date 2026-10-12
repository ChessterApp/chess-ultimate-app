'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { EndReason, RushMode, RushResults } from '@/lib/puzzle-rush/types';
import { formatClock } from './RunTiles';
import styles from './PuzzleRush.module.css';

/** Below this a non-PB run gets the red "Tough One" header (chess.com S9). */
export const LOW_SCORE = 10;

export type ResultTone = 'pb' | 'great' | 'tough';

export function resultTone(score: number, isPb: boolean): ResultTone {
  if (isPb) return 'pb';
  return score >= LOW_SCORE ? 'great' : 'tough';
}

interface Props {
  mode: RushMode;
  score: number;
  results: RushResults | null;
  endReason: EndReason | null;
  isPb: boolean;
  isGuest: boolean;
  onPlayAgain: () => void;
  onNewRush: () => void;
  onClose: () => void;
  signInHref: string;
}

/** S9: end-of-run card. Enter = Play Again, Esc = close (§1 Keyboard). */
export default function ResultsModal({
  mode, score, results, endReason, isPb, isGuest, onPlayAgain, onNewRush, onClose, signInHref,
}: Props) {
  const t = useTranslations('puzzleRush');
  const [copied, setCopied] = useState(false);
  const tone = resultTone(score, isPb);

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
    const url = `${window.location.origin}/puzzle/rush`;
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

  const rank = (n: number | null | undefined) => (n ? `#${n}` : '—');
  const ranks = results?.global_rank;
  const avg = results?.avg_ms_per_puzzle;

  return (
    <div className={styles.scrim} onClick={onClose}>
      <div
        className={styles.modal}
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

        <div className={styles.ranks}>
          <div className={styles.rankCell}>
            <div className={styles.rankLabel}>{t('results.personal')}</div>
            <div className={styles.rankValue}>{rank(results?.personal_rank)}</div>
          </div>
          <div className={styles.rankCell}>
            <div className={styles.rankLabel}>{t('results.today')}</div>
            <div className={styles.rankValue}>{rank(ranks?.daily)}</div>
          </div>
          <div className={styles.rankCell}>
            <div className={styles.rankLabel}>{t('results.allTime')}</div>
            <div className={styles.rankValue}>{rank(ranks?.all)}</div>
          </div>
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

        <div className={styles.resultActions}>
          <div className={styles.buttonRow}>
            <button type="button" className={styles.cta} onClick={onPlayAgain} autoFocus>
              {t('results.playAgain')}
            </button>
            <button type="button" className={styles.ghostButton} onClick={onNewRush}>
              {t('results.newRush')}
            </button>
          </div>
          <div className={styles.shareRow}>
            <button type="button" className={styles.linkButton} onClick={share}>
              {copied ? t('results.copied') : t('results.share')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
