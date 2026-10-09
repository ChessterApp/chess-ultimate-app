import { Chess } from 'chess.js';

/**
 * Helpers for the "manual move entry" board tab in the Add-Game modal.
 * Turns a list of SAN moves into a PGN movetext string and auto-detects the
 * game result when a position is terminal.
 */

/**
 * Build a PGN movetext string from a list of SAN moves, in the same shape the
 * main-board builder (`buildMyGamesPgn` in database/page.tsx) produces:
 * move numbers before each White move and a trailing result token.
 *
 * @param sanMoves ordered SAN moves (White, Black, White, …)
 * @param result   trailing result token (defaults to `*` for an unfinished game)
 */
export function buildPgnFromSanMoves(sanMoves: string[], result = '*'): string {
  if (sanMoves.length === 0) return '';
  let pgn = '';
  for (let i = 0; i < sanMoves.length; i++) {
    if (i % 2 === 0) {
      pgn += `${Math.floor(i / 2) + 1}. `;
    }
    pgn += `${sanMoves[i]} `;
  }
  pgn += result;
  return pgn.trim();
}

/**
 * Detect the game result for a terminal position.
 * - Checkmate → the side NOT to move delivered mate, so `1-0` (Black mated) or
 *   `0-1` (White mated).
 * - Stalemate / insufficient material / any other draw → `1/2-1/2`.
 * - Non-terminal position → `null` (caller keeps `*`).
 */
export function detectResult(chess: Chess): string | null {
  if (chess.isCheckmate()) {
    return chess.turn() === 'w' ? '0-1' : '1-0';
  }
  if (chess.isStalemate() || chess.isInsufficientMaterial() || chess.isDraw()) {
    return '1/2-1/2';
  }
  return null;
}
