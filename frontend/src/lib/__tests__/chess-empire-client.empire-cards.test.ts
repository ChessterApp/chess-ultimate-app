/**
 * Tests for the "Survivor" / "Bot Slayer" homepage-card extraction helpers:
 * bestSurvivalScore, bestDefeatedBot, and their wiring into getStudentProfile.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  bestSurvivalScore,
  bestDefeatedBot,
  getStudentProfile,
  getStudentRank,
} from '../chess-empire-client';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

describe('bestSurvivalScore', () => {
  it('returns the max value across a plain number array', () => {
    expect(bestSurvivalScore([12, 47, 33])).toBe(47);
  });

  it('reads the value from objects (score / survival_score / value)', () => {
    expect(
      bestSurvivalScore([{ score: 20 }, { survival_score: 55 }, { value: 40 }]),
    ).toBe(55);
  });

  it('coerces numeric strings', () => {
    expect(bestSurvivalScore(['10', '30', '5'])).toBe(30);
  });

  it('handles a tie by returning that shared max', () => {
    expect(bestSurvivalScore([42, 42, 10])).toBe(42);
  });

  it('ignores invalid entries but keeps valid ones', () => {
    expect(bestSurvivalScore([{ nope: 1 }, 'abc', null, 18])).toBe(18);
  });

  it('returns null for an empty array', () => {
    expect(bestSurvivalScore([])).toBeNull();
  });

  it('returns null for missing / non-array input', () => {
    expect(bestSurvivalScore(undefined)).toBeNull();
    expect(bestSurvivalScore(null)).toBeNull();
    expect(bestSurvivalScore('nope')).toBeNull();
  });
});

describe('bestDefeatedBot', () => {
  it('picks the highest-rated bot (every row is a defeated bot)', () => {
    const battles = [
      { bot_name: 'Pawn', bot_rating: 800 },
      { bot_name: 'Titan', bot_rating: 2100 },
      { bot_name: 'Knight', bot_rating: 1200 },
    ];
    expect(bestDefeatedBot(battles)).toEqual({ name: 'Titan', rating: 2100 });
  });

  it('does not require any win/result field', () => {
    expect(
      bestDefeatedBot([{ bot_name: 'Titan', bot_rating: 2100 }]),
    ).toEqual({ name: 'Titan', rating: 2100 });
  });

  it('accepts alternate field names (name / rating)', () => {
    expect(
      bestDefeatedBot([{ name: 'Rookie', rating: 950 }]),
    ).toEqual({ name: 'Rookie', rating: 950 });
  });

  it('keeps the first-seen bot on a rating tie', () => {
    const battles = [
      { bot_name: 'First', bot_rating: 1500 },
      { bot_name: 'Second', bot_rating: 1500 },
    ];
    expect(bestDefeatedBot(battles)).toEqual({ name: 'First', rating: 1500 });
  });

  it('skips entries missing a name or a finite rating', () => {
    const battles = [
      { bot_rating: 3000 },
      { bot_name: 'NoRating' },
      { bot_name: 'Good', bot_rating: 1100 },
    ];
    expect(bestDefeatedBot(battles)).toEqual({ name: 'Good', rating: 1100 });
  });

  it('returns null for empty / missing / non-array input', () => {
    expect(bestDefeatedBot([])).toBeNull();
    expect(bestDefeatedBot(undefined)).toBeNull();
    expect(bestDefeatedBot(null)).toBeNull();
    expect(bestDefeatedBot({})).toBeNull();
  });
});

describe('getStudentProfile — survival/bot extraction', () => {
  const originalKey = process.env.CHESS_EMPIRE_SERVICE_KEY;
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  beforeEach(() => {
    process.env.CHESS_EMPIRE_SERVICE_KEY = 'ce-test-key';
    fetchSpy.mockReset();
  });
  afterEach(() => {
    if (originalKey === undefined) delete process.env.CHESS_EMPIRE_SERVICE_KEY;
    else process.env.CHESS_EMPIRE_SERVICE_KEY = originalKey;
  });

  it('reads survival_scores / bot_battles as siblings of student under data', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          student: {
            id: 'stu-1',
            first_name: 'A',
            status: 'active',
            branch_id: 'br-1',
          },
          survival_scores: [15, 62, 40],
          bot_battles: [
            { bot_name: 'Pawn', bot_rating: 800 },
            { bot_name: 'Titan', bot_rating: 2100 },
          ],
        },
      }),
    );
    const profile = await getStudentProfile('stu-1');
    expect(profile.best_survival_score).toBe(62);
    expect(profile.best_defeated_bot).toEqual({ name: 'Titan', rating: 2100 });
  });

  it('sets both to null when the arrays are absent', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ id: 'stu-1', first_name: 'A' }),
    );
    const profile = await getStudentProfile('stu-1');
    expect(profile.best_survival_score).toBeNull();
    expect(profile.best_defeated_bot).toBeNull();
  });
});

describe('getStudentRank', () => {
  const originalKey = process.env.CHESS_EMPIRE_SERVICE_KEY;
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  beforeEach(() => {
    process.env.CHESS_EMPIRE_SERVICE_KEY = 'ce-test-key';
    fetchSpy.mockReset();
  });
  afterEach(() => {
    if (originalKey === undefined) delete process.env.CHESS_EMPIRE_SERVICE_KEY;
    else process.env.CHESS_EMPIRE_SERVICE_KEY = originalKey;
  });

  it('calls the progress_ranking action and parses the wrapped response', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          student_id: 'stu-1',
          school_rank: 139,
          school_size: 743,
          branch_rank: 18,
          branch_size: 65,
        },
      }),
    );
    const rank = await getStudentRank('stu-1');
    const calledUrl = fetchSpy.mock.calls[0][0] as string;
    expect(calledUrl).toContain('action=progress_ranking');
    expect(calledUrl).not.toContain('action=ranking&');
    expect(rank).toEqual({
      school_rank: 139,
      school_size: 743,
      branch_rank: 18,
      branch_size: 65,
    });
  });

  it('returns all-null when the student is not in the active list', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({
        success: true,
        data: {
          student_id: 'stu-x',
          school_rank: null,
          school_size: 743,
          branch_rank: null,
          branch_size: null,
        },
      }),
    );
    const rank = await getStudentRank('stu-x');
    expect(rank.school_rank).toBeNull();
    expect(rank.branch_rank).toBeNull();
    expect(rank.school_size).toBe(743);
  });
});
