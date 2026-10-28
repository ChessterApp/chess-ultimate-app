import { Chess } from 'chess.js';
import type { BoardRecord, GameStateView } from './boards-api';

/** The side lines kept in a stored game state, the way Hermes's game payload gives them (at_ply, moves). */
function storedVariations(raw: unknown): NonNullable<GameStateView['variations']> {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((v) => {
    if (!v || typeof v !== 'object') return [];
    const { at_ply: at, moves } = v as { at_ply?: unknown; moves?: unknown };
    if (typeof at !== 'number' || !Number.isInteger(at) || at < 0) return [];
    if (!Array.isArray(moves) || !moves.every((m) => typeof m === 'string')) return [];
    return [{ at_ply: at, moves: moves as string[] }];
  });
}

function sideToMoveInCheck(fen: string): boolean {
  try {
    return new Chess(fen).inCheck();
  } catch {
    return false;
  }
}

/** A live game restored from its board record (no last move / verdict known). */
export function gameViewFromBoard(b: BoardRecord): GameStateView | null {
  const gs = (b.game_state ?? null) as Record<string, unknown> | null;
  if (b.kind !== 'game' || !gs || gs.status !== 'playing') return null;
  const moves = Array.isArray(gs.moves) ? (gs.moves as string[]) : [];
  const studentColor = gs.student_color === 'black' ? 'black' : 'white';
  const whiteToMove = moves.length % 2 === 0;
  return {
    board_id: b.id,
    student_color: studentColor,
    engine_elo: typeof gs.engine_elo === 'number' ? gs.engine_elo : 1500,
    comment_mode: (gs.comment_mode as GameStateView['comment_mode']) ?? 'mistakes',
    status: 'playing',
    result: null,
    termination: null,
    winner: null,
    fen: b.fen,
    pgn: b.pgn,
    ply: moves.length,
    moves,
    // A reload lost the kept side lines and the check notice until the next move (seam audit 28.10): both are
    // in the stored record — the lines in game_state, the check in the position itself.
    variations: storedVariations(gs.variations),
    student_to_move: whiteToMove === (studentColor === 'white'),
    in_check: sideToMoveInCheck(b.fen),
    student: null,
    engine: null,
    comment_wanted: false,
  };
}
