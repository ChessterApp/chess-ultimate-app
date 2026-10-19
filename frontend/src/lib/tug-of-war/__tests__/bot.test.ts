// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { Chess } from 'chess.js';
import {
  BOT_LEVELS,
  botDelayMs,
  botLevel,
  botPuzzleLevel,
  pickBotMove,
  rollSolve,
  solveProbability,
  wrongMoves,
  MIN_DELAY_MS,
} from '../bot';
import { useTugBot, BOT_REPLY_DELAY_MS } from '../useTugBot';
import { evaluateTeamMove } from '../validateMove';
import type { TugPuzzle } from '../types';

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

const MATE_IN_1: TugPuzzle = {
  id: 'unAqc',
  fen: 'rnbk1r2/ppppn3/6pB/b3P3/3P4/2P5/PP4PP/RN3RK1 w - - 0 15',
  moves: ['f1f8'],
  rating: 513,
  themes: ['mateIn1'],
};
const MATE_IN_2: TugPuzzle = {
  id: 'nGWLI',
  fen: '6k1/4rppb/4pb1p/8/1P1PpPP1/p6P/P2N1P2/2R3K1 w - - 0 30',
  moves: ['c1c8', 'e7e8', 'c8e8'],
  rating: 568,
  themes: ['mateIn2'],
};

describe('BOT_LEVELS', () => {
  it('has six zebra ranks from 500 / 14s to 2000 / 4s, evenly spaced', () => {
    expect(BOT_LEVELS.map((l) => l.rating)).toEqual([500, 800, 1100, 1400, 1700, 2000]);
    expect(BOT_LEVELS.map((l) => l.secondsPerMove)).toEqual([14, 12, 10, 8, 6, 4]);
  });

  it('maps each rank to the puzzle band containing its rating', () => {
    expect(BOT_LEVELS.map(botPuzzleLevel)).toEqual(['pawn', 'knight', 'knight', 'rook', 'queen', 'queen']);
  });
});

describe('solveProbability', () => {
  it('follows the Elo expected score', () => {
    expect(solveProbability(1000, 1000)).toBeCloseTo(0.5);
    expect(solveProbability(1400, 1000)).toBeCloseTo(10 / 11);
    expect(solveProbability(1000, 1400)).toBeCloseTo(1 / 11);
    expect(solveProbability(500, 1300)).toBeCloseTo(1 / 101);
  });
});

describe('pickBotMove', () => {
  it('converges on the expected success rate with a seeded RNG', () => {
    const rng = seeded(42);
    const p = solveProbability(800, 1000);
    const N = 20_000;
    let hits = 0;
    for (let i = 0; i < N; i++) if (rollSolve(p, rng)) hits += 1;
    expect(Math.abs(hits / N - p)).toBeLessThan(0.01);
    // pickBotMove makes the same roll: same seed → same hit pattern.
    const a = seeded(9);
    const b = seeded(9);
    for (let i = 0; i < 30; i++) {
      const hit = rollSolve(p, a);
      if (!hit) a(); // the miss draws once more to pick its wrong move
      expect(pickBotMove(MATE_IN_1.fen, MATE_IN_1.moves, 0, p, b).correct).toBe(hit);
    }
  });

  it('plays the solution move on a hit', () => {
    expect(pickBotMove(MATE_IN_1.fen, MATE_IN_1.moves, 0, 1, () => 0.5)).toEqual({
      uci: 'f1f8',
      correct: true,
    });
  });

  it('plays a legal wrong move on a miss — never the solution or another mate', () => {
    const rng = seeded(7);
    const legal = new Set(new Chess(MATE_IN_1.fen).moves({ verbose: true }).map((m) => m.from + m.to));
    for (let i = 0; i < 40; i++) {
      const pick = pickBotMove(MATE_IN_1.fen, MATE_IN_1.moves, 0, 0, rng);
      expect(pick.correct).toBe(false);
      expect(pick.uci).not.toBe('f1f8');
      expect(legal.has(pick.uci)).toBe(true);
      const probe = new Chess(MATE_IN_1.fen);
      probe.move({ from: pick.uci.slice(0, 2), to: pick.uci.slice(2, 4), promotion: 'q' });
      expect(probe.isCheckmate()).toBe(false);
    }
  });

  it('wrongMoves is exactly the legal moves the board would reject', () => {
    for (const { fen, moves } of [MATE_IN_1, MATE_IN_2]) {
      const wrong = wrongMoves(fen, moves, 0);
      expect(wrong.length).toBeGreaterThan(0);
      for (const m of new Chess(fen).moves({ verbose: true })) {
        const rejected = !evaluateTeamMove(fen, moves, 0, m.from, m.to).accepted;
        expect(wrong.includes(m.from + m.to)).toBe(rejected);
      }
    }
  });
});

