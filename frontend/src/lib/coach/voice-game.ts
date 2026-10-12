/**
 * The game against the coach and the famous games, as the voice coach hears about them.
 *
 * The game itself is Hermes' (src/tools/game_play.py): start_game / make_game_move, called by the
 * text coach and the voice coach alike, answer with a `game` board action carrying the game's state,
 * which the page shows the way it shows a game started by its «Сыграть с тренером» button
 * (2026-10-12; on 2026-10-10 voice "played" by talking and wrote a FEN of its own). What stays here
 * is what the browser tells the Live model itself: the [Game] line after a move made on the board,
 * and the verified score of a famous game the student named.
 */
import type { BoardAction } from '@/types/coach';
import type { GameStateView } from '@/lib/coach/boards-api';

/** The game's state carried by a `game` board action, if the actions have one (the last). */
export function gameFromActions(actions: unknown): GameStateView | null {
  if (!Array.isArray(actions)) return null;
  let found: GameStateView | null = null;
  for (const a of actions as BoardAction[]) {
    if (a && a.type === 'game' && a.game && typeof a.game.fen === 'string') found = a.game;
  }
  return found;
}

function sideToMove(view: GameStateView): string {
  if (view.status !== 'playing') return 'the game is over';
  return view.student_to_move ? "the student's move" : "the engine's move";
}

/** The [Game] line the voice coach gets when the game's position changed on the board. */
export function gameNote(view: GameStateView): string {
  const parts: string[] = [];
  if (view.student) {
    const v = view.student.verdict && view.student.verdict !== 'ok' ? ` (${view.student.verdict})` : '';
    parts.push(`the student played ${view.student.san}${v}`);
  }
  if (view.engine) parts.push(`the engine answered ${view.engine.san} — say it aloud in words`);
  const moves = parts.length ? `${parts.join('; ')}. ` : '';
  const end = view.status === 'playing'
    ? `Now it is ${sideToMove(view)}.`
    : `The game is over: ${view.result ?? ''} ${view.termination ?? ''} — say the result.`.replace(/\s+/g, ' ');
  return (
    `[Game] A game against the student is on the board (the student plays ${view.student_color}, ` +
    `engine ${view.engine_elo}). ${moves}${end} Position (FEN): ${view.fen}. ` +
    "The student's moves go through make_game_move; never change the position with board_control."
  );
}

/** Words that may name a famous game: Hermes decides which, if any (famous_game). */
export function mentionsAGame(text: string): boolean {
  return /парти|game|ойын/i.test(text || '');
}

/** The line the voice coach gets with a famous game's verified score (famous_game). */
export function famousNote(result: { found?: boolean; facts?: string } | null): string | null {
  if (!result?.found || !result.facts) return null;
  return `[Game record] ${result.facts}`.replace(/\s+/g, ' ').trim();
}

/** Words that may ask for a game («давай сыграем», «спорим, я тебя обыграю», "let's play"): Hermes decides. */
export function mayAskForAGame(text: string): boolean {
  return /сыгра|поигра|партейк|обыгра|спорим|play|ойна/i.test(text || '');
}

/** The line after the site started the game for the student's words (start_game with `said`). */
export function gameStartNote(result: { ok?: boolean; note?: string; student_color?: string } | null): string | null {
  if (!result?.ok) return null;
  return (
    `[Game] The student asked to play and the game has started on the board (the system started it; ` +
    `the student plays ${result.student_color ?? 'white'}). ${result.note ?? ''} Never play or invent a move ` +
    'yourself: the student\'s moves go through make_game_move, the engine makes yours.'
  ).replace(/\s+/g, ' ').trim();
}

/** The line after the site played the move the student said (make_game_move with `said`). */
export function gameMoveNote(
  result: { ok?: boolean; student_move?: string; verdict?: string; engine_reply?: string | null; game_over?: boolean; result?: string } | null,
): string | null {
  if (!result?.ok || !result.student_move) return null;
  const verdict = result.verdict && result.verdict !== 'ok' ? ` (${result.verdict})` : '';
  const reply = result.engine_reply ? `; the engine answered ${result.engine_reply} — say it aloud in words` : '';
  const over = result.game_over ? ` The game is over: ${result.result ?? ''} — say the result.` : '';
  return (
    `[Game] The student's move ${result.student_move}${verdict} was played on the board (the system played it)` +
    `${reply}.${over} Do not call make_game_move for this move.`
  ).replace(/\s+/g, ' ').trim();
}
