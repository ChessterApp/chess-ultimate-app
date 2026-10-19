import { describe, it, expect } from 'vitest';
import {
  adaptiveReducer,
  expectedScore,
  initialAdaptive,
  initialLadder,
  initialPlayer,
  kFactor,
  ladderBotLevel,
  loadAdaptive,
  nearestRank,
  rankNumber,
  saveAdaptive,
  stepLadder,
  targetRating,
  toSaved,
  updatePlayer,
  BOT_MIN_SECONDS,
  BOT_START_SECONDS,
  K_MIN,
  K_START,
  RESUME_SEEN,
  STORAGE_KEY,
  type AdaptiveState,
} from '../adaptive';
import { BOT_LEVELS } from '../bot';

function memoryStorage() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
  };
}

describe('player rating update', () => {
  it('moves up on a solve and down on a skip, by K × surprise', () => {
    const p = initialPlayer();
    expect(p).toEqual({ estimate: 1000, seen: 0, avgSeconds: null });
    const up = updatePlayer(p, 1000, true, 6);
    expect(up.estimate).toBeCloseTo(1000 + K_START * 0.5);
    const down = updatePlayer(p, 1000, false);
    expect(down.estimate).toBeCloseTo(1000 - K_START * 0.5);
    expect(up.seen).toBe(1);
  });

  it('gains little for an easy solve and loses a lot for an easy skip', () => {
    const p = initialPlayer();
    const easySolve = updatePlayer(p, 600, true).estimate - 1000;
    const hardSolve = updatePlayer(p, 1400, true).estimate - 1000;
    const easySkip = 1000 - updatePlayer(p, 600, false).estimate;
    expect(easySolve).toBeLessThan(hardSolve);
    expect(easySkip).toBeCloseTo(K_START * expectedScore(1000, 600));
    expect(easySkip).toBeGreaterThan(easySolve);
  });

  it('decays K from 64 towards 24 as puzzles are seen', () => {
    expect(kFactor(0)).toBe(K_START);
    expect(kFactor(5)).toBeLessThan(kFactor(1));
    expect(kFactor(60)).toBeCloseTo(K_MIN, 1);
    expect(kFactor(1000)).toBeGreaterThanOrEqual(K_MIN);
  });

  it('keeps an EMA of seconds per solve; skips leave it alone', () => {
    let p = updatePlayer(initialPlayer(), 1000, true, 10);
    expect(p.avgSeconds).toBe(10);
    p = updatePlayer(p, 1000, true, 4);
    expect(p.avgSeconds).toBeCloseTo(10 + 0.3 * (4 - 10));
    expect(updatePlayer(p, 1000, false).avgSeconds).toBe(p.avgSeconds);
  });

  it('resumes from a saved estimate with a calmer K', () => {
    const p = initialPlayer({ estimate: 1340, avgSeconds: 7, peakBotLevel: 'expert', date: '' });
    expect(p).toEqual({ estimate: 1340, seen: RESUME_SEEN, avgSeconds: 7 });
  });
});

describe('bot ladder', () => {
  it('starts 300 below the player and slow, never under 400', () => {
    expect(initialLadder(1000)).toEqual({ rating: 700, secondsPerMove: BOT_START_SECONDS });
    expect(initialLadder(500).rating).toBe(400);
  });

  it('climbs +100 / −1 s per step and drops half a step', () => {
    const l = initialLadder(1000);
    expect(stepLadder(l, 1)).toEqual({ rating: 800, secondsPerMove: 13 });
    expect(stepLadder(stepLadder(l, 1), -0.5)).toEqual({ rating: 750, secondsPerMove: 13.5 });
  });

  it('never gets faster than 3 s or slower than the start', () => {
    let l = initialLadder(1000);
    for (let i = 0; i < 30; i++) l = stepLadder(l, 1);
    expect(l.secondsPerMove).toBe(BOT_MIN_SECONDS);
    for (let i = 0; i < 80; i++) l = stepLadder(l, -0.5);
    expect(l.secondsPerMove).toBe(BOT_START_SECONDS);
    expect(l.rating).toBe(400);
  });
});

