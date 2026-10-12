'use client';

import dynamic from 'next/dynamic';
import type { Key } from 'chessground/types';
import type { PromotionRole } from '@/lib/chess/promotion';
import type { CountdownStep } from '@/hooks/usePuzzleRush';
import styles from './PuzzleRush.module.css';

// Same board component /puzzle renders (via AiChessboard); client-only.
const ChessgroundBoard = dynamic(() => import('@/components/chess/ChessgroundBoard'), { ssr: false });

/** Top-right corner of `square` as percentages of the board, for the ✓/✕ badge. */
export function badgePosition(square: Key, orientation: 'white' | 'black') {
  const file = square.charCodeAt(0) - 97;
  const rank = Number(square[1]) - 1;
  const col = orientation === 'white' ? file : 7 - file;
  const row = orientation === 'white' ? 7 - rank : rank;
  return { left: `${((col + 1) / 8) * 100}%`, top: `${(row / 8) * 100}%` };
}

interface Props {
  fen: string;
  orientation: 'white' | 'black';
  boardKey: number;
  lastMove: [Key, Key] | null;
  movable: boolean;
  covered?: boolean;
  badge?: { square: Key; kind: 'ok' | 'fail' } | null;
  countdown?: CountdownStep;
  goLabel?: string;
  /** The next puzzle is still downloading (pack top-up): hold the board. */
  waiting?: boolean;
  onMove?: (from: Key, to: Key, promotion?: PromotionRole) => void;
  /** Retry-mode hints: green arrow (level 2) / circle on the piece (level 1). */
  hintMove?: [Key, Key] | null;
  hintSquare?: Key | null;
}

export default function RushBoard({
  fen, orientation, boardKey, lastMove, movable, covered = false, badge = null, countdown = null, goLabel = 'Go!',
  waiting = false, onMove, hintMove = null, hintSquare = null,
}: Props) {
  return (
    <div className={styles.boardFrame} data-testid="rush-board">
      <ChessgroundBoard
        key={boardKey}
        fen={fen}
        orientation={orientation}
        lastMove={lastMove}
        movable={movable}
        onMove={onMove}
        hintMove={hintMove}
        hintSquare={hintSquare}
        animationDuration={200}
      />
      <div className={`${styles.cover} ${covered || waiting ? styles.coverOn : ''}`} aria-hidden="true" />
      {waiting && <span className={styles.spinner} role="status" data-testid="rush-waiting" />}
      {badge && (
        <span
          className={`${styles.badge} ${badge.kind === 'ok' ? styles.badgeOk : styles.badgeFail}`}
          style={badgePosition(badge.square, orientation)}
          data-testid={`badge-${badge.kind}`}
          aria-hidden="true"
        >
          {badge.kind === 'ok' ? '✓' : '✕'}
        </span>
      )}
      {countdown !== null && (
        <div className={styles.countdown} aria-live="assertive">
          <span key={String(countdown)} className={countdown === 'go' ? styles.countdownGo : styles.countdownNum}>
            {countdown === 'go' ? goLabel : countdown}
          </span>
        </div>
      )}
    </div>
  );
}
