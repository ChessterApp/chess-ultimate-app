/**
 * Move validation for Tug of War, extracted from TugBoard so it can be unit
 * tested without mounting chessground.
 *
 * The solving team plays the moves at even indices of `puzzle.moves`; odd
 * indices are the opponent's auto-played replies. Validation is *outcome*-based
 * on the finishing move, not a literal string match: beginner K+Q / K+R vs K
 * positions almost always have several legal checkmates, so any legal move that
 * delivers mate on the final step is accepted. Earlier (non-terminal) moves
 * must still follow the script so the scripted opponent reply lines up.
 */
import { Chess } from 'chess.js';

export interface MoveDecision {
  /** Whether the played move should be accepted (scripted or an alt mate). */
  accepted: boolean;
  /** Promotion piece to apply when accepted (undefined = no promotion). */
  promotion?: string;
  /** True when this accepted move completes the puzzle (mate or line end). */
  solved: boolean;
}

/**
 * Decide the fate of a team move played from `orig` to `dest` in position
 * `fen`, where `idx` is the index into `moves` of the expected team move.
 */
export function evaluateTeamMove(
  fen: string,
  moves: string[],
  idx: number,
  orig: string,
  dest: string,
): MoveDecision {
  const expected = moves[idx];
  const played = `${orig}${dest}`;
  const isTerminal = idx === moves.length - 1;
  const matchesScript = !!expected && played === expected.slice(0, 4);

  // Any legal move that mates on the finishing step is accepted.
  let acceptedAsAltMate = false;
  if (!matchesScript && isTerminal) {
    try {
      const probe = new Chess(fen);
      const res = probe.move({ from: orig, to: dest, promotion: 'q' });
      if (res && probe.isCheckmate()) acceptedAsAltMate = true;
    } catch {
      acceptedAsAltMate = false;
    }
  }

  if (!matchesScript && !acceptedAsAltMate) {
    return { accepted: false, solved: false };
  }

  const promotion = matchesScript
    ? expected.length > 4
      ? expected[4]
      : undefined
    : 'q';

  let solved = idx + 1 >= moves.length;
  if (!solved) {
    try {
      const probe = new Chess(fen);
      probe.move({ from: orig, to: dest, promotion });
      solved = probe.isCheckmate();
    } catch {
      solved = false;
    }
  }

  return { accepted: true, promotion, solved };
}
