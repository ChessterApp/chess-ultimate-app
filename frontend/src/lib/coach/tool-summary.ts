/**
 * Typed `summary` of a Hermes `tool_result` SSE frame (hermes/src/tool_summaries.py):
 * what the coach's rich cards are drawn from. Evaluations are from White's side
 * (`eval_cp` centipawns, `mate` moves, + = White); moves are SAN.
 *
 * `parseToolSummary` is the runtime guard: anything that is not one of the
 * known kinds in a usable shape gives null, so a newer server never breaks an
 * older client. `parseDailyPlan` guards the home screen's plan
 * (GET /api/coach/daily-plan, hermes/src/daily_plan.py) the same way.
 */

import { Chess } from 'chess.js';

export type Score = { eval_cp: number; mate?: undefined } | { mate: number; eval_cp?: undefined };

export type EngineLineSummary = {
  kind: 'engine_line';
  fen: string;
  depth?: number;
  lines: Array<{ san: string[] } & Score>;
} & Score;

export interface SummaryGame {
  id?: number | string;
  white: string;
  black: string;
  result: string;
  eco?: string;
  year?: number;
  white_elo?: number;
  black_elo?: number;
}

export interface GameListSummary {
  kind: 'game_list';
  games: SummaryGame[];
}

export interface OpeningSummary {
  kind: 'opening';
  name: string;
  eco: string;
  moves_san?: string[];
  /** Master-game results in percent, and how many games. */
  stats?: { white: number; draw: number; black: number; games: number };
}

export interface PuzzleSummary {
  kind: 'puzzle';
  puzzle_id: string;
  fen: string;
  rating?: number;
  themes?: string[];
}

export interface CriticalMomentsSummary {
  kind: 'critical_moments';
  moments: Array<{ ply: number; san: string; eval_before: number; eval_after: number; label: string }>;
}

/** One step of the «Моменты» review (hermes/src/review_moments.py). */
export interface ReviewMoment {
  /** 1-based ply of the move played. */
  ply: number;
  /** The position before the move; the side to move is the player who erred. */
  fen: string;
  /** The move played and the better one, SAN; `best_uci` is what a board move is checked against. */
  played: string;
  best: string;
  best_uci: string;
  /** Short slug: mate, fork, discovered_attack, pin, skewer, hanging_piece. */
  motif?: string;
  question: string;
  explanation: string;
  eval_before?: number;
  eval_after?: number;
}

export interface ReviewMomentsSummary {
  kind: 'review_moments';
  game: { white: string; black: string; result?: string; id?: number | string };
  moments: ReviewMoment[];
}

export type ToolSummary =
  | EngineLineSummary
  | GameListSummary
  | OpeningSummary
  | PuzzleSummary
  | CriticalMomentsSummary
  | ReviewMomentsSummary;

export type ToolSummaryKind = ToolSummary['kind'];

const MAX_LINES = 3;
const MAX_PLIES = 8;
const MAX_GAMES = 10;
const MAX_MOMENTS = 10;

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isStr = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const optNum = (v: unknown) => (isNum(v) ? v : undefined);
const optStr = (v: unknown) => (isStr(v) ? v : undefined);
const strings = (v: unknown, max: number) => (Array.isArray(v) ? v.filter(isStr).slice(0, max) : []);

function score(o: Obj): Score | null {
  if (isNum(o.mate)) return { mate: o.mate };
  if (isNum(o.eval_cp)) return { eval_cp: o.eval_cp };
  return null;
}

/** Drops undefined keys so parsed objects compare equal to the server's. */
function compact<T extends Obj>(o: T): T {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as T;
}

function engineLine(o: Obj): EngineLineSummary | null {
  const top = score(o);
  if (!isStr(o.fen) || !top || !Array.isArray(o.lines)) return null;
  const lines = o.lines
    .filter(isObj)
    .map((l) => ({ san: strings(l.san, MAX_PLIES), score: score(l) }))
    .filter((l) => l.san.length > 0 && l.score)
    .slice(0, MAX_LINES)
    .map((l) => ({ san: l.san, ...l.score! }));
  if (!lines.length) return null;
  return compact({ kind: 'engine_line' as const, fen: o.fen, ...top, depth: optNum(o.depth), lines });
}

