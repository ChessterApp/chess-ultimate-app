/**
 * Board geometry helpers shared by chess overlays (hint, target star, arrows).
 *
 * A chessboard rendered from Black's perspective is rotated 180° relative to
 * White's, so BOTH the file and rank axes must flip when computing the on-screen
 * position of a square. Overlays that ignore orientation land on the mirrored
 * square (e.g. a hint for g4 shows up on b5 on a black-oriented board).
 */

export type BoardOrientation = 'white' | 'black';

export interface SquarePercent {
  /** Left offset of the square's top-left corner, as a percentage (0–87.5). */
  left: number;
  /** Top offset of the square's top-left corner, as a percentage (0–87.5). */
  top: number;
}

/**
 * Convert an algebraic square (e.g. "g4") to the top-left corner position of its
 * cell on an 8×8 board, in percent, accounting for board orientation.
 */
export function squareToPercent(square: string, orientation: BoardOrientation): SquarePercent {
  const fileIdx = square.charCodeAt(0) - 'a'.charCodeAt(0); // a=0 … h=7
  const rankIdx = parseInt(square[1], 10) - 1; // rank1=0 … rank8=7

  const x = orientation === 'white' ? fileIdx : 7 - fileIdx;
  const y = orientation === 'white' ? 7 - rankIdx : rankIdx;

  return { left: x * 12.5, top: y * 12.5 };
}
