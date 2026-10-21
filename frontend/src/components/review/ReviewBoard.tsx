'use client';

import { useCallback, useState } from 'react';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import ClassificationIcon from './ClassificationIcon';
import type { Classification } from './ClassificationIcon';

/** 180ms piece slide — locked to the Chess.com reference (teardown Part B). */
export const PIECE_ANIMATION_MS = 180;

export type Orientation = 'white' | 'black';

export interface SquarePos {
  /** 0 = a-file column when white, flips for black. */
  col: number;
  /** 0 = top row. */
  row: number;
}

/**
 * Map an algebraic square (e.g. "e4") to a board grid column/row for the given
 * orientation. White: a-file at the left, rank 8 at the top. Black flips both.
 */
export function squareToColRow(square: string, orientation: Orientation): SquarePos {
  const file = square.charCodeAt(0) - 97; // a → 0 … h → 7
  const rank = parseInt(square[1], 10) - 1; // 1 → 0 … 8 → 7
  if (orientation === 'white') {
    return { col: file, row: 7 - rank };
  }
  return { col: 7 - file, row: rank };
}

/** Top/left percentage box for a full-square overlay (a tint). */
export function squareTintStyle(
  square: string,
  orientation: Orientation,
): { left: string; top: string; width: string; height: string } {
  const { col, row } = squareToColRow(square, orientation);
  return {
    left: `${col * 12.5}%`,
    top: `${row * 12.5}%`,
    width: '12.5%',
    height: '12.5%',
  };
}

/**
 * Top-right "tuck" box for the on-board classification badge: a badge ~`badgePct`
 * of a square, centred on the destination square's top-right corner so it
 * half-overlaps the edge.
 */
export function badgeTuckStyle(
  square: string,
  orientation: Orientation,
  badgePct = 5.5,
): { left: string; top: string; width: string; height: string } {
  const { col, row } = squareToColRow(square, orientation);
  // Top-right corner of the square in board %, then pull back by half the badge.
  const cornerLeft = (col + 1) * 12.5;
  const cornerTop = row * 12.5;
  return {
    left: `${cornerLeft - badgePct / 2}%`,
    top: `${cornerTop - badgePct / 2}%`,
    width: `${badgePct}%`,
    height: `${badgePct}%`,
  };
}

export interface ReviewBoardMove {
  uci: string;
  classification: Classification;
  best?: { uci: string } | null;
}

export interface ReviewBoardProps {
  fen: string;
  orientation?: Orientation;
  /** The move landed on (its uci gives from/to; classification drives overlays). */
  move?: ReviewBoardMove | null;
  /** Re-key the badge to retrigger the pop-in animation on ply change. */
  animationKey?: number | string;
  /** Reports the board's real rendered pixel size (used to size the eval bar). */
  onBoardSize?: (px: number) => void;
  /** Arrows from the coach's Explain text; they replace the best-move arrow. */
  coachArrows?: Array<{ from: string; to: string; brush: string }>;
  /** Squares the coach's Explain text highlights. */
  coachSquares?: string[];
}

function uciSquares(uci?: string): [string, string] | null {
  if (!uci || uci.length < 4) return null;
  return [uci.slice(0, 2), uci.slice(2, 4)];
}

/**
 * Interactive review board. Follows the store's current ply (the caller passes
 * that ply's `fen` + `move`) and paints three overlay layers over the reused
 * ChessgroundBoard, all orientation-aware:
 *   (a) from/to square tints = the move's classification colour @ 0.5 opacity,
 *   (b) a best-move arrow when the played move ≠ engine best,
 *   (c) a tuck-right classification badge on the destination square, popping in.
 * Piece movement is locked to 180ms.
 */
export default function ReviewBoard({
  fen,
  orientation = 'white',
  move,
  animationKey,
  onBoardSize,
  coachArrows,
  coachSquares,
}: ReviewBoardProps) {
  // The board's real rendered pixel size, measured by ChessgroundBoard. Once
  // known we drive the box height from it so the box is exactly square in every
  // browser — Safari mis-derives an aspect-ratio height on shrunk flex items,
  // which left dead space below the board and stretched the eval bar too tall.
  const [boardPx, setBoardPx] = useState<number | null>(null);
  const handleSize = useCallback(
    (px: number) => {
      setBoardPx(px);
      onBoardSize?.(px);
    },
    [onBoardSize],
  );

  const squares = uciSquares(move?.uci);
  const bestSquares = uciSquares(move?.best?.uci);
  const showBestArrow =
    !!bestSquares && !!move?.best && move.best.uci !== move.uci;

  const tintColor = move ? `var(--color-classification-${move.classification})` : undefined;

  return (
    <div
      data-testid="review-board"
      style={{
        position: 'relative',
        width: '100%',
        maxWidth: 520,
        // Height comes from the measured board px once known (square guaranteed);
        // aspectRatio is only a first-paint fallback before the measurement lands.
        ...(boardPx != null ? { height: boardPx } : { aspectRatio: '1 / 1' }),
        borderRadius: 16,
        boxShadow: 'var(--review-board-shadow)',
      }}
    >
      <ChessgroundBoard
        fen={fen}
        orientation={orientation}
        onSizeChange={handleSize}
        movable={false}
        viewOnly
        animationDuration={PIECE_ANIMATION_MS}
        lastMove={squares as never}
        arrows={
          coachArrows?.length
            ? coachArrows.map((a) => ({ from: a.from as never, to: a.to as never, brush: a.brush }))
            : showBestArrow && bestSquares
              ? [{ from: bestSquares[0] as never, to: bestSquares[1] as never, brush: 'blue' }]
              : []
        }
        highlightSquares={(coachSquares ?? []) as never}
      />

      {/* Overlay layers — do not intercept pointer events. */}
      <div
        data-testid="review-board-overlay"
        style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
      >
        {squares && tintColor &&
          squares.map((sq, i) => (
            <div
              key={`tint-${i}-${sq}`}
              data-testid="square-tint"
              data-square={sq}
              className="review-square-tint"
              style={{
                position: 'absolute',
                ...squareTintStyle(sq, orientation),
                background: tintColor,
              }}
            />
          ))}

        {squares && move && (
          <div
            key={`badge-${animationKey ?? move.uci}`}
            data-testid="board-badge"
            data-square={squares[1]}
            className="review-board-badge"
            style={{ position: 'absolute', ...badgeTuckStyle(squares[1], orientation) }}
          >
            <ClassificationIcon type={move.classification} />
          </div>
        )}
      </div>
    </div>
  );
}
