import { describe, it, expect } from 'vitest';
import { formatScore, numberedLine, parseDailyPlan, parseToolSummary } from '../tool-summary';

const FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('parseToolSummary', () => {
  it('accepts each kind the server sends, unchanged', () => {
    const samples = [
      { kind: 'engine_line', fen: FEN, eval_cp: 30, depth: 16, lines: [{ san: ['e4', 'e5'], eval_cp: 30 }, { san: ['d4'], mate: 3 }] },
      { kind: 'game_list', games: [{ id: 7, white: 'Kasparov', black: 'Topalov', result: '1-0', eco: 'B07', year: 1999, white_elo: 2812, black_elo: 2700 }] },
      { kind: 'opening', name: 'Sicilian Defense', eco: 'B20', moves_san: ['e4', 'c5'], stats: { white: 35.5, draw: 40, black: 24.5, games: 1200 } },
      { kind: 'puzzle', puzzle_id: 'abc', fen: FEN, rating: 1500, themes: ['fork'] },
      { kind: 'critical_moments', moments: [{ ply: 26, san: 'Qxb2', eval_before: 40, eval_after: -260, label: 'blunder' }] },
    ];
    for (const s of samples) expect(parseToolSummary(s)).toEqual(s);
  });

  it('rejects unknown kinds and junk', () => {
    for (const v of [null, undefined, 'x', 3, [], {}, { kind: 'daily_plan' }, { kind: 'review_moments', moments: [] }]) {
      expect(parseToolSummary(v)).toBeNull();
    }
  });

  it('rejects summaries missing what the card needs', () => {
    expect(parseToolSummary({ kind: 'engine_line', fen: FEN, lines: [{ san: ['e4'], eval_cp: 1 }] })).toBeNull();
    expect(parseToolSummary({ kind: 'engine_line', fen: FEN, eval_cp: 1, lines: [{ san: [], eval_cp: 1 }] })).toBeNull();
    expect(parseToolSummary({ kind: 'game_list', games: [{ white: 'A' }] })).toBeNull();
    expect(parseToolSummary({ kind: 'opening', name: 'x' })).toBeNull();
    expect(parseToolSummary({ kind: 'puzzle', puzzle_id: 'p' })).toBeNull();
    expect(parseToolSummary({ kind: 'critical_moments', moments: [{ ply: 1 }] })).toBeNull();
  });

  it('drops bad fields and caps lists', () => {
    const lines = Array.from({ length: 6 }, () => ({ san: Array(12).fill('Nf3'), eval_cp: 1 }));
    const s = parseToolSummary({ kind: 'engine_line', fen: FEN, eval_cp: 1, depth: 'deep', lines });
    expect(s && s.kind === 'engine_line' && s.lines.length).toBe(3);
    expect(s && s.kind === 'engine_line' && s.lines[0].san.length).toBe(8);
    expect(s && 'depth' in s).toBe(false);
    const games = parseToolSummary({
      kind: 'game_list',
      games: Array.from({ length: 15 }, (_, i) => ({ id: i, white: 'W', black: 'B', year: 'old' })),
    });
    expect(games && games.kind === 'game_list' && games.games.length).toBe(10);
    expect(games && games.kind === 'game_list' && games.games[0]).toEqual({ id: 0, white: 'W', black: 'B', result: '*' });
    const op = parseToolSummary({ kind: 'opening', name: 'x', eco: 'A00', stats: { white: 1, draw: 1, black: 1, games: 0 } });
    expect(op).toEqual({ kind: 'opening', name: 'x', eco: 'A00' });
  });
});

describe('formatScore', () => {
  it('formats evaluations and mates from White’s side', () => {
    expect(formatScore({ eval_cp: 31 })).toBe('+0.3');
    expect(formatScore({ eval_cp: -120 })).toBe('−1.2');
    expect(formatScore({ eval_cp: 2 })).toBe('0.0');
    expect(formatScore({ mate: 3 })).toBe('#3');
    expect(formatScore({ mate: -2 })).toBe('#−2');
  });
});

describe('numberedLine', () => {
  it('numbers from the position, Black to move with an ellipsis', () => {
    expect(numberedLine(FEN, ['e4', 'e5', 'Nf3'])).toBe('1. e4 e5 2. Nf3');
    expect(numberedLine('8/8/8/8/8/8/8/K6k b - - 0 12', ['Qxb2', 'O-O', 'Kh1'])).toBe('12… Qxb2 13. O-O Kh1');
  });
});

