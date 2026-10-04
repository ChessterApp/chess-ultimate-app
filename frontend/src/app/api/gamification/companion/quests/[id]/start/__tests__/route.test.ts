import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/quest-service', () => ({ startQuest: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { startQuest } from '@/lib/companion/quest-service';

const mock = (fn: unknown) =>
  fn as unknown as { mockResolvedValue: (v: unknown) => void; mock: { calls: unknown[][] } };

const req = () => ({}) as unknown as import('next/server').NextRequest;
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });
const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

function questView(over: Record<string, unknown> = {}) {
  return {
    id: 'watchtower',
    version: 1,
    title: { en: 'The Watchtower Quest', ru: '', kk: '' },
    description: { en: '', ru: '', kk: '' },
    region: 'watchtower',
    state: 'active',
    objectives: { done: 0, total: 6, complete: false },
    reward_granted: false,
    xp: 0,
    coins: 0,
    ...over,
  };
}

describe('POST /api/gamification/companion/quests/:id/start', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    expect((await POST(req(), ctx('watchtower'))).status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    expect((await POST(req(), ctx('watchtower'))).status).toBe(403);
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { POST } = await import('../route');
    expect((await POST(req(), ctx('watchtower'))).status).toBe(404);
    expect(startQuest).not.toHaveBeenCalled();
  });

  it('404 for an unknown quest id', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(startQuest).mockResolvedValue({ status: 'not_found' });
    const { POST } = await import('../route');
    expect((await POST(req(), ctx('nope'))).status).toBe(404);
  });

  it('200 moves the quest to active, forwarding server identity', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(startQuest).mockResolvedValue({ status: 'ok', quest: questView({ state: 'active' }) });
    const { POST } = await import('../route');
    const res = await POST(req(), ctx('watchtower'));
    expect(res.status).toBe(200);
    expect((await res.json()).state).toBe('active');
    expect(mock(startQuest).mock.calls[0][0]).toMatchObject({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      questId: 'watchtower',
    });
  });

  it('grants the completion reward exactly once — a replay grants nothing', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');

    // First completion: reward granted.
    mock(startQuest).mockResolvedValue({
      status: 'ok',
      quest: questView({
        state: 'completed',
        objectives: { done: 6, total: 6, complete: true },
        reward_granted: true,
        xp: 50,
        coins: 20,
      }),
    });
    const first = await (await POST(req(), ctx('watchtower'))).json();
    expect(first.state).toBe('completed');
    expect(first.reward_granted).toBe(true);
    expect(first.xp).toBe(50);

    // Replay (idempotent): already completed, nothing re-granted.
    mock(startQuest).mockResolvedValue({
      status: 'ok',
      quest: questView({
        state: 'completed',
        objectives: { done: 6, total: 6, complete: true },
        reward_granted: false,
        xp: 0,
        coins: 0,
      }),
    });
    const second = await (await POST(req(), ctx('watchtower'))).json();
    expect(second.state).toBe('completed');
    expect(second.reward_granted).toBe(false);
    expect(second.xp).toBe(0);
  });
});