function gameList(o: Obj): GameListSummary | null {
  if (!Array.isArray(o.games)) return null;
  const games = o.games
    .filter(isObj)
    .filter((g) => isStr(g.white) && isStr(g.black))
    .slice(0, MAX_GAMES)
    .map((g) =>
      compact({
        id: isNum(g.id) || isStr(g.id) ? (g.id as number | string) : undefined,
        white: g.white as string,
        black: g.black as string,
        result: optStr(g.result) ?? '*',
        eco: optStr(g.eco),
        year: optNum(g.year),
        white_elo: optNum(g.white_elo),
        black_elo: optNum(g.black_elo),
      }),
    );
  return games.length ? { kind: 'game_list', games } : null;
}

function opening(o: Obj): OpeningSummary | null {
  if (!isStr(o.name) || !isStr(o.eco)) return null;
  const s = isObj(o.stats) ? o.stats : null;
  const stats =
    s && isNum(s.white) && isNum(s.draw) && isNum(s.black) && isNum(s.games) && s.games > 0
      ? { white: s.white, draw: s.draw, black: s.black, games: s.games }
      : undefined;
  const moves = strings(o.moves_san, 40);
  return compact({ kind: 'opening' as const, name: o.name, eco: o.eco, moves_san: moves.length ? moves : undefined, stats });
}

function puzzle(o: Obj): PuzzleSummary | null {
  if (!isStr(o.puzzle_id) || !isStr(o.fen)) return null;
  const themes = strings(o.themes, 6);
  return compact({
    kind: 'puzzle' as const,
    puzzle_id: o.puzzle_id,
    fen: o.fen,
    rating: optNum(o.rating),
    themes: themes.length ? themes : undefined,
  });
}

function criticalMoments(o: Obj): CriticalMomentsSummary | null {
  if (!Array.isArray(o.moments)) return null;
  const moments = o.moments
    .filter(isObj)
    .filter((m) => isNum(m.ply) && isStr(m.san) && isNum(m.eval_before) && isNum(m.eval_after))
    .slice(0, MAX_MOMENTS)
    .map((m) => ({
      ply: m.ply as number,
      san: m.san as string,
      eval_before: m.eval_before as number,
      eval_after: m.eval_after as number,
      label: optStr(m.label) ?? 'mistake',
    }));
  return moments.length ? { kind: 'critical_moments', moments } : null;
}

const UCI_RE = /^[a-h][1-8][a-h][1-8][qrbn]?$/;

/** A moment whose better move is legal in its position (the board checks the student's move against it). */
function reviewMoment(m: Obj): ReviewMoment | null {
  if (!isNum(m.ply) || !isStr(m.fen) || !isStr(m.played) || !isStr(m.best) || !isStr(m.best_uci)) return null;
  if (!isStr(m.question) || !isStr(m.explanation) || !UCI_RE.test(m.best_uci)) return null;
  try {
    const chess = new Chess(m.fen);
    chess.move({ from: m.best_uci.slice(0, 2), to: m.best_uci.slice(2, 4), promotion: m.best_uci[4] });
  } catch {
    return null;
  }
  return compact({
    ply: m.ply,
    fen: m.fen,
    played: m.played,
    best: m.best,
    best_uci: m.best_uci,
    motif: optStr(m.motif),
    question: m.question,
    explanation: m.explanation,
    eval_before: optNum(m.eval_before),
    eval_after: optNum(m.eval_after),
  });
}

function reviewMoments(o: Obj): ReviewMomentsSummary | null {
  if (!isObj(o.game) || !Array.isArray(o.moments)) return null;
  const g = o.game;
  const moments = o.moments
    .filter(isObj)
    .map(reviewMoment)
    .filter((m): m is ReviewMoment => m !== null)
    .slice(0, MAX_MOMENTS);
  if (!moments.length) return null;
  const game = compact({
    white: optStr(g.white) ?? '?',
    black: optStr(g.black) ?? '?',
    result: optStr(g.result),
    id: isNum(g.id) || isStr(g.id) ? (g.id as number | string) : undefined,
  });
  return { kind: 'review_moments', game, moments };
}

