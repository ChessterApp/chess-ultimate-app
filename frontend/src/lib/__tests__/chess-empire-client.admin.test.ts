/**
 * Phase 4 — tests for the admin-side CE client helpers
 * (listBranches, listCoaches, listActiveStudentsByBranch). Verifies happy
 * path, 404 → [], and unknown shape → [] + single warning.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  listBranches,
  listCoaches,
  listActiveStudentsByBranch,
  listActiveStudentsByCoach,
} from '../chess-empire-client';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

describe('chess-empire-client admin helpers', () => {
  const originalKey = process.env.CHESS_EMPIRE_SERVICE_KEY;
  const originalUrl = process.env.CHESS_EMPIRE_SUPABASE_URL;
  const fetchSpy = vi.spyOn(globalThis, 'fetch');
  const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

  beforeEach(() => {
    process.env.CHESS_EMPIRE_SERVICE_KEY = 'ce-test-key';
    process.env.CHESS_EMPIRE_SUPABASE_URL = 'https://ce.example.com';
    fetchSpy.mockReset();
    warnSpy.mockClear();
  });
  afterEach(() => {
    if (originalKey === undefined) delete process.env.CHESS_EMPIRE_SERVICE_KEY;
    else process.env.CHESS_EMPIRE_SERVICE_KEY = originalKey;
    if (originalUrl === undefined) delete process.env.CHESS_EMPIRE_SUPABASE_URL;
    else process.env.CHESS_EMPIRE_SUPABASE_URL = originalUrl;
  });

  describe('listBranches', () => {
    it('returns rows on happy path', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          { id: 'br-1', name: 'Debut' },
          { id: 'br-2', name: 'Astana' },
        ]),
      );
      const branches = await listBranches();
      expect(branches).toHaveLength(2);
      expect(branches[0]?.name).toBe('Debut');
      const [url, init] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('/rest/v1/branches');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers.apikey).toBe('ce-test-key');
    });

    it('returns [] on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const branches = await listBranches();
      expect(branches).toEqual([]);
    });

    it('returns [] + warns once on unexpected shape', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ wat: true }));
      const branches = await listBranches();
      expect(branches).toEqual([]);
      const prev = warnSpy.mock.calls.length;
      // Second call should not warn again (one-shot warning).
      const second = await listBranches();
      expect(second).toEqual([]);
      expect(warnSpy.mock.calls.length).toBe(prev);
    });

    it('returns [] when service key missing', async () => {
      delete process.env.CHESS_EMPIRE_SERVICE_KEY;
      const branches = await listBranches();
      expect(branches).toEqual([]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });

  describe('listCoaches', () => {
    it('returns rows on happy path with a derived full_name', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          { id: 'co-1', first_name: 'Yerkezhan', last_name: 'Toktarov', branch_id: 'br-1' },
        ]),
      );
      const coaches = await listCoaches();
      expect(coaches[0]?.first_name).toBe('Yerkezhan');
      expect(coaches[0]?.last_name).toBe('Toktarov');
      expect(coaches[0]?.full_name).toBe('Yerkezhan Toktarov');
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('/rest/v1/coaches');
      expect(String(url)).toContain('first_name');
      // The real CE table has no full_name column — must not be selected.
      expect(String(url)).not.toContain('full_name');
    });

    it('ignores legacy full_name-only rows (unexpected shape → [])', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([{ id: 'co-1', full_name: 'Legacy', branch_id: 'br-1' }]),
      );
      const coaches = await listCoaches();
      expect(coaches).toEqual([]);
    });

    it('returns [] on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const coaches = await listCoaches();
      expect(coaches).toEqual([]);
    });

    it('returns [] on unknown shape', async () => {
      fetchSpy.mockResolvedValue(jsonResponse('nope'));
      const coaches = await listCoaches();
      expect(coaches).toEqual([]);
    });
  });

  describe('listActiveStudentsByBranch', () => {
    it('queries CE REST with branch + status + select', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          {
            id: 'stu-1',
            first_name: 'A',
            last_name: 'B',
            status: 'active',
            branch_id: 'br-1',
          },
        ]),
      );
      const out = await listActiveStudentsByBranch('br-1');
      expect(out).toHaveLength(1);
      const [url] = fetchSpy.mock.calls[0]!;
      const s = String(url);
      expect(s).toContain('branch_id=eq.br-1');
      expect(s).toContain('status=eq.active');
      // razryad is a plain column; league is embedded from the
      // student_current_ratings source-of-truth table.
      expect(decodeURIComponent(s)).toContain(
        'student_current_ratings(league,league_tier)',
      );
      expect(decodeURIComponent(s)).not.toContain('current_razryad');
    });

    it('maps razryad + embedded league onto the CEActiveStudent shape', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          {
            id: 'stu-1',
            first_name: 'A',
            last_name: 'B',
            status: 'active',
            branch_id: 'br-1',
            razryad: '3rd',
            student_current_ratings: [
              { league: 'League A', league_tier: 'gold' },
            ],
          },
          {
            id: 'stu-2',
            first_name: 'C',
            last_name: 'D',
            status: 'active',
            branch_id: 'br-1',
            razryad: null,
            student_current_ratings: [],
          },
        ]),
      );
      const out = await listActiveStudentsByBranch('br-1');
      expect(out[0]?.current_razryad).toBe('3rd');
      expect(out[0]?.current_league).toBe('A');
      expect(out[1]?.current_razryad).toBeNull();
      expect(out[1]?.current_league).toBeNull();
    });

    it('returns [] for empty branchId without fetching', async () => {
      const out = await listActiveStudentsByBranch('');
      expect(out).toEqual([]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('returns [] on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const out = await listActiveStudentsByBranch('br-1');
      expect(out).toEqual([]);
    });

    it('filters out non-active rows defensively', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          { id: 'a', first_name: 'A', last_name: '', status: 'active', branch_id: 'br-1' },
          { id: 'b', first_name: 'B', last_name: '', status: 'left', branch_id: 'br-1' },
        ]),
      );
      const out = await listActiveStudentsByBranch('br-1');
      expect(out.map((r) => r.id)).toEqual(['a']);
    });

    it('returns [] on unknown shape', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ rows: [] }));
      const out = await listActiveStudentsByBranch('br-1');
      expect(out).toEqual([]);
    });
  });

  describe('listActiveStudentsByCoach', () => {
    it('queries CE REST scoped by coach_id + status + embedded league', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          {
            id: 'stu-1',
            first_name: 'A',
            last_name: 'B',
            status: 'active',
            branch_id: 'br-1',
            coach_id: 'co-1',
            razryad: '3rd',
            student_current_ratings: [
              { league: 'League A', league_tier: 'gold' },
            ],
          },
        ]),
      );
      const out = await listActiveStudentsByCoach('co-1');
      expect(out).toHaveLength(1);
      expect(out[0]?.current_razryad).toBe('3rd');
      expect(out[0]?.current_league).toBe('A');
      const [url] = fetchSpy.mock.calls[0]!;
      const s = String(url);
      expect(s).toContain('/rest/v1/students');
      expect(s).toContain('coach_id=eq.co-1');
      expect(s).toContain('status=eq.active');
      expect(s).not.toContain('branch_id=eq');
      expect(decodeURIComponent(s)).toContain(
        'student_current_ratings(league,league_tier)',
      );
    });

    it('returns [] for empty coachId without fetching', async () => {
      const out = await listActiveStudentsByCoach('');
      expect(out).toEqual([]);
      expect(fetchSpy).not.toHaveBeenCalled();
    });

    it('returns [] on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      const out = await listActiveStudentsByCoach('co-1');
      expect(out).toEqual([]);
    });

    it('returns [] on unknown shape', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ rows: [] }));
      const out = await listActiveStudentsByCoach('co-1');
      expect(out).toEqual([]);
    });

    it('filters out non-active rows defensively', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          { id: 'a', first_name: 'A', last_name: '', status: 'active', branch_id: 'br-1', coach_id: 'co-1' },
          { id: 'b', first_name: 'B', last_name: '', status: 'left', branch_id: 'br-1', coach_id: 'co-1' },
        ]),
      );
      const out = await listActiveStudentsByCoach('co-1');
      expect(out.map((r) => r.id)).toEqual(['a']);
    });
  });
});
