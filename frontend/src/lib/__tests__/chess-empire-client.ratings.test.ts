/**
 * Tests for the Phase 3 chess-empire-client additions: getStudentRatings,
 * getStudentAchievements, getStudentRank. Mocks global fetch and verifies
 * URL shape, envelope unwrapping, and the soft-fallback behaviour for rank.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  getStudentRatings,
  getStudentAchievements,
  getStudentRank,
  ChessEmpireAPIError,
} from '../chess-empire-client';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

describe('chess-empire-client (Phase 3)', () => {
  const originalKey = process.env.CHESS_EMPIRE_SERVICE_KEY;
  const originalUrl = process.env.CHESS_EMPIRE_SUPABASE_URL;
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  beforeEach(() => {
    process.env.CHESS_EMPIRE_SERVICE_KEY = 'ce-test-key';
    process.env.CHESS_EMPIRE_SUPABASE_URL = 'https://ce.example.com';
    fetchSpy.mockReset();
  });
  afterEach(() => {
    if (originalKey === undefined) delete process.env.CHESS_EMPIRE_SERVICE_KEY;
    else process.env.CHESS_EMPIRE_SERVICE_KEY = originalKey;
    if (originalUrl === undefined) delete process.env.CHESS_EMPIRE_SUPABASE_URL;
    else process.env.CHESS_EMPIRE_SUPABASE_URL = originalUrl;
  });

  describe('getStudentRatings', () => {
    it('hits analytics-students with Bearer auth and unwraps {data: [...]} + maps rating_date→date', async () => {
      const apiRows = [
        { id: 'r1', student_id: 'stu-1', rating: 1200, rating_date: '2026-05-01', source: 'tournament' },
        { id: 'r2', student_id: 'stu-1', rating: 1230, rating_date: '2026-05-15', source: 'csv_import' },
      ];
      fetchSpy.mockResolvedValue(jsonResponse({ success: true, data: apiRows, count: 2, trend: null }));
      const result = await getStudentRatings('stu-1', 14);
      expect(result).toEqual([
        { date: '2026-05-01', rating: 1200, source: 'tournament' },
        { date: '2026-05-15', rating: 1230, source: 'csv_import' },
      ]);
      const [url, init] = fetchSpy.mock.calls[0]!;
      const urlStr = String(url);
      expect(urlStr).toContain('/functions/v1/analytics-students');
      expect(urlStr).toContain('action=ratings');
      expect(urlStr).toContain('student_id=stu-1');
      expect(urlStr).toContain('days=14');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer ce-test-key');
      expect(headers['x-api-key']).toBeUndefined();
    });

    it('accepts a flat array response (forward-compat)', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([{ rating_date: '2026-05-01', rating: 1100 }]));
      const result = await getStudentRatings('stu-1');
      expect(result).toEqual([{ date: '2026-05-01', rating: 1100, source: undefined }]);
    });

    it('defaults to 30 days when not specified', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ success: true, data: [] }));
      await getStudentRatings('stu-1');
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('days=30');
    });

    it('returns empty array on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const result = await getStudentRatings('missing');
      expect(result).toEqual([]);
    });

    it('returns empty array for unknown shape', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ weird: 'shape' }));
      const result = await getStudentRatings('stu-1');
      expect(result).toEqual([]);
    });

    it('throws on timeout', async () => {
      fetchSpy.mockImplementation(async (_url, init?: RequestInit) => {
        await new Promise((_, reject) => {
          init?.signal?.addEventListener('abort', () => {
            const err = new Error('aborted');
            err.name = 'AbortError';
            reject(err);
          });
        });
        return new Response();
      });
      await expect(getStudentRatings('stu-1')).rejects.toBeInstanceOf(
        ChessEmpireAPIError,
      );
    }, 15000);

    it('throws on non-2xx, non-404 errors', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ error: 'boom' }, { status: 500 }));
      await expect(getStudentRatings('stu-1')).rejects.toBeInstanceOf(
        ChessEmpireAPIError,
      );
    });
  });

  describe('getStudentAchievements', () => {
    it('hits analytics-students achievements action with Bearer and unwraps {data:[...]}', async () => {
      const achievements = [
        { name: 'Bot Slayer', description: 'Completed first bot battle' },
      ];
      fetchSpy.mockResolvedValue(jsonResponse({ success: true, data: achievements, count: 1 }));
      const result = await getStudentAchievements('stu-1');
      expect(result).toEqual(achievements);
      const [url, init] = fetchSpy.mock.calls[0]!;
      const urlStr = String(url);
      expect(urlStr).toContain('action=achievements');
      expect(urlStr).toContain('student_id=stu-1');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer ce-test-key');
      expect(headers['x-api-key']).toBeUndefined();
    });

    it('accepts a flat array response', async () => {
      const achievements = [{ id: 'ach-1', name: 'First win', earned_at: '2026-04-01' }];
      fetchSpy.mockResolvedValue(jsonResponse(achievements));
      const result = await getStudentAchievements('stu-1');
      expect(result).toEqual(achievements);
    });

    it('returns empty array on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const result = await getStudentAchievements('missing');
      expect(result).toEqual([]);
    });

    it('throws on 500', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 500 }));
      await expect(getStudentAchievements('stu-1')).rejects.toBeInstanceOf(
        ChessEmpireAPIError,
      );
    });
  });

  describe('getStudentRank', () => {
    it('returns all-null on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const result = await getStudentRank('stu-1');
      expect(result).toEqual({
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      });
    });

    it('returns all-null when fetch throws (network error / timeout)', async () => {
      fetchSpy.mockRejectedValue(new Error('network down'));
      const result = await getStudentRank('stu-1');
      expect(result).toEqual({
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      });
    });

    it('returns all-null on unknown shape', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ totally: 'unexpected' }));
      const result = await getStudentRank('stu-1');
      expect(result).toEqual({
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      });
    });

    it('parses flat shape', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse({
          branch_rank: 4,
          school_rank: 42,
          branch_size: 50,
          school_size: 500,
        }),
      );
      const result = await getStudentRank('stu-1');
      expect(result).toEqual({
        branch_rank: 4,
        school_rank: 42,
        branch_size: 50,
        school_size: 500,
      });
    });

    it('parses {rank: {...}} envelope', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse({
          rank: { branch_rank: 1, school_rank: 7, branch_size: 30, school_size: 700 },
        }),
      );
      const result = await getStudentRank('stu-1');
      expect(result.branch_rank).toBe(1);
      expect(result.school_rank).toBe(7);
      expect(result.school_size).toBe(700);
    });

    it('parses {success, data: {...}} envelope (CE canonical)', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse({
          success: true,
          data: { branch_rank: 2, school_rank: 15, branch_size: 40, school_size: 800 },
        }),
      );
      const result = await getStudentRank('stu-1');
      expect(result.branch_rank).toBe(2);
      expect(result.school_rank).toBe(15);
      expect(result.branch_size).toBe(40);
      expect(result.school_size).toBe(800);
    });

    it('hits the ranking action (not rank) with Bearer auth', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ success: true, data: {} }));
      await getStudentRank('stu-1');
      const [url, init] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('action=ranking');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer ce-test-key');
      expect(headers['x-api-key']).toBeUndefined();
    });

    it('coerces non-numeric fields to null', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse({ branch_rank: '4', school_rank: 12, branch_size: null }),
      );
      const result = await getStudentRank('stu-1');
      expect(result.branch_rank).toBeNull();
      expect(result.school_rank).toBe(12);
      expect(result.branch_size).toBeNull();
    });
  });
});
