import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/goal-service', () => ({ loadGoal: vi.fn(), setGoalTarget: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadGoal, setGoalTarget } from '@/lib/companion/goal-service';

const mock = (fn: unknown) =>
  fn as unknown as { mockResolvedValue: (v: unknown) => void; mock: { calls: unknown[][] } };

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}
const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };
const GOAL = { target: 3, progress: 1, met: false, week_start: 'w', week_end: 'w2' };

describe('GET /api/gamification/companion/goal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { GET } = await import('../route');
    expect((await GET()).status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { GET } = await import('../route');
    expect((await GET()).status).toBe(403);
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { GET } = await import('../route');
    expect((await GET()).status).toBe(404);
    expect(loadGoal).not.toHaveBeenCalled();
  });

  it('200 returns target + current-week progress (no PII)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(loadGoal).mockResolvedValue(GOAL);
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ target: 3, progress: 1, met: false });
    expect(JSON.stringify(body)).not.toContain('solution');
    expect(mock(loadGoal).mock.calls[0][0]).toBe('user_1');
  });
});

describe('PATCH /api/gamification/companion/goal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { PATCH } = await import('../route');
    expect((await PATCH(req({ target: 4 }))).status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { PATCH } = await import('../route');
    expect((await PATCH(req({ target: 4 }))).status).toBe(403);
  });

  it('400 when the target is out of bounds', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(setGoalTarget).mockResolvedValue({ status: 'invalid_target' });
    const { PATCH } = await import('../route');
    const res = await PATCH(req({ target: 99 }));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_target');
  });

  it('200 returns the refreshed goal after a valid update', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(setGoalTarget).mockResolvedValue({ status: 'ok', goal: { ...GOAL, target: 5 } });
    const { PATCH } = await import('../route');
    const res = await PATCH(req({ target: 5 }));
    expect(res.status).toBe(200);
    expect((await res.json()).target).toBe(5);
    expect(mock(setGoalTarget).mock.calls[0]).toEqual(['user_1', 5]);
  });
});