// 13.Nc7+ forks the king and the rook (hermes/tests/unit/test_review_moments.py).
const FORK_FEN = 'r3k3/8/8/1N6/8/8/8/4K3 w - - 0 13';
const MOMENT = {
  ply: 25,
  fen: FORK_FEN,
  played: 'Ke2',
  best: 'Nc7+',
  best_uci: 'b5c7',
  motif: 'fork',
  question: 'В партии было 13.Ke2. Найдите ход сильнее за белых.',
  explanation: 'Сильнее 13.Nc7+ — вилка.',
  eval_before: 480,
  eval_after: 10,
};

describe('review_moments', () => {
  it('accepts what the server sends, unchanged', () => {
    const s = { kind: 'review_moments', game: { white: 'Student', black: 'Bot', result: '0-1', id: 'g1' }, moments: [MOMENT] };
    expect(parseToolSummary(s)).toEqual(s);
  });

  it('drops a moment whose better move is not legal there, or that lacks a field', () => {
    const bad = [
      { ...MOMENT, best_uci: 'b5b6' },
      { ...MOMENT, best_uci: 'Nc7+' },
      { ...MOMENT, fen: 'junk' },
      { ...MOMENT, question: '' },
      { ...MOMENT, ply: '25' },
      'row',
    ];
    const s = parseToolSummary({ kind: 'review_moments', game: { white: 'A', black: 'B' }, moments: [...bad, MOMENT] });
    expect(s && s.kind === 'review_moments' && s.moments).toEqual([MOMENT]);
    expect(parseToolSummary({ kind: 'review_moments', game: { white: 'A', black: 'B' }, moments: bad })).toBeNull();
  });

  it('caps at 10 moments, defaults missing players, needs a game object', () => {
    const s = parseToolSummary({ kind: 'review_moments', game: {}, moments: Array(14).fill(MOMENT) });
    expect(s && s.kind === 'review_moments' && s.moments.length).toBe(10);
    expect(s && s.kind === 'review_moments' && s.game).toEqual({ white: '?', black: '?' });
    expect(parseToolSummary({ kind: 'review_moments', moments: [MOMENT] })).toBeNull();
  });
});

describe('parseDailyPlan', () => {
  const FULL = {
    kind: 'daily_plan',
    cards: [
      { type: 'review_last_game', game_id: 'g1', title: 'Student – Bot', moments_count: 3 },
      { type: 'weak_spot', puzzles: 5, theme: 'endgame', stat: { games_with: 4, games: 10 } },
      { type: 'opening_lesson', eco: 'C50', name: 'Italian Game' },
      { type: 'play_coach' },
    ],
  };

  it('accepts the full and the minimal plan, unchanged', () => {
    expect(parseDailyPlan(FULL)).toEqual(FULL);
    const minimal = { kind: 'daily_plan', cards: [{ type: 'weak_spot', puzzles: 5 }, { type: 'play_coach' }] };
    expect(parseDailyPlan(minimal)).toEqual(minimal);
  });

  it('drops unknown or broken cards and impossible stats', () => {
    const plan = parseDailyPlan({
      kind: 'daily_plan',
      cards: [
        { type: 'streak', days: 3 },
        { type: 'review_last_game', title: 'no id' },
        { type: 'weak_spot', puzzles: 5, theme: 'fork', stat: { games_with: 11, games: 10 } },
        { type: 'opening_lesson', eco: 'C50' },
        { type: 'play_coach', level: 'hard' },
      ],
    });
    expect(plan).toEqual({ kind: 'daily_plan', cards: [{ type: 'weak_spot', puzzles: 5, theme: 'fork' }, { type: 'play_coach' }] });
  });

  it('is null for junk or a plan with nothing this client knows', () => {
    for (const v of [null, 'x', {}, { kind: 'daily_plan' }, { kind: 'daily_plan', cards: [{ type: 'x' }] }, { ...FULL, kind: 'other' }]) {
      expect(parseDailyPlan(v)).toBeNull();
    }
  });

  it('keeps at most four cards', () => {
    const plan = parseDailyPlan({ kind: 'daily_plan', cards: [...FULL.cards, { type: 'play_coach' }] });
    expect(plan?.cards).toHaveLength(4);
  });
});
