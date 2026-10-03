import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mutable flag the mocked feature-flags module reads through a getter, so a
// single file can exercise both flag-on and flag-off paths.
const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({
  isCompanionEnabledForOrg: vi.fn(),
  loadCompanionView: vi.fn(),
}));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg, loadCompanionView } from '@/lib/companion/service';

const mock = (fn: unknown) => fn as unknown as { mockResolvedValue: (v: unknown) => void };

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('GET /api/gamification/companion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch flag is off (feature stays dark)', async () => {
    flags.on = false;
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(403);
    expect(isCompanionEnabledForOrg).not.toHaveBeenCalled();
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(404);
    expect(loadCompanionView).not.toHaveBeenCalled();
  });

  it('200 with the companion view for a linked, enabled student', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(loadCompanionView).mockResolvedValue({
      companion: { species: 'fox', name: null, stage: 'egg', hatched_at: null },
      competencies: [{ code: 'H_ROOK', progress: 0, demonstrated: false }],
      hatch_ready: false,
      hatch_progress: 0,
    });
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.companion.species).toBe('fox');
    expect(body.hatch_ready).toBe(false);
    expect(loadCompanionView).toHaveBeenCalledWith('user_1');
  });
});
