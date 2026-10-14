import { Chess } from 'chess.js';

/** The placement + side to move of a FEN: what a move changes for certain. */
function positionKey(fen: string): string {
  return fen.split(' ').slice(0, 2).join(' ');
}

/**
 * The SAN moves between consecutive positions of the study board's history
 * (useCoachBoard keeps positions, not moves). Stops at the first pair no legal
 * move connects (a set position, a puzzle start).
 */
export function sanMoves(fens: string[]): string[] {
  const moves: string[] = [];
  for (let i = 0; i + 1 < fens.length; i++) {
    let san: string | null = null;
    try {
      const chess = new Chess(fens[i]);
      const target = positionKey(fens[i + 1]);
      for (const m of chess.moves({ verbose: true })) {
        if (positionKey(m.after) === target) {
          san = m.san;
          break;
        }
      }
    } catch {
      san = null;
    }
    if (!san) break;
    moves.push(san);
  }
  return moves;
}
