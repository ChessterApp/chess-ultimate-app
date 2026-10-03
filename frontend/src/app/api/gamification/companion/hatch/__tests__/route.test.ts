import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({
  isCompanionEnabledForOrg: vi.fn(),
  hatchCompanion: vi.fn(),
}));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg, hatchCompanion } from '@/lib/companion/service';

const mock = (fn: unknown) => fn as unknown as { mockResolvedValue: (v: unknown) => void };

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };
const HATCHED = {
  status: 'ok',
  companion: { species: 'fox', name: 'Rusty', stage: 'hatched', hatched_at: '2026-10-03T00:00:00Z' },
  reward_granted: true,
  xp: 50,
  coins: 20,
  starter_granted: true,
};

describe('POST /api/gamification/companion/hatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch flag is off (reveal path stays dark)', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    const res = await POST(req({ name: 'Rusty' }));
    expect(res.status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
    expect(hatchCompanion).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    const res = await POST(req({ name: 'Rusty' }));
    expect(res.status).toBe(403);
    expect(hatchCompanion).not.toHaveBeenCalled();
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { POST } = await import('../route');
    const res = await POST(req({ name: 'Rusty' }));
    expect(res.status).toBe(404);
    expect(hatchCompanion).not.toHaveBeenCalled();
  });

  it('400 when the name is missing / blank (server-side validation)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');
    const res = await POST(req({ name: '   ' }));
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_name');
    expect(hatchCompanion).not.toHaveBeenCalled();
  });

  it('200 on a successful hatch (reward + starter committed server-side)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(hatchCompanion).mockResolvedValue(HATCHED);
    const { POST } = await import('../route');
    const res = await POST(req({ name: '  Rusty  ' }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.companion.stage).toBe('hatched');
    expect(body.xp).toBe(50);
    expect(body.starter_granted).toBe(true);
    // Name is sanitized before reaching the service.
    expect(hatchCompanion).toHaveBeenCalledWith({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      name: 'Rusty',
    });
  });

  it('200 and no second hatch on a double-call (idempotent already_hatched)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    // First call hatches; a replayed call returns the SAME companion, grants nothing.
    (hatchCompanion as unknown as { mockResolvedValueOnce: (v: unknown) => void }).mockResolvedValueOnce(
      HATCHED,
    );
    (hatchCompanion as unknown as { mockResolvedValueOnce: (v: unknown) => void }).mockResolvedValueOnce({
      status: 'already_hatched',
      companion: HATCHED.companion,
      reward_granted: false,
      xp: 0,
      coins: 0,
      starter_granted: false,
    });
    const { POST } = await import('../route');

    const res1 = await POST(req({ name: 'Rusty' }));
    const res2 = await POST(req({ name: 'Rusty' }));
    expect(res1.status).toBe(200);
    expect(res2.status).toBe(200);
    expect((await res1.json()).reward_granted).toBe(true);
    const second = await res2.json();
    expect(second.status).toBe('already_hatched');
    expect(second.reward_granted).toBe(false); // exactly one hatch grant
    expect(second.xp).toBe(0);
  });

  it('409 when hatch readiness is not met (server re-checks evidence)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(hatchCompanion).mockResolvedValue({ status: 'not_ready', demonstrated: 7, required: 9 });
    const { POST } = await import('../route');
    const res = await POST(req({ name: 'Rusty' }));
    expect(res.status).toBe(409);
    expect((await res.json()).status).toBe('not_ready');
  });
});
