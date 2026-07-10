/**
 * Tests for the coach-search CE client helpers added for coach registration:
 * searchCoachesByBranch (branch + name ILIKE, no status filter, derived
 * full_name) and getCoachProfile (single-row fetch, 404 on empty).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  searchCoachesByBranch,
  getCoachProfile,
  ChessEmpireAPIError,
} from '../chess-empire-client';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

describe('chess-empire-client coach helpers', () => {
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

  describe('searchCoachesByBranch', () => {
    it('queries the coaches table by branch + name with no status filter', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          { id: 'co-1', first_name: 'Anna', last_name: 'Petrova', branch_id: 'br-1' },
        ]),
      );
      const out = await searchCoachesByBranch('br-1', 'ann');
      expect(out).toEqual([
        {
          id: 'co-1',
          first_name: 'Anna',
          last_name: 'Petrova',
          full_name: 'Anna Petrova',
          branch_id: 'br-1',
        },
      ]);
      const [url] = fetchSpy.mock.calls[0]!;
      const s = String(url);
      expect(s).toContain('/rest/v1/coaches');
      expect(s).toContain('branch_id=eq.br-1');
      expect(s).not.toContain('status=');
      expect(s).toContain('first_name.ilike');
    });

    it('omits the name filter when the query is blank', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([]));
      await searchCoachesByBranch('br-1', '   ');
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).not.toContain('ilike');
    });

    it('throws ChessEmpireAPIError on non-2xx', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ msg: 'boom' }, { status: 500 }));
      await expect(searchCoachesByBranch('br-1', 'ann')).rejects.toBeInstanceOf(
        ChessEmpireAPIError,
      );
    });
  });

  describe('getCoachProfile', () => {
    it('returns the single coach row', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse([
          {
            id: 'co-1',
            first_name: 'Anna',
            last_name: 'Petrova',
            branch_id: 'br-1',
            email: 'anna@example.com',
            photo_url: 'https://cdn.example.com/anna.jpg',
            bio: 'FIDE master, 10 years coaching.',
          },
        ]),
      );
      const coach = await getCoachProfile('co-1');
      expect(coach.branch_id).toBe('br-1');
      expect(coach.first_name).toBe('Anna');
      expect(coach.email).toBe('anna@example.com');
      expect(coach.photo_url).toBe('https://cdn.example.com/anna.jpg');
      expect(coach.bio).toBe('FIDE master, 10 years coaching.');
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('id=eq.co-1');
      expect(String(url)).toContain('photo_url');
      expect(String(url)).toContain('bio');
    });

    it('throws a 404 ChessEmpireAPIError when no row is found', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([]));
      await expect(getCoachProfile('missing')).rejects.toMatchObject({
        statusCode: 404,
      });
    });
  });
});
