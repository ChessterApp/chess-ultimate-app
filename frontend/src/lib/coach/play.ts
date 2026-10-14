/**
 * Game-against-the-coach helpers: strengths offered, their names, move
 * verdict badges and rematch options.
 */
import type { GameCommentMode, GameStateView } from './boards-api';

/** Opponent strengths offered at setup (Stockfish Elo). */
export const GAME_STRENGTHS = [600, 800, 1000, 1200, 1500, 1800, 2000, 2200, 2500];

export interface GameStartOptions {
  color: 'white' | 'black' | 'random';
  elo: number;
  comment_mode: GameCommentMode;
}

export type EloLevel = 'novice' | 'amateur' | 'club' | 'expert' | 'master';

/** The named level of an engine strength (an i18n key suffix). */
export function eloLevel(elo: number): EloLevel {
  if (elo < 1000) return 'novice';
  if (elo < 1500) return 'amateur';
  if (elo < 1800) return 'club';
  if (elo < 2200) return 'expert';
  return 'master';
}

/** Index of the offered strength nearest to `elo`. */
export function nearestStrengthIndex(elo: number): number {
  let best = 0;
  GAME_STRENGTHS.forEach((s, i) => {
    if (Math.abs(s - elo) < Math.abs(GAME_STRENGTHS[best] - elo)) best = i;
  });
  return best;
}

export type VerdictKind = 'blunder' | 'mistake' | 'inaccuracy' | 'good' | 'brilliant' | 'best';

export const VERDICT_SYMBOL: Record<VerdictKind, string> = {
  blunder: '??',
  mistake: '?',
  inaccuracy: '?!',
  good: '!',
  brilliant: '!!',
  best: '★',
};

export interface MoveVerdict {
  kind: VerdictKind;
  /** The square the move landed on: where the badge goes. */
  square: string;
  san: string;
  best: string | null;
}

/** The badge for the student's last move, or null when it was an ordinary good move. */
export function moveVerdict(student: GameStateView['student']): MoveVerdict | null {
  if (!student) return null;
  const square = student.uci.slice(2, 4);
  const base = { square, san: student.san, best: student.best };
  if (student.verdict !== 'ok') return { kind: student.verdict, ...base };
  if (student.best && student.best === student.san) return { kind: 'best', ...base };
  return null;
}

/** «Реванш»: the settings of the last start, else what the finished game shows. */
export function rematchOptions(game: GameStateView, last: GameStartOptions | null): GameStartOptions {
  if (last) return last;
  return { color: game.student_color, elo: game.engine_elo, comment_mode: game.comment_mode };
}

/** The coach's whole remark for the play bubble: no markdown, every sentence, capped at a word. */
export function coachRemark(markdown: string, max = 600): string {
  const plain = markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max - 1);
  const space = cut.lastIndexOf(' ');
  return `${(space > max / 2 ? cut.slice(0, space) : cut).trimEnd()}…`;
}
