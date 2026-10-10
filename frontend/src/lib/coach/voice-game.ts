/**
 * The game against the coach, by voice (2026-10-10).
 *
 * Voice had no game: on «спорим, я тебя надую» the Live coach "played" by talking — it said
 * «я пошёл e4» without putting anything on the board, and after 1.e4 d5 2.exd5 it wrote a FEN
 * of its own with both pawns gone (Alexander, chesster.io, 10.10). Now two tools the browser runs
 * itself start the same game as the «Сыграть с тренером» button and play the student's spoken
 * moves in it; the engine plays the coach's moves, the board shows them, and the voice coach
 * only says them aloud. Shared by the live-token route (declarations + prompt) and the voice
 * hook (the calls, the [Game] lines).
 */
import { Chess } from 'chess.js';
import { russianToSan } from '@/lib/russianNotation';
import type { GameStateView } from '@/lib/coach/boards-api';

export const VOICE_GAME_TOOL_NAMES = new Set(['start_game', 'make_game_move']);

/** The engine strengths the site offers (GamePanel's GAME_STRENGTHS). */
const STRENGTHS = [600, 800, 1000, 1200, 1500, 1800, 2000, 2200, 2500];

export const VOICE_GAME_TOOLS = [
  {
    name: 'start_game',
    description:
      "Start a game against the student on the site's board — the same game as its «Play the coach» " +
      "button. The engine plays the coach's moves at the chosen strength. The result says the student's " +
      "colour, whose move it is and, when the student plays Black, the engine's first move.",
    parameters: {
      type: 'object',
      properties: {
        color: { type: 'string', enum: ['white', 'black', 'random'], description: "The student's colour (default white)." },
        elo: { type: 'integer', description: 'Engine strength, 600–2500 (default 1200).' },
      },
    },
  },
  {
    name: 'make_game_move',
    description:
      "Play the student's move in the game on the board. The result gives the engine's reply (say it " +
      'aloud), the verdict on the student\'s move and whether the game is over.',
    parameters: {
      type: 'object',
      properties: {
        move: { type: 'string', description: "The student's move in SAN: e4, Nf3, exd5, O-O, e8=Q." },
      },
      required: ['move'],
    },
  },
];

export const VOICE_GAME_GUIDANCE = `

## A game against the student (voice)
- When the student wants to play a game with you — in any words: «давай сыграем», «спорим, я тебя обыграю», "let's play" — call start_game. The site starts the same game as its «Play the coach» button and the engine plays your moves. Pass the colour and strength the student named (colour white|black|random; elo 600–2500, default 1200); ask nothing first.
- In a game you never choose or invent a move yourself and never say you made a move that the tools did not report. When the student says their move («е4», «конь эф три», «пешка бьёт на d5», "knight f3"), call make_game_move with it in SAN (e4, Nf3, exd5, O-O, e8=Q). Its result gives the engine's reply: say that move aloud in words («я отвечаю: конь эф шесть»), so the student can play without looking. If the move is illegal or it is not their turn, say so and ask for another.
- The student may move on the board instead: you then get a [Game] line with their move and the engine's reply — say the reply aloud the same way.
- During a game board_control may only draw arrows or highlight squares: the position belongs to the game. Give hints, never the best move unless the student asks for a hint; when a result marks their move a mistake or a blunder, you may say so in a word.
- Outside a game, to show moves on the board use board_control load_pgn with the moves; never write a FEN by hand.`;

export function nearestStrength(elo: unknown): number {
  const n = typeof elo === 'number' && Number.isFinite(elo) ? elo : 1200;
  return STRENGTHS.reduce((best, s) => (Math.abs(s - n) < Math.abs(best - n) ? s : best), STRENGTHS[0]);
}

export function gameColor(color: unknown): 'white' | 'black' | 'random' {
  return color === 'black' || color === 'random' ? color : 'white';
}

/**
 * The student's move, as the model wrote it, played from *fen*: SAN, Russian notation
 * («Кf3», «е:д5»), from-to («e2e4», «e2-e4») or castling with zeros. Returns its UCI and SAN,
 * or why it cannot be played with the legal moves.
 */
export function spokenMoveToUci(
  fen: string,
  move: unknown,
): { uci: string; san: string } | { error: string; legal: string[] } {
  const chess = new Chess(fen);
  const legal = chess.moves();
  const raw = typeof move === 'string' ? move.trim() : '';
  if (!raw) return { error: 'no move given', legal };
  const candidates = new Set<string>([raw, russianToSan(raw), raw.replace(/[+#!?]+$/, '')]);
  for (const text of candidates) {
    try {
      const m = new Chess(fen).move(text);
      if (m) return { uci: `${m.from}${m.to}${m.promotion ?? ''}`, san: m.san };
    } catch {
      /* not this spelling */
    }
  }
  const coord = /^([a-h][1-8])\s*[-x:]?\s*([a-h][1-8])\s*=?\s*([qrbnQRBN])?$/.exec(raw);
  if (coord) {
    try {
      const m = new Chess(fen).move({ from: coord[1], to: coord[2], promotion: coord[3]?.toLowerCase() });
      if (m) return { uci: `${m.from}${m.to}${m.promotion ?? ''}`, san: m.san };
    } catch {
      /* illegal */
    }
  }
  return { error: `${raw} is not a legal move here`, legal };
}

function sideToMove(view: GameStateView): string {
  if (view.status !== 'playing') return 'the game is over';
  return view.student_to_move ? "the student's move" : "the engine's move";
}

function over(view: GameStateView): Record<string, unknown> {
  if (view.status === 'playing') return {};
  return { game_over: true, result: view.result, termination: view.termination, winner: view.winner };
}

/** What the model hears after start_game. */
export function gameStartResult(view: GameStateView): Record<string, unknown> {
  return {
    ok: true,
    student_color: view.student_color,
    engine_elo: view.engine_elo,
    engine_first_move: view.engine?.san ?? null,
    to_move: sideToMove(view),
    fen: view.fen,
    note: view.engine?.san
      ? `The game is on. The engine opened with ${view.engine.san}: say it aloud, then wait for the student's move.`
      : 'The game is on and the student moves first: ask for their move.',
  };
}

/** What the model hears after make_game_move. */
export function gameMoveResult(view: GameStateView): Record<string, unknown> {
  const s = view.student;
  const bad = s && (s.verdict === 'mistake' || s.verdict === 'blunder');
  return {
    ok: true,
    student_move: s?.san ?? null,
    verdict: s?.verdict ?? null,
    ...(bad && s?.best ? { better_was: s.best } : {}),
    engine_reply: view.engine?.san ?? null,
    to_move: sideToMove(view),
    fen: view.fen,
    ...over(view),
    note: view.engine?.san
      ? `Say the engine's reply ${view.engine.san} aloud in words.`
      : view.status === 'playing' ? '' : 'The game is over: say the result.',
  };
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
    'Moves go only through make_game_move; never change the position with board_control.'
  );
}
