// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { Chess } from 'chess.js';
import {
  BOT_CALIBRATION,
  BOT_LEVELS,
  BOT_REPLY_DELAY_MS,
  BOT_WRONG_SHOW_MS,
  botLevel,
  firstMoveDelayMs,
  followUpDelayMs,
  pickMissMove,
  planAttempt,
  rethinkDelayMs,
  seeProbability,
  simulateBotPuzzle,
  thinkSecondsFor,
  wrongMoveDelayMs,
  wrongMoves,
  FOLLOW_UP_MS,
  MIN_DELAY_MS,
  RETRY_BONUS,
} from '../bot';
import { useTugBot } from '../useTugBot';
import { evaluateTeamMove } from '../validateMove';
import type { TugPuzzle } from '../types';
import fixture from './fixtures/bot-calibration-puzzles.json';

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
  it('has six zebra ranks from 500 to 2000, each thinking faster than the last', () => {
    expect(BOT_LEVELS.map((l) => l.rating)).toEqual([500, 800, 1100, 1400, 1700, 2000]);
    for (let i = 1; i < BOT_LEVELS.length; i++) {
      expect(BOT_LEVELS[i].thinkSeconds).toBeLessThan(BOT_LEVELS[i - 1].thinkSeconds);
    }
  });

  it('has a calibration target per rank: more solved, faster, as the rank goes up', () => {
    const t = BOT_LEVELS.map((l) => BOT_CALIBRATION[l.id]);
    for (let i = 1; i < t.length; i++) {
      expect(t[i].solveRate).toBeGreaterThan(t[i - 1].solveRate);
      expect(t[i].secondsPerPuzzle).toBeLessThan(t[i - 1].secondsPerPuzzle);
    }
  });

  it('interpolates think time between ranks and clamps outside them', () => {
    expect(thinkSecondsFor(300)).toBe(BOT_LEVELS[0].thinkSeconds);
    expect(thinkSecondsFor(2600)).toBe(BOT_LEVELS[5].thinkSeconds);
    expect(thinkSecondsFor(950)).toBeCloseTo((BOT_LEVELS[1].thinkSeconds + BOT_LEVELS[2].thinkSeconds) / 2);
  });
});

describe('seeProbability', () => {
  it('rises with the bot rating and falls with the puzzle rating and line length', () => {
    expect(seeProbability(1400, 1000, 1)).toBeGreaterThan(seeProbability(1100, 1000, 1));
    expect(seeProbability(1400, 1600, 1)).toBeLessThan(seeProbability(1400, 1200, 1));
    expect(seeProbability(1400, 1400, 3)).toBeLessThan(seeProbability(1400, 1400, 1));
  });

  it('each rejected idea closes RETRY_BONUS of the remaining gap', () => {
    const p0 = seeProbability(800, 800, 2);
    const p1 = seeProbability(800, 800, 2, 1);
    const p2 = seeProbability(800, 800, 2, 2);
    expect(p1).toBeGreaterThan(p0);
    expect(p2).toBeGreaterThan(p1);
    expect(1 - p1).toBeCloseTo((1 - p0) * (1 - RETRY_BONUS));
  });
});

describe('one roll per puzzle', () => {
  it('a seen first roll plays the whole line with zero misses', () => {
    const level = botLevel('club');
    const p0 = seeProbability(level.rating, MATE_IN_2.rating, 2);
    for (let seed = 1; seed <= 300; seed++) {
      const rng = seeded(seed);
      let first: number | null = null;
      const spy = () => {
        const v = rng();
        first ??= v;
        return v;
      };
      const r = simulateBotPuzzle(level, MATE_IN_2, spy);
      if (first! < p0) expect(r).toMatchObject({ solved: true, misses: 0 });
      else expect(r.misses).toBeGreaterThan(0);
    }
  });

  it('an unseen attempt is a quick wrong move; a seen retry comes after a longer rethink', () => {
    const level = botLevel('junior');
    const miss = planAttempt(level, MATE_IN_2, 0, true, () => 0.9999);
    expect(miss.seen).toBe(false);
    const retry = planAttempt(level, MATE_IN_2, 1, true, () => 0);
    expect(retry).toEqual({ seen: true, delayMs: rethinkDelayMs(level, () => 0) });
    expect(miss.delayMs).toBeLessThan(retry.delayMs);
  });

  it('cannot miss when no wrong move is left', () => {
    expect(planAttempt(botLevel('baby'), MATE_IN_2, 2, false, () => 0.9999).seen).toBe(true);
  });
});

