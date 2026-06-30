/**
 * Tests for chess-empire-client.ts — mock global fetch, verify request URLs,
 * headers, and error mapping.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  searchStudentsByBranch,
  getStudentProfile,
  getBranches,
  countActiveStudentsInBranch,
  ChessEmpireAPIError,
} from '../chess-empire-client';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

describe('chess-empire-client', () => {
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

  describe('searchStudentsByBranch', () => {
    it('hits REST students endpoint with branch + name filter + auth headers', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([{ id: 'stu-1', first_name: 'Aiman' }]));
      const result = await searchStudentsByBranch('br-1', 'aim', 5);
      expect(result).toEqual([{ id: 'stu-1', first_name: 'Aiman' }]);
      expect(fetchSpy).toHaveBeenCalledOnce();
      const [url, init] = fetchSpy.mock.calls[0]!;
      const urlStr = String(url);
      expect(urlStr).toContain('https://ce.example.com/rest/v1/students');
      expect(urlStr).toContain('branch_id=eq.br-1');
      expect(urlStr).toContain('status=eq.active');
      expect(urlStr).toContain('first_name.ilike.*aim*');
      expect(urlStr).toContain('limit=5');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers.apikey).toBe('ce-test-key');
      expect(headers.Authorization).toBe('Bearer ce-test-key');
    });

    it('omits the or= filter when query is empty', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([]));
      await searchStudentsByBranch('br-1', '   ');
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).not.toContain('or=');
    });

    it('throws ChessEmpireAPIError on 4xx', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ message: 'bad' }, { status: 400 }));
      await expect(searchStudentsByBranch('br-1', 'q')).rejects.toBeInstanceOf(
        ChessEmpireAPIError,
      );
    });

    it('throws when service key missing', async () => {
      delete process.env.CHESS_EMPIRE_SERVICE_KEY;
      await expect(searchStudentsByBranch('br-1', 'q')).rejects.toBeInstanceOf(
        ChessEmpireAPIError,
      );
    });

    it('clamps absurd limits to 50', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([]));
      await searchStudentsByBranch('br-1', 'q', 999);
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('limit=50');
    });
  });

  describe('getStudentProfile', () => {
    it('hits analytics-students with x-api-key', async () => {
      fetchSpy.mockResolvedValue(
        jsonResponse({ profile: { id: 'stu-1', first_name: 'A', last_name: 'B', status: 'active' } }),
      );
      const profile = await getStudentProfile('stu-1');
      expect(profile.id).toBe('stu-1');
      const [url, init] = fetchSpy.mock.calls[0]!;
      const urlStr = String(url);
      expect(urlStr).toContain('/functions/v1/analytics-students?action=profile&student_id=stu-1');
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers['x-api-key']).toBe('ce-test-key');
    });

    it('unwraps the profile envelope', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ profile: { id: 'stu-1' } }));
      const profile = await getStudentProfile('stu-1');
      expect(profile.id).toBe('stu-1');
    });

    it('accepts a flat profile response (forward-compat)', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({ id: 'stu-1', first_name: 'A' }));
      const profile = await getStudentProfile('stu-1');
      expect(profile.id).toBe('stu-1');
    });

    it('throws ChessEmpireAPIError on 404', async () => {
      fetchSpy.mockResolvedValue(jsonResponse({}, { status: 404 }));
      await expect(getStudentProfile('missing')).rejects.toBeInstanceOf(ChessEmpireAPIError);
    });
  });

  describe('getBranches', () => {
    it('hits REST branches endpoint with select + order', async () => {
      fetchSpy.mockResolvedValue(jsonResponse([{ id: 'br-1', name: 'Debut' }]));
      const branches = await getBranches();
      expect(branches[0]?.name).toBe('Debut');
      const [url] = fetchSpy.mock.calls[0]!;
      expect(String(url)).toContain('/rest/v1/branches');
      expect(String(url)).toContain('order=name.asc');
    });
  });

  describe('countActiveStudentsInBranch', () => {
    it('reads count from content-range header', async () => {
      fetchSpy.mockResolvedValue(
        new Response(JSON.stringify([{ id: 'x' }]), {
          status: 206,
          headers: { 'content-range': '0-0/262', 'content-type': 'application/json' },
        }),
      );
      const count = await countActiveStudentsInBranch('br-1');
      expect(count).toBe(262);
    });

    it('falls back to row count when content-range is *', async () => {
      fetchSpy.mockResolvedValue(
        new Response(JSON.stringify([{ id: 'x' }]), {
          status: 200,
          headers: { 'content-range': '0-0/*', 'content-type': 'application/json' },
        }),
      );
      const count = await countActiveStudentsInBranch('br-1');
      expect(count).toBe(1);
    });
  });
});
