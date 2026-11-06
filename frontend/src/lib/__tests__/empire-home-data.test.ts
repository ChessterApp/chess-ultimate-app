/**
 * Tests for loadEmpireHomeData — the CE homepage decision tree shared by
 * renderEmpireHomepage and GET /api/chess-empire/home — and toEmpireHomeJson,
 * the trim applied before the data leaves the server as JSON.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const memberStore: {
  state: string;
  role: string;
  studentId: string | null;
  source: string;
  throws: boolean;
} = {
  state: 'verified',
  role: 'student',
  studentId: 'stu-1',
  source: 'chess_empire',
  throws: false,
};
vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipState: vi.fn(async () => {
    if (memberStore.throws) throw new Error('db down');
    return {
      state: memberStore.state,
      role: memberStore.role,
      studentId: memberStore.studentId,
      memberId: memberStore.studentId ? 'mem-1' : null,
      source: memberStore.source,
    };
  }),
}));

const fullProfile = {
  id: 'stu-1',
  first_name: 'Ali',
  last_name: 'Khan',
  branch_id: 'b1',
  status: 'active',
  date_of_birth: '2015-03-04',
  coach_id: 'coach-1',
  photo_url: null,
  coach_name: 'Aigerim Nur',
  branch_name: 'Debut',
  current_level: 3,
  current_lesson: 40,
  total_lessons: 120,
  current_rating: 1210,
  razryad: '3rd',
  current_league: 'B',
  league_tier: 'B2',
  joined_at: '2024-09-01',
  best_survival_score: 17,
  best_defeated_bot: { name: 'Bot 1200', rating: 1200 },
};

const getStudentProfile = vi.fn(async () => fullProfile);
const getCoachProfile = vi.fn(async () => ({
  id: 'coach-1',
  first_name: 'Aigerim',
  last_name: 'Nur',
  branch_id: 'b1',
  email: 'coach@example.com',
  photo_url: 'https://img/c.png',
  bio: 'Bio',
}));
const listBranches = vi.fn(async () => [{ id: 'b1', name: 'Debut Branch' }]);
const listActiveStudentsByCoach = vi.fn(async () => [
  {
    id: 'stu-1',
    first_name: 'A',
    last_name: 'B',
    date_of_birth: '2015-01-01',
    status: 'active',
    branch_id: 'b1',
    coach_id: 'coach-1',
    current_razryad: '3rd',
    current_league: 'A',
  },
]);
const getStudentRatings = vi.fn(async () => [{ date: '2026-10-01', rating: 1200 }]);
const getStudentRank = vi.fn(async () => ({
  branch_rank: 2,
  school_rank: 10,
  branch_size: 30,
  school_size: 300,
}));
const getStudentAchievements = vi.fn(async () => []);
vi.mock('@/lib/chess-empire-client', () => ({
  getStudentProfile: (...a: unknown[]) => getStudentProfile(...(a as [])),
  getCoachProfile: (...a: unknown[]) => getCoachProfile(...(a as [])),
  listBranches: (...a: unknown[]) => listBranches(...(a as [])),
  listActiveStudentsByCoach: (...a: unknown[]) => listActiveStudentsByCoach(...(a as [])),
  getStudentRatings: (...a: unknown[]) => getStudentRatings(...(a as [])),
  getStudentRank: (...a: unknown[]) => getStudentRank(...(a as [])),
  getStudentAchievements: (...a: unknown[]) => getStudentAchievements(...(a as [])),
}));

vi.mock('@/lib/gamification/store', () => ({
  loadGamificationProfile: vi.fn(async () => null),
}));

const standingsStore: { current: unknown } = { current: null };
vi.mock('@/lib/gamification/standings-store', () => ({
  buildCurrentStandings: vi.fn(async () => standingsStore.current),
}));

import { loadEmpireHomeData, toEmpireHomeJson } from '../empire-home-data';

beforeEach(() => {
  memberStore.state = 'verified';
  memberStore.role = 'student';
  memberStore.studentId = 'stu-1';
  memberStore.source = 'chess_empire';
  memberStore.throws = false;
  standingsStore.current = null;
  vi.clearAllMocks();
});

describe('loadEmpireHomeData — membership branches', () => {
  it.each([
    ['no_link', 'no_link'],
    ['frozen', 'frozen'],
    ['expired', 'expired'],
  ])('state %s → kind %s without any CE fetch', async (state, kind) => {
    memberStore.state = state;
    const data = await loadEmpireHomeData('org-1', 'user-1');
    expect(data).toEqual({ kind });
    expect(getStudentProfile).not.toHaveBeenCalled();
    expect(getCoachProfile).not.toHaveBeenCalled();
  });

  it('online-track member → kind online', async () => {
    memberStore.source = 'online';
    expect(await loadEmpireHomeData('org-1', 'user-1')).toEqual({ kind: 'online' });
    expect(getStudentProfile).not.toHaveBeenCalled();
  });

  it('rethrows the membership lookup error', async () => {
    memberStore.throws = true;
    await expect(loadEmpireHomeData('org-1', 'user-1')).rejects.toThrow('db down');
  });

  it('throws when a verified row has no studentId', async () => {
    memberStore.studentId = null;
    await expect(loadEmpireHomeData('org-1', 'user-1')).rejects.toThrow(/no studentId/);
  });

  it('rethrows a student profile failure', async () => {
    getStudentProfile.mockRejectedValueOnce(new Error('profile 500'));
    await expect(loadEmpireHomeData('org-1', 'user-1')).rejects.toThrow('profile 500');
  });

  it('pending_confirm student → name only, no secondary fetches', async () => {
    memberStore.state = 'pending_confirm';
    const data = await loadEmpireHomeData('org-1', 'user-1');
    expect(data).toEqual({ kind: 'pending_confirm', studentDisplayName: 'Ali' });
    expect(getStudentRatings).not.toHaveBeenCalled();
  });
});

describe('loadEmpireHomeData — coach', () => {
  beforeEach(() => {
    memberStore.role = 'coach';
    memberStore.studentId = 'coach-1';
  });

  it('builds the coach home with branch name and stats', async () => {
    const data = await loadEmpireHomeData('org-1', 'user-1');
    expect(data.kind).toBe('coach');
    if (data.kind !== 'coach' || !data.coach) throw new Error('expected coach');
    expect(data.coach.displayName).toBe('Aigerim Nur');
    expect(data.coach.branchName).toBe('Debut Branch');
    expect(data.coach.stats).toEqual({
      total: 1,
      withRazryad: 1,
      leagueBreakdown: [{ league: 'A', count: 1 }],
    });
    expect(getStudentProfile).not.toHaveBeenCalled();
  });

  it('a pending coach still gets the coach home (role checked first)', async () => {
    memberStore.state = 'pending_confirm';
    const data = await loadEmpireHomeData('org-1', 'user-1');
    expect(data.kind).toBe('coach');
  });

  it('coach profile failure → coach: null', async () => {
    getCoachProfile.mockRejectedValueOnce(new Error('404'));
    expect(await loadEmpireHomeData('org-1', 'user-1')).toEqual({ kind: 'coach', coach: null });
  });

  it('branch and roster failures degrade to empty', async () => {
    listBranches.mockRejectedValueOnce(new Error('x'));
    listActiveStudentsByCoach.mockRejectedValueOnce(new Error('y'));
    const data = await loadEmpireHomeData('org-1', 'user-1');
    if (data.kind !== 'coach' || !data.coach) throw new Error('expected coach');
    expect(data.coach.branchName).toBeNull();
    expect(data.coach.roster).toEqual([]);
    expect(data.coach.stats.total).toBe(0);
  });
});

describe('loadEmpireHomeData — verified student', () => {
  it('loads the full student home with best-effort fallbacks', async () => {
    getStudentRank.mockRejectedValueOnce(new Error('rank down'));
    const data = await loadEmpireHomeData('org-1', 'user-1');
    if (data.kind !== 'student') throw new Error('expected student');
    expect(data.studentDisplayName).toBe('Ali');
    expect(data.ratings).toHaveLength(1);
    expect(data.rank).toEqual({
      branch_rank: null,
      school_rank: null,
      branch_size: null,
      school_size: null,
    });
    expect(data.bestSurvivalScore).toBe(17);
    expect(data.bestDefeatedBot).toEqual({ name: 'Bot 1200', rating: 1200 });
    expect(data.legionStanding).toBeNull();
    expect(data.topNProximity).toBeNull();
    expect(data.topN).toBe(5);
    expect(getStudentRatings).toHaveBeenCalledWith('stu-1', 30);
  });
});

describe('toEmpireHomeJson', () => {
  it('drops date_of_birth, status and internal ids from the student profile', async () => {
    const json = toEmpireHomeJson(await loadEmpireHomeData('org-1', 'user-1')) as {
      kind: string;
      profile: Record<string, unknown>;
    };
    expect(json.kind).toBe('student');
    expect(json.profile).toEqual({
      first_name: 'Ali',
      last_name: 'Khan',
      photo_url: null,
      branch_name: 'Debut',
      coach_name: 'Aigerim Nur',
      current_level: 3,
      current_lesson: 40,
      total_lessons: 120,
      current_rating: 1210,
      razryad: '3rd',
      current_league: 'B',
      league_tier: 'B2',
      joined_at: '2024-09-01',
    });
    const text = JSON.stringify(json);
    expect(text).not.toContain('2015-03-04');
    expect(text).not.toContain('coach-1');
  });

  it('strips roster rows to id, names, razryad and league, and never leaks e-mail', async () => {
    memberStore.role = 'coach';
    memberStore.studentId = 'coach-1';
    const json = toEmpireHomeJson(await loadEmpireHomeData('org-1', 'user-1')) as {
      coach: { roster: unknown[] };
    };
    expect(json.coach.roster).toEqual([
      { id: 'stu-1', first_name: 'A', last_name: 'B', current_razryad: '3rd', current_league: 'A' },
    ]);
    const text = JSON.stringify(json);
    expect(text).not.toContain('coach@example.com');
    expect(text).not.toContain('2015-01-01');
  });

  it('passes simple kinds through unchanged', () => {
    expect(toEmpireHomeJson({ kind: 'frozen' })).toEqual({ kind: 'frozen' });
    expect(toEmpireHomeJson({ kind: 'coach', coach: null })).toEqual({ kind: 'coach', coach: null });
  });
});