describe('adaptiveReducer', () => {
  const start = (): AdaptiveState => initialAdaptive();

  it('steps the bot up when the human solves and records the rating beaten', () => {
    const s = adaptiveReducer(start(), { type: 'HUMAN_SOLVED', puzzleRating: 900, seconds: 8 });
    expect(s.ladder).toEqual({ rating: 800, secondsPerMove: 13 });
    expect(s.peakBeaten).toBe(700);
    expect(s.player.estimate).toBeGreaterThan(1000);
    expect(s.player.avgSeconds).toBe(8);
  });

  it('drops the bot half a step when it solves; a skip only scores the player', () => {
    const s = adaptiveReducer(start(), { type: 'BOT_SOLVED' });
    expect(s.ladder).toEqual({ rating: 650, secondsPerMove: 14 });
    expect(s.player.estimate).toBe(1000);
    const skip = adaptiveReducer(start(), { type: 'HUMAN_SKIPPED', puzzleRating: 900 });
    expect(skip.ladder).toEqual(start().ladder);
    expect(skip.player.estimate).toBeLessThan(1000);
  });

  it('creeps +25 per 20 s tick', () => {
    let s = start();
    for (let i = 0; i < 4; i++) s = adaptiveReducer(s, { type: 'CREEP' });
    expect(s.ladder.rating).toBe(800);
    expect(s.ladder.secondsPerMove).toBe(13);
  });

  it('flags the trend when the displayed rank changes', () => {
    let s = start(); // 700 → Junior (lv 2)
    expect(s.trend).toBeNull();
    s = adaptiveReducer(s, { type: 'HUMAN_SOLVED', puzzleRating: 900, seconds: 5 }); // 800, still Junior
    expect(s.trend).toBeNull();
    s = adaptiveReducer(s, { type: 'HUMAN_SOLVED', puzzleRating: 900, seconds: 5 }); // 900, still Junior
    s = adaptiveReducer(s, { type: 'HUMAN_SOLVED', puzzleRating: 900, seconds: 5 }); // 1000 → Club
    expect(rankNumber(s.ladder.rating)).toBe(3);
    expect(s.trend).toBe('up');
    s = adaptiveReducer(s, { type: 'BOT_SOLVED' }); // 950: a Junior/Club tie goes to the lower rank
    expect(s.trend).toBe('down');
  });
});

describe('rank mapping and puzzle target', () => {
  it('maps a bot rating to the nearest zebra rank', () => {
    expect(nearestRank(400).id).toBe('baby');
    expect(nearestRank(640).id).toBe('baby');
    expect(nearestRank(660).id).toBe('junior');
    expect(nearestRank(1450).id).toBe('expert');
    expect(nearestRank(2800).id).toBe('grandmaster');
    expect(BOT_LEVELS.map((l) => rankNumber(l.rating))).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('plays the ladder rating and speed under the rank colour', () => {
    const bot = ladderBotLevel({ rating: 1430, secondsPerMove: 7 });
    expect(bot).toEqual({ id: 'expert', color: BOT_LEVELS[3].color, rating: 1430, secondsPerMove: 7 });
  });

  it('targets the bot rating blended toward the player', () => {
    expect(targetRating(initialAdaptive())).toBe(820); // 0.6·700 + 0.4·1000
    expect(targetRating({ ladder: { rating: 2800, secondsPerMove: 3 }, player: initialPlayer() })).toBe(2080);
  });
});

describe('persistence', () => {
  it('round-trips estimate, speed, peak rank and date', () => {
    const storage = memoryStorage();
    let s = initialAdaptive();
    for (let i = 0; i < 8; i++) s = adaptiveReducer(s, { type: 'HUMAN_SOLVED', puzzleRating: 1200, seconds: 6.44 });
    const saved = toSaved(s, () => new Date('2026-10-19T10:00:00Z'));
    expect(saved.date).toBe('2026-10-19T10:00:00.000Z');
    expect(saved.peakBotLevel).toBe('expert'); // beaten at 1400
    expect(saved.avgSeconds).toBe(6.4);
    expect(Number.isInteger(saved.estimate)).toBe(true);

    saveAdaptive(saved, storage);
    expect(storage.data.has(STORAGE_KEY)).toBe(true);
    expect(loadAdaptive(storage)).toEqual(saved);
    // A rematch starts near the saved level.
    expect(initialAdaptive(loadAdaptive(storage)).player.estimate).toBe(saved.estimate);
  });

  it('saves no peak when nothing was beaten', () => {
    expect(toSaved(initialAdaptive(), () => new Date(0)).peakBotLevel).toBeNull();
  });

  it('ignores missing or malformed data and clamps the estimate', () => {
    const storage = memoryStorage();
    expect(loadAdaptive(storage)).toBeNull();
    storage.setItem(STORAGE_KEY, '{nope');
    expect(loadAdaptive(storage)).toBeNull();
    storage.setItem(STORAGE_KEY, JSON.stringify({ estimate: 'x' }));
    expect(loadAdaptive(storage)).toBeNull();
    storage.setItem(STORAGE_KEY, JSON.stringify({ estimate: 9000, peakBotLevel: 'king' }));
    expect(loadAdaptive(storage)).toEqual({ estimate: 2800, avgSeconds: null, peakBotLevel: null, date: '' });
  });
});