/** A known, well-formed summary — or null (unknown kind, junk, missing fields). */
export function parseToolSummary(value: unknown): ToolSummary | null {
  if (!isObj(value)) return null;
  switch (value.kind) {
    case 'engine_line':
      return engineLine(value);
    case 'game_list':
      return gameList(value);
    case 'opening':
      return opening(value);
    case 'puzzle':
      return puzzle(value);
    case 'critical_moments':
      return criticalMoments(value);
    case 'review_moments':
      return reviewMoments(value);
    default:
      return null;
  }
}

/** «+0.3», «−1.2», «#3», «#−2» — an evaluation as the eval pill shows it. */
export function formatScore(s: Score): string {
  if (s.mate !== undefined) return s.mate < 0 ? `#−${-s.mate}` : `#${s.mate}`;
  const pawns = (s.eval_cp ?? 0) / 100;
  if (Math.abs(pawns) < 0.05) return '0.0';
  return `${pawns > 0 ? '+' : '−'}${Math.abs(pawns).toFixed(1)}`;
}

/** «1. e4 e5 2. Nf3», «12… Qxb2 13. O-O» — SAN moves numbered from the position's FEN. */
export function numberedLine(fen: string, san: string[]): string {
  const parts = fen.trim().split(/\s+/);
  let white = parts[1] !== 'b';
  let number = Number.parseInt(parts[5] ?? '1', 10) || 1;
  const out: string[] = [];
  san.forEach((move, i) => {
    if (white) out.push(`${number}. ${move}`);
    else out.push(i === 0 ? `${number}… ${move}` : move);
    if (!white) number += 1;
    white = !white;
  });
  return out.join(' ');
}

export type DailyPlanCard =
  | { type: 'review_last_game'; game_id: string; title: string; moments_count?: number }
  /** No theme: puzzles on any theme. `stat`: reviewed games with a blunder on the theme, of how many. */
  | { type: 'weak_spot'; puzzles: number; theme?: string; stat?: { games_with: number; games: number } }
  | { type: 'opening_lesson'; eco: string; name: string }
  | { type: 'play_coach'; level?: number };

export interface DailyPlan {
  kind: 'daily_plan';
  greeting_name?: string;
  cards: DailyPlanCard[];
}

const MAX_PLAN_CARDS = 4;

function planCard(c: Obj): DailyPlanCard | null {
  switch (c.type) {
    case 'review_last_game':
      if (!isStr(c.game_id) || !isStr(c.title)) return null;
      return compact({
        type: 'review_last_game' as const,
        game_id: c.game_id,
        title: c.title,
        moments_count: isNum(c.moments_count) && c.moments_count >= 0 ? c.moments_count : undefined,
      });
    case 'weak_spot': {
      if (!isNum(c.puzzles) || c.puzzles < 1) return null;
      const s = isObj(c.stat) ? c.stat : null;
      const stat =
        s && isNum(s.games_with) && isNum(s.games) && s.games_with > 0 && s.games_with <= s.games
          ? { games_with: s.games_with, games: s.games }
          : undefined;
      return compact({ type: 'weak_spot' as const, puzzles: c.puzzles, theme: optStr(c.theme), stat });
    }
    case 'opening_lesson':
      return isStr(c.eco) && isStr(c.name) ? { type: 'opening_lesson', eco: c.eco, name: c.name } : null;
    case 'play_coach':
      return compact({ type: 'play_coach' as const, level: optNum(c.level) });
    default:
      return null;
  }
}

/** The home screen's plan — or null (junk, or no card this client knows). */
export function parseDailyPlan(value: unknown): DailyPlan | null {
  if (!isObj(value) || value.kind !== 'daily_plan' || !Array.isArray(value.cards)) return null;
  const cards = value.cards
    .filter(isObj)
    .map(planCard)
    .filter((c): c is DailyPlanCard => c !== null)
    .slice(0, MAX_PLAN_CARDS);
  if (!cards.length) return null;
  return compact({ kind: 'daily_plan' as const, greeting_name: optStr(value.greeting_name), cards });
}