describe('botDelayMs', () => {
  it('stays within ±25% of secondsPerMove', () => {
    const rng = seeded(1);
    for (const level of BOT_LEVELS) {
      for (let i = 0; i < 200; i++) {
        const d = botDelayMs(level, rng);
        expect(d).toBeGreaterThanOrEqual(Math.max(MIN_DELAY_MS, level.secondsPerMove * 750));
        expect(d).toBeLessThanOrEqual(level.secondsPerMove * 1250);
      }
    }
    expect(botDelayMs(botLevel('grandmaster'), () => 0)).toBe(3000);
    expect(botDelayMs(botLevel('baby'), () => 1)).toBe(17500);
  });

  it('never drops under 1.5s', () => {
    expect(botDelayMs({ ...botLevel('grandmaster'), secondsPerMove: 1 }, () => 0)).toBe(MIN_DELAY_MS);
  });
});

describe('useTugBot', () => {
  let hidden = false;
  beforeEach(() => {
    vi.useFakeTimers();
    hidden = false;
    vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const level = botLevel('grandmaster'); // rng 0.5 → exactly 4000ms
  const setup = (puzzle: TugPuzzle, rng: () => number, active = true) => {
    const onSolved = vi.fn();
    const onWrong = vi.fn();
    const hook = renderHook((props: { active: boolean }) =>
      useTugBot({ level, puzzle, round: 0, active: props.active, onSolved, onWrong, rng }),
      { initialProps: { active } },
    );
    return { onSolved, onWrong, ...hook };
  };

  it('thinks, then solves with the scripted move', () => {
    const { onSolved, onWrong, result } = setup(MATE_IN_1, () => 0); // 0 < p → hit; delay floor 3000
    expect(result.current.thinking).toBe(true);
    act(() => vi.advanceTimersByTime(2999));
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onSolved).toHaveBeenCalledTimes(1);
    expect(onWrong).not.toHaveBeenCalled();
    expect(result.current.lastMove).toEqual(['f1', 'f8']);
  });

  it('reports a wrong move on a miss and tries again', () => {
    const { onSolved, onWrong } = setup(MATE_IN_1, () => 0.9999); // above p ≈ 0.9998
    act(() => vi.advanceTimersByTime(5000));
    expect(onWrong).toHaveBeenCalledTimes(1);
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(600 + 5000));
    expect(onWrong).toHaveBeenCalledTimes(2);
  });

  it('plays each of its moves in a multi-move puzzle, with replies in between', () => {
    const { onSolved, result } = setup(MATE_IN_2, () => 0);
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current.lastMove).toEqual(['c1', 'c8']);
    act(() => vi.advanceTimersByTime(BOT_REPLY_DELAY_MS));
    expect(result.current.lastMove).toEqual(['e7', 'e8']);
    expect(result.current.thinking).toBe(true);
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(3000));
    expect(result.current.lastMove).toEqual(['c8', 'e8']);
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it('pauses while the tab is hidden and resumes with the remaining time', () => {
    const { onSolved } = setup(MATE_IN_1, () => 0);
    act(() => vi.advanceTimersByTime(1000));
    hidden = true;
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    act(() => vi.advanceTimersByTime(60_000));
    expect(onSolved).not.toHaveBeenCalled();
    hidden = false;
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    act(() => vi.advanceTimersByTime(1999));
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it('stays still while inactive (match over) and cleans up on unmount', () => {
    const { onSolved, rerender, unmount } = setup(MATE_IN_1, () => 0, false);
    act(() => vi.advanceTimersByTime(60_000));
    expect(onSolved).not.toHaveBeenCalled();
    rerender({ active: true });
    unmount();
    act(() => vi.advanceTimersByTime(60_000));
    expect(onSolved).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
