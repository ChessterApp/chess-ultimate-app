/**
 * Solution-line validation logic for multi-move puzzles.
 *
 * A solution line is an ordered array of UCI moves:
 *   [ userMove, opponentReply, userMove, opponentReply, ... ]
 * Even indices are the user's moves; odd indices are auto-played opponent replies.
 *
 * These helpers are intentionally pure (no React / chessground) so the
 * decision logic can be unit-tested in isolation.
 */

/** Return the promotion piece letter of a UCI move, if any (e.g. "e7e8q" -> "q"). */
export function promotionPiece(uci: string): string | undefined {
  return uci.length === 5 ? uci[4].toLowerCase() : undefined;
}

/**
 * Whether the user's from/to squares match an expected UCI move.
 * Promotions are compared on the from/to squares only — the promotion piece is
 * supplied by the expected line, not chosen by the user in the puzzle UI.
 */
export function movesMatch(orig: string, dest: string, expected: string): boolean {
  if (!expected) return false;
  return `${orig}${dest}` === expected.slice(0, 4);
}

export type LineEvaluation =
  | { kind: 'incorrect' }
  | {
      kind: 'solved';
      userMove: string;
      userPromotion?: string;
      nextIndex: number;
    }
  | {
      kind: 'progress';
      userMove: string;
      userPromotion?: string;
      opponentMove: string;
      opponentPromotion?: string;
      nextIndex: number;
      /** True when the opponent reply is the final move of the line (puzzle solved after it). */
      completesAfterReply: boolean;
    };

/**
 * Evaluate a user move against the solution line at the given index.
 *
 * - `incorrect`: move does not match the expected line move (index unchanged).
 * - `solved`: correct move that completes the line.
 * - `progress`: correct move with an opponent reply to auto-play; `nextIndex`
 *   points at the user's next move (after the opponent reply).
 */
export function evaluateLineMove(
  line: string[],
  index: number,
  orig: string,
  dest: string
): LineEvaluation {
  const expected = line[index];
  if (!movesMatch(orig, dest, expected)) {
    return { kind: 'incorrect' };
  }

  const userMove = expected;
  const userPromotion = promotionPiece(expected);
  const afterUser = index + 1;

  if (afterUser >= line.length) {
    return { kind: 'solved', userMove, userPromotion, nextIndex: afterUser };
  }

  const opponentMove = line[afterUser];
  const afterOpponent = afterUser + 1;
  return {
    kind: 'progress',
    userMove,
    userPromotion,
    opponentMove,
    opponentPromotion: promotionPiece(opponentMove),
    nextIndex: afterOpponent,
    completesAfterReply: afterOpponent >= line.length,
  };
}

/** Colour to move for a FEN, as chessground expects it. */
export function colorToMove(fen: string): 'white' | 'black' {
  return fen.split(' ')[1] === 'b' ? 'black' : 'white';
}
