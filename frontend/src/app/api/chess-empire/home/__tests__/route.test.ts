/**
 * Tests for GET /api/chess-empire/home.
 *
 * Covers: off-tenant host (400), unauthenticated (401), the pending-cookie
 * auto-claim running first, lookup failure (500), and the trimmed JSON. The
 * loader itself is covered in lib/__tests__/empire-home-data.test.ts; here it
 * is mocked while the real `toEmpireHomeJson` trim runs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const headerStore: { current: Record<string, string | null> } = {
  current: { 'x-org-id': 'org-ce', 'x-org-slug': 'chess-empire' },
};
vi.mock('next/headers', () => ({
  headers: async () => ({
    get: (key: string) => headerStore.current[key] ?? null,
  }),
}));

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

const autoClaim = vi.fn(async () => false);
vi.mock('@/lib/pending-registration', () => ({
  autoClaimPendingCookie: (...a: unknown[]) => autoClaim(...(a as [])),
}));

const loadStore: { result: unknown; throws: boolean } = {
  result: { kind: 'no_link' },
  throws: false,
};
const loadEmpireHomeData = vi.fn(async () => {
  if (loadStore.throws) throw new Error('db down');
  return loadStore.result;
});
vi.mock('@/lib/empire-home-data', async () => {
  const actual = await vi.importActual<typeof import('@/lib/empire-home-data')>(
    '@/lib/empire-home-data',
  );
  return {
    ...actual,
    loadEmpireHomeData: (...a: unknown[]) => loadEmpireHomeData(...(a as [])),
  };
});

// The real module's own imports are never called once the loader is mocked,
// but they must be importable.
vi.mock('@/lib/chess-empire-member', () => ({ getMembershipState: vi.fn() }));
vi.mock('@/lib/chess-empire-client', () => ({}));
vi.mock('@/lib/gamification/store', () => ({ loadGamificationProfile: vi.fn() }));
vi.mock('@/lib/gamification/standings-store', () => ({ buildCurrentStandings: vi.fn() }));

import { GET } from '../route';

beforeEach(() => {
  headerStore.current = { 'x-org-id': 'org-ce', 'x-org-slug': 'chess-empire' };
  authStore.userId = 'user-1';
  loadStore.result = { kind: 'no_link' };
  loadStore.throws = false;
  vi.clearAllMocks();
});

describe('GET /api/chess-empire/home', () => {
  it('400 off the chess-empire host', async () => {
    headerStore.current = { 'x-org-id': 'org-2', 'x-org-slug': 'other-school' };
    const res = await GET();
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'not_ce_host' });
    expect(loadEmpireHomeData).not.toHaveBeenCalled();
  });

  it('400 on the apex host (no org headers)', async () => {
    headerStore.current = {};
    expect((await GET()).status).toBe(400);
  });

  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await GET();
    expect(res.status).toBe(401);
    expect(loadEmpireHomeData).not.toHaveBeenCalled();
  });

  it('auto-claims the pending cookie before loading', async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(autoClaim).toHaveBeenCalledWith('user-1');
    expect(loadEmpireHomeData).toHaveBeenCalledWith('org-ce', 'user-1');
    expect(await res.json()).toEqual({ kind: 'no_link' });
  });

  it('still loads when the auto-claim throws', async () => {
    autoClaim.mockRejectedValueOnce(new Error('cookie'));
    const res = await GET();
    expect(res.status).toBe(200);
  });

  it('500 lookup_error when the loader throws', async () => {
    loadStore.throws = true;
    const res = await GET();
    expect(res.status).toBe(500);
    expect(await res.json()).toEqual({ error: 'lookup_error' });
  });

  it('returns the trimmed student payload', async () => {
    loadStore.result = {
      kind: 'student',
      studentDisplayName: 'Ali',
      profile: {
        id: 'stu-1',
        first_name: 'Ali',
        last_name: 'Khan',
        branch_id: 'b1',
        status: 'active',
        date_of_birth: '2015-03-04',
        coach_id: 'coach-1',
        current_level: 3,
      },
      ratings: [],
      rank: { branch_rank: null, school_rank: null, branch_size: null, school_size: null },
      bestSurvivalScore: null,
      bestDefeatedBot: null,
      gamification: null,
      achievements: [],
      legionStanding: null,
      topNProximity: null,
      topN: 5,
    };
    const res = await GET();
    const json = await res.json();
    expect(json.kind).toBe('student');
    expect(json.profile.current_level).toBe(3);
    expect(json.profile).not.toHaveProperty('date_of_birth');
    expect(json.profile).not.toHaveProperty('status');
    expect(json.profile).not.toHaveProperty('branch_id');
    expect(json.profile).not.toHaveProperty('coach_id');
    expect(json.profile).not.toHaveProperty('id');
  });
});
