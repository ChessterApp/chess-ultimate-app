/**
 * Calibration of the bot model against 240 real puzzles (40 per rank rating,
 * from api.chesster.io): a seeded Monte Carlo of simulateBotPuzzle — the same
 * rolls and delays useTugBot schedules, without timers.
 */
import { describe, it, expect } from 'vitest';
import { BOT_CALIBRATION, BOT_LEVELS, simulateBotPuzzle, wrongMoves, type BotLevel } from '../bot';
import fixture from './fixtures/bot-calibration-puzzles.json';

interface Fixture {
  id: string;
  fen: string;
  moves: string[];
  rating: number;
}

const PUZZLES = (fixture as Fixture[]).map((p) => ({ ...p, wrong: wrongMoves(p.fen, p.moves, 0).length }));
const RUNS = 60;

/** Deterministic mulberry32 RNG. */
function seeded(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function measure(level: BotLevel, puzzles: typeof PUZZLES, seed = 1) {
  const rng = seeded(seed);
  let solved = 0;
  let ms = 0;
  for (let run = 0; run < RUNS; run++) {
    for (const p of puzzles) {
      const r = simulateBotPuzzle(level, p, rng, p.wrong);
      if (r.solved) solved += 1;
      ms += r.ms;
    }
  }
  const n = RUNS * puzzles.length;
  return { solveRate: solved / n, seconds: ms / n / 1000 };
}

const own = BOT_LEVELS.map((level) =>
  measure(level, PUZZLES.filter((p) => Math.abs(p.rating - level.rating) <= 150)),
);

describe('bot calibration (puzzles at its own rating ±150)', () => {
  it.each(BOT_LEVELS.map((l, i) => [l.id, l, own[i]] as const))(
    '%s hits its solve rate and time targets',
    (_id, level, got) => {
      const target = BOT_CALIBRATION[level.id];
      expect(Math.abs(got.solveRate - target.solveRate)).toBeLessThanOrEqual(0.07);
      expect(Math.abs(got.seconds - target.secondsPerPuzzle) / target.secondsPerPuzzle).toBeLessThanOrEqual(0.3);
    },
  );

  it('each stronger rank solves more, faster', () => {
    for (let i = 1; i < own.length; i++) {
      expect(own[i].solveRate).toBeGreaterThan(own[i - 1].solveRate);
      expect(own[i].seconds).toBeLessThan(own[i - 1].seconds);
    }
  });
});

describe('bot calibration (one common puzzle set)', () => {
  it('each stronger rank solves more, faster on the whole fixture', () => {
    const all = BOT_LEVELS.map((level) => measure(level, PUZZLES, 7));
    for (let i = 1; i < all.length; i++) {
      expect(all[i].solveRate).toBeGreaterThan(all[i - 1].solveRate);
      expect(all[i].seconds).toBeLessThan(all[i - 1].seconds);
    }
  });
});

if (process.env.BOT_CALIBRATION_REPORT) {
  for (const [i, l] of BOT_LEVELS.entries()) {
    console.log(l.id, (own[i].solveRate * 100).toFixed(1), own[i].seconds.toFixed(1));
  }
}
