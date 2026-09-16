import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/org-from-headers', () => ({ loadOrgFromHeaders: vi.fn() }));
vi.mock('@/lib/chess-empire-member', () => ({ getMembershipState: vi.fn() }));
vi.mock('@/lib/gamification/store', () => ({ loadGamificationProfile: vi.fn() }));

import { auth } from '@clerk/nextjs/server';
import { loadOrgFromHeaders } from '@/lib/org-from-headers';
import { getMembershipState } from '@/lib/chess-empire-member';
import { loadGamificationProfile } from '@/lib/gamification/store';

const mock = (fn: unknown) => fn as unknown as { mockResolvedValue: (v: unknown) => void; mockReturnValue: (v: unknown) => void };

describe('GET /api/gamification/profile', () => {
  beforeEach(() => vi.clearAllMocks());

  it('401 when not authenticated', async () => {
    mock(auth).mockResolvedValue({ userId: null });
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(401);
  });

  it('returns hidden/empty profile (200) when no org resolves on the host', async () => {
    // Plain chesster.io has no tenant org — must NOT 400 (spams the dashboard
    // console on every load); same hidden-profile semantics as an unlinked student.
    mock(auth).mockResolvedValue({ userId: 'user_1' });
    mock(loadOrgFromHeaders).mockResolvedValue(null);
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ linked: false });
    expect(getMembershipState).not.toHaveBeenCalled();
  });

  it('returns hidden/empty profile for an unlinked student (D-8)', async () => {
    mock(auth).mockResolvedValue({ userId: 'user_1' });
    mock(loadOrgFromHeaders).mockResolvedValue({ id: 'org-1' });
    mock(getMembershipState).mockResolvedValue({ state: 'no_link', studentId: null });
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ linked: false });
  });

  it('hides pending_confirm links too (not yet verified)', async () => {
    mock(auth).mockResolvedValue({ userId: 'user_1' });
    mock(loadOrgFromHeaders).mockResolvedValue({ id: 'org-1' });
    mock(getMembershipState).mockResolvedValue({ state: 'pending_confirm', studentId: 'stu-9' });
    const { GET } = await import('../route');
    const res = await GET();
    expect(await res.json()).toEqual({ linked: false });
  });

  it('returns the real profile for a verified linked student', async () => {
    mock(auth).mockResolvedValue({ userId: 'user_1' });
    mock(loadOrgFromHeaders).mockResolvedValue({ id: 'org-1' });
    mock(getMembershipState).mockResolvedValue({ state: 'verified', studentId: 'stu-1' });
    mock(loadGamificationProfile).mockResolvedValue({
      linked: true,
      student_id: 'stu-1',
      xp: 12,
      coins: 12,
      rank: { code: 'knight', name_ru: 'Конь', name_kk: 'Ат', name_en: 'Knight', icon_url: null },
      rank_progress: { pct: 20, xp_into_rank: 2, xp_for_next: 20, next_code: 'bishop', next_min_xp: 30 },
      streak: { current_weeks: 2, best_weeks: 3, last_active_week: '2026-01-12', next_milestone: { weeks: 3, reward: 3 } },
      stats: { tournaments_played: 4, wins_total: 6 },
    });
    const { GET } = await import('../route');
    const res = await GET();
    const body = await res.json();
    expect(body.linked).toBe(true);
    expect(body.xp).toBe(12);
    expect(body.rank.code).toBe('knight');
    expect(body.streak.current_weeks).toBe(2);
    expect(body.stats.tournaments_played).toBe(4);
    expect(loadGamificationProfile).toHaveBeenCalledWith('org-1', 'stu-1');
  });
});
