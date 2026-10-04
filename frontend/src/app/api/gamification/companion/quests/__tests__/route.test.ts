import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/quest-service', () => ({ loadQuests: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadQuests } from '@/lib/companion/quest-service';

const mock = (fn: unknown) =>
  fn as unknown as { mockResolvedValue: (v: unknown) => void; mock: { calls: unknown[][] } };

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };
const QUEST = {
  id: 'watchtower',
  version: 1,
  title: { en: 'The Watchtower Quest', ru: '', kk: '' },
  description: { en: 'Finish the chapter', ru: '', kk: '' },
  region: 'watchtower',
  state: 'available',
  objectives: { done: 2, total: 6, complete: false },
  reward_granted: false,
  xp: 0,
  coins: 0,
};

describe('GET /api/gamification/companion/quests', () => {
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
    expect(loadQuests).not.toHaveBeenCalled();
  });

  it('200 returns the quest strip with availability + progress, no solutions', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(loadQuests).mockResolvedValue([QUEST]);
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.count).toBe(1);
    expect(body.quests[0]).toMatchObject({ id: 'watchtower', state: 'available' });
    expect(body.quests[0].objectives).toMatchObject({ done: 2, total: 6 });
    expect(JSON.stringify(body)).not.toContain('solution');
    expect(mock(loadQuests).mock.calls[0]).toEqual(['user_1', 'org-1', 'stu-1']);
  });
});
