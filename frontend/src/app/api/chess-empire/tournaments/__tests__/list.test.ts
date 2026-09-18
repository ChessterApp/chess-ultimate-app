/**
 * Tests for GET /api/chess-empire/tournaments.
 *
 * The route returns the shared schedule snapshot (branches + per-tournament
 * rosters + the viewer's own registration status). Covers: logged-out → no
 * registration status; verified member → registration status + roster merged
 * per tournament; schedule fetch failure → graceful empty (200).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: null };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

interface FakeMember {
  state: string;
  studentId: string | null;
  relationship: 'self' | 'child' | 'other';
}
const memberStore: { members: FakeMember[] } = {
  members: [{ state: 'verified', studentId: 'stu-1', relationship: 'self' }],
};
vi.mock('@/lib/chess-empire-member', () => ({
  // The snapshot now resolves the full verified allowlist (family multi-link).
  getVerifiedMembersForUser: vi.fn(async () => memberStore.members),
}));

const listMock = vi.fn();
const regsMock = vi.fn();
const rosterMock = vi.fn();
const branchesMock = vi.fn();
const nameMock = vi.fn();
vi.mock('@/lib/chess-empire-client', () => ({
  listTournaments: (...args: unknown[]) => listMock(...args),
  getStudentTournamentRegistrations: (...args: unknown[]) => regsMock(...args),
  getTournamentRoster: (...args: unknown[]) => rosterMock(...args),
  listBranches: (...args: unknown[]) => branchesMock(...args),
  getStudentDisplayName: (...args: unknown[]) => nameMock(...args),
}));

import { GET } from '../route';

beforeEach(() => {
  authStore.userId = null;
  memberStore.members = [
    { state: 'verified', studentId: 'stu-1', relationship: 'self' },
  ];
  listMock.mockReset();
  regsMock.mockReset();
  rosterMock.mockReset().mockResolvedValue([]);
  branchesMock.mockReset().mockResolvedValue([]);
  nameMock.mockReset().mockResolvedValue('Stu One');
});

describe('GET /api/chess-empire/tournaments', () => {
  it('logged out → list with membership logged_out, is_registered false', async () => {
    listMock.mockResolvedValue([{ id: 't1', name: 'Blitz' }]);
    const res = await GET();
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      membership: string;
      tournaments: Array<{ is_registered: boolean; registration_id: string | null }>;
    };
    expect(body.membership).toBe('logged_out');
    expect(body.tournaments[0].is_registered).toBe(false);
    expect(body.tournaments[0].registration_id).toBeNull();
    expect(regsMock).not.toHaveBeenCalled();
  });

  it('verified member → merges registration status + roster per tournament', async () => {
    authStore.userId = 'user-1';
    listMock.mockResolvedValue([
      { id: 't1', name: 'Blitz' },
      { id: 't2', name: 'Rapid' },
    ]);
    regsMock.mockResolvedValue([
      { id: 'reg-1', tournament_id: 't1', registered_at: 'x' },
    ]);
    rosterMock.mockImplementation(async (id: string) =>
      id === 't1' ? ['Aida Bekova', 'Stu One'] : [],
    );
    const res = await GET();
    const body = (await res.json()) as {
      membership: string;
      tournaments: Array<{
        id: string;
        is_registered: boolean;
        registration_id: string | null;
        roster: string[];
        registered_count: number;
      }>;
    };
    expect(body.membership).toBe('verified');
    expect(body.tournaments[0]).toMatchObject({
      id: 't1',
      is_registered: true,
      registration_id: 'reg-1',
    });
    expect(body.tournaments[0].roster).toEqual(['Aida Bekova', 'Stu One']);
    expect(body.tournaments[0].registered_count).toBe(2);
    expect(body.tournaments[1]).toMatchObject({
      id: 't2',
      is_registered: false,
      registration_id: null,
    });
  });

  it('gracefully returns an empty schedule (200) when the fetch fails', async () => {
    listMock.mockRejectedValue(new Error('down'));
    const res = await GET();
    expect(res.status).toBe(200);
    const body = (await res.json()) as { tournaments: unknown[] };
    expect(body.tournaments).toEqual([]);
  });
});