describe('pickMissMove', () => {
  const legal = (fen: string) => new Set(new Chess(fen).moves({ verbose: true }).map((m) => m.from + m.to));

  it('plays legal wrong moves — never the solution, an alternative mate or a rejected move', () => {
    for (const { fen, moves } of [MATE_IN_1, MATE_IN_2]) {
      const rng = seeded(3);
      const rejected: string[] = [];
      const all = wrongMoves(fen, moves, 0);
      for (;;) {
        const uci = pickMissMove(fen, moves, 0, rejected, rng);
        if (uci === null) break;
        expect(legal(fen).has(uci)).toBe(true);
        expect(uci).not.toBe(moves[0].slice(0, 4));
        expect(all).toContain(uci);
        expect(rejected).not.toContain(uci);
        rejected.push(uci);
      }
      // Null only once every wrong move has been rejected.
      expect(rejected.sort()).toEqual([...all].sort());
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

  it('prefers checks and captures when they are available', () => {
    const rng = seeded(11);
    let picks = 0;
    let tempting = 0;
    let pool = 0;
    let poolTempting = 0;
    for (const p of (fixture as TugPuzzle[]).filter((_, i) => i % 8 === 0)) {
      const chess = new Chess(p.fen);
      const isTempting = new Set(
        chess
          .moves({ verbose: true })
          .filter((m) => m.captured || m.san.includes('+'))
          .map((m) => m.from + m.to),
      );
      const wrong = wrongMoves(p.fen, p.moves, 0);
      if (!wrong.some((m) => isTempting.has(m))) continue;
      pool += wrong.length;
      poolTempting += wrong.filter((m) => isTempting.has(m)).length;
      for (let i = 0; i < 4; i++) {
        picks += 1;
        if (isTempting.has(pickMissMove(p.fen, p.moves, 0, [], rng)!)) tempting += 1;
      }
    }
    expect(tempting / picks).toBeGreaterThan(0.5);
    expect(tempting / picks).toBeGreaterThan(2 * (poolTempting / pool));
  }, 20_000);

  it('falls back to a quiet move only when nothing is tempting', () => {
    // Lone kings and a pawn: no checks, captures or moves near the solution.
    const fen = '7k/8/8/8/8/8/P7/K7 w - - 0 1';
    const pick = pickMissMove(fen, ['a2a4'], 0, [], () => 0);
    expect(legal(fen).has(pick!)).toBe(true);
    expect(pick).not.toBe('a2a4');
  });
});

describe('human timing', () => {
  const samples = (fn: (rng: () => number) => number, seed: number, n = 400) => {
    const rng = seeded(seed);
    return Array.from({ length: n }, () => fn(rng));
  };
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

  it('follow-up moves (1–3 s) come faster than the first move', () => {
    for (const level of BOT_LEVELS) {
      const follow = samples((r) => followUpDelayMs(level, r), 1);
      const first = samples((r) => firstMoveDelayMs(level, level.rating, r), 2);
      for (const d of follow) {
        expect(d).toBeGreaterThanOrEqual(FOLLOW_UP_MS[0]);
        expect(d).toBeLessThanOrEqual(FOLLOW_UP_MS[1]);
      }
      expect(mean(follow)).toBeLessThan(mean(first));
      expect(followUpDelayMs(level, () => 0.5)).toBeLessThan(firstMoveDelayMs(level, level.rating, () => 0.5));
    }
    expect(mean(samples((r) => followUpDelayMs(botLevel('grandmaster'), r), 3))).toBeLessThan(
      mean(samples((r) => followUpDelayMs(botLevel('baby'), r), 3)),
    );
  });

  it('a wrong move always comes quicker than the rethink after it', () => {
    for (const level of BOT_LEVELS) {
      for (const v of [0, 0.3, 0.7, 0.9999]) {
        expect(wrongMoveDelayMs(level, () => v)).toBeLessThan(rethinkDelayMs(level, () => v));
      }
    }
  });

  it('thinks longer on harder puzzles, sometimes gets stuck, never under 1.5 s', () => {
    const level = botLevel('club');
    const easy = mean(samples((r) => firstMoveDelayMs(level, 800, r), 4));
    const hard = mean(samples((r) => firstMoveDelayMs(level, 1500, r), 4));
    expect(hard).toBeGreaterThan(easy);
    const own = samples((r) => firstMoveDelayMs(level, level.rating, r), 5, 4000);
    expect(Math.abs(mean(own) / (level.thinkSeconds * 1000) - 1.1)).toBeLessThan(0.08); // +10% stuck
    expect(Math.min(...samples((r) => firstMoveDelayMs(botLevel('grandmaster'), 400, r), 6))).toBeGreaterThanOrEqual(
      MIN_DELAY_MS,
    );
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

  const level = botLevel('grandmaster');
  // A constant RNG makes every delay the hook draws equal to these.
  const first = (p: TugPuzzle, v = 0) => firstMoveDelayMs(level, p.rating, () => v);
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
    const { onSolved, onWrong, result } = setup(MATE_IN_1, () => 0); // 0 < p → seen
    expect(result.current.thinking).toBe(true);
    act(() => vi.advanceTimersByTime(first(MATE_IN_1) - 1));
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onSolved).toHaveBeenCalledTimes(1);
    expect(onWrong).not.toHaveBeenCalled();
    expect(result.current.lastMove).toEqual(['f1', 'f8']);
  });

  it('misses quickly with a plausible move, never repeats it, and rethinks longer', () => {
    const { onSolved, onWrong, result } = setup(MATE_IN_1, () => 0.9999); // above every p
    const wrong = wrongMoveDelayMs(level, () => 0.9999);
    act(() => vi.advanceTimersByTime(wrong));
    expect(onWrong).toHaveBeenCalledTimes(1);
    const firstMiss = result.current.lastMove!.join('');
    expect(firstMiss).not.toBe('f1f8');
    act(() => vi.advanceTimersByTime(BOT_WRONG_SHOW_MS + wrong));
    expect(onWrong).toHaveBeenCalledTimes(2);
    expect(result.current.lastMove!.join('')).not.toBe(firstMiss);
    expect(onSolved).not.toHaveBeenCalled();
  });

  it('a seen line plays every move: long first think, quick follow-up after the reply', () => {
    const { onSolved, onWrong, result } = setup(MATE_IN_2, () => 0);
    act(() => vi.advanceTimersByTime(first(MATE_IN_2)));
    expect(result.current.lastMove).toEqual(['c1', 'c8']);
    act(() => vi.advanceTimersByTime(BOT_REPLY_DELAY_MS));
    expect(result.current.lastMove).toEqual(['e7', 'e8']);
    expect(result.current.thinking).toBe(true);
    const follow = followUpDelayMs(level, () => 0);
    expect(follow).toBeLessThan(first(MATE_IN_2));
    act(() => vi.advanceTimersByTime(follow - 1));
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(result.current.lastMove).toEqual(['c8', 'e8']);
    expect(onSolved).toHaveBeenCalledTimes(1);
    expect(onWrong).not.toHaveBeenCalled();
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
    act(() => vi.advanceTimersByTime(first(MATE_IN_1) - 1001));
    expect(onSolved).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onSolved).toHaveBeenCalledTimes(1);
  });

  it('follows a changing (adaptive) level without restarting the puzzle', () => {
    const onSolved = vi.fn();
    const slow = { ...level, id: 'baby' as const, rating: 500, thinkSeconds: 12 };
    const fast = { ...level, id: 'grandmaster' as const, rating: 2000, thinkSeconds: 2.4 };
    const hook = renderHook(
      (props: { lv: typeof level }) =>
        useTugBot({ level: props.lv, puzzle: MATE_IN_2, round: 0, active: true, onSolved, onWrong: vi.fn(), rng: () => 0 }),
      { initialProps: { lv: slow } },
    );
    act(() => vi.advanceTimersByTime(firstMoveDelayMs(slow, MATE_IN_2.rating, () => 0))); // the slow first think
    expect(hook.result.current.lastMove).toEqual(['c1', 'c8']);
    hook.rerender({ lv: fast }); // rank and speed change mid-puzzle
    act(() => vi.advanceTimersByTime(BOT_REPLY_DELAY_MS));
    expect(hook.result.current.lastMove).toEqual(['e7', 'e8']); // same puzzle, not reset
    const follow = followUpDelayMs(fast, () => 0); // the follow-up uses the fast pace
    expect(follow).toBeLessThan(followUpDelayMs(slow, () => 0));
    act(() => vi.advanceTimersByTime(follow - 1));
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
