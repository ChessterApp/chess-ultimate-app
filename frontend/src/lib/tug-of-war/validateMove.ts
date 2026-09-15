/**
 * Move validation for Tug of War, extracted from TugBoard so it can be unit
 * tested without mounting chessground.
 *
 * The solving team plays the moves at even indices of `puzzle.moves`; odd
 * indices are the opponent's auto-played replies. Validation is *outcome*-based
 * on the finishing move, not a literal string match: beginner K+Q / K+R vs K
 * positions almost always have several legal checkmates, so any legal move that
 * delivers checkmate is accepted and immediately solves the puzzle — on ANY
 * ply, not just the scripted last one. Delivering mate ends the game, so a
 * faster mate than the scripted line (e.g. a mate-in-1 inside a position the
 * data mislabels as mate-in-2) is a win, not a wrong answer. Non-mating moves
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
  const matchesScript = !!expected && played === expected.slice(0, 4);

  // Any legal move that delivers immediate checkmate is accepted and wins the
  // puzzle outright — on any ply, regardless of the scripted line. This rescues
  // positions the data mislabels as longer-than-they-are (a mate-in-1 shortcut
  // inside a "mate-in-2").
  let acceptedAsAltMate = false;
  if (!matchesScript) {
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

  // An accepted alt-mate ends the game immediately. A scripted move solves when
  // it is the last ply or itself delivers mate.
  let solved = acceptedAsAltMate || idx + 1 >= moves.length;
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
