import { Chess } from 'chess.js';

export interface EngineLineToken {
  /** Move number prefix, e.g. "12." or "12…" — only on White moves and the first Black move. */
  num?: string;
  san: string;
}

/**
 * Convert a UCI principal variation into numbered SAN tokens, capped at
 * `maxFullMoves` full moves (2 half-moves each). Stops at the first illegal
 * or malformed move; a bad FEN yields [].
 */
export function formatEngineLine(
  fen: string,
  pvUci: string[],
  maxFullMoves = 4,
): EngineLineToken[] {
  let chess: Chess;
  try {
    chess = new Chess(fen);
  } catch {
    return [];
  }

  const tokens: EngineLineToken[] = [];
  for (const uci of pvUci.slice(0, maxFullMoves * 2)) {
    if (!uci || uci.length < 4) break;
    const whiteToMove = chess.turn() === 'w';
    const moveNumber = chess.moveNumber();
    try {
      const move = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] });
      const num = whiteToMove ? `${moveNumber}.` : tokens.length === 0 ? `${moveNumber}…` : undefined;
      tokens.push(num ? { num, san: move.san } : { san: move.san });
    } catch {
      break;
    }
  }
  return tokens;
}

export function engineLineToString(tokens: EngineLineToken[]): string {
  return tokens.map((t) => `${t.num ?? ''}${t.san}`).join(' ');
}
