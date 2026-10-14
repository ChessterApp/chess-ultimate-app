/**
 * What a card's button does, as board actions / game cards for the existing
 * paths (onBoardActions, onOpenGame) — pure, so it is unit-tested apart from
 * the components.
 */

import { Chess } from 'chess.js';
import type { BoardAction, GameResult, SetPuzzleAction } from '@/types/coach';
import type { EngineLineSummary, PuzzleSummary, SummaryGame } from './tool-summary';

/** Plies of the best line drawn as arrows, and their brushes in order. */
const ARROW_BRUSHES = ['green', 'blue', 'yellow'];

const placement = (fen: string) => fen.trim().split(/\s+/)[0] ?? '';

/**
 * «Показать на доске»: the engine's best line as arrows from its position —
 * the first few plies, one brush each. The position is put up first when the
 * board shows another one.
 */
export function engineLineActions(summary: EngineLineSummary, boardFen: string): BoardAction[] {
  const arrows: Array<{ from: string; to: string; brush: string }> = [];
  try {
    const chess = new Chess(summary.fen);
    for (const san of summary.lines[0]?.san.slice(0, ARROW_BRUSHES.length) ?? []) {
      const move = chess.move(san);
      arrows.push({ from: move.from, to: move.to, brush: ARROW_BRUSHES[arrows.length] });
    }
  } catch {
    // A move the board does not accept ends the drawn line.
  }
  if (!arrows.length) return [];
  const actions: BoardAction[] = [];
  if (placement(summary.fen) !== placement(boardFen)) actions.push({ type: 'set_fen', fen: summary.fen });
  actions.push({ type: 'draw_arrows', arrows });
  return actions;
}

/** «Решить»: the turn's own set_puzzle action for this puzzle (it carries the solution), or null. */
export function puzzleAction(summary: PuzzleSummary, actions: BoardAction[] | undefined): SetPuzzleAction | null {
  for (const a of actions ?? []) {
    if (a.type !== 'set_puzzle') continue;
    if (a.puzzle_id ? String(a.puzzle_id) === summary.puzzle_id : placement(a.fen) === placement(summary.fen)) {
      return a;
    }
  }
  return null;
}

/**
 * The game card to open for a game of a game_list summary: the turn's
 * game_results card with that id (it may carry the PGN), else one built from
 * the summary (opened by its master-database id). No id → nothing to open.
 */
export function gameToOpen(game: SummaryGame, results: GameResult[] | undefined): GameResult | null {
  if (game.id === undefined) return null;
  const known = results?.find((r) => String(r.id) === String(game.id));
  if (known) return known;
  return {
    id: game.id,
    white_name: game.white,
    black_name: game.black,
    result: game.result,
    date: game.year ? String(game.year) : '',
    eco: game.eco ?? '',
    opening: '',
    event: '',
    white_elo: game.white_elo ?? null,
    black_elo: game.black_elo ?? null,
  };
}

/** A game_results card in the summary's game shape (one list renders both). */
export function resultToGame(r: GameResult): SummaryGame {
  const year = Number.parseInt(String(r.date ?? '').slice(0, 4), 10);
  return {
    id: r.id,
    white: r.white_name,
    black: r.black_name,
    result: r.result,
    eco: r.eco || undefined,
    year: Number.isFinite(year) ? year : undefined,
    white_elo: r.white_elo ?? undefined,
    black_elo: r.black_elo ?? undefined,
  };
}
