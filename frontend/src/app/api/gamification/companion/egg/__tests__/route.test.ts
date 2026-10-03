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
  chooseEgg: vi.fn(),
}));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg, chooseEgg } from '@/lib/companion/service';

const mock = (fn: unknown) => fn as unknown as { mockResolvedValue: (v: unknown) => void };

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('POST /api/gamification/companion/egg', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch flag is off', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    const res = await POST(req({ species: 'fox' }));
    expect(res.status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    const res = await POST(req({ species: 'fox' }));
    expect(res.status).toBe(403);
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { POST } = await import('../route');
    const res = await POST(req({ species: 'fox' }));
    expect(res.status).toBe(404);
    expect(chooseEgg).not.toHaveBeenCalled();
  });

  it('400 when species is missing', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    expect(chooseEgg).not.toHaveBeenCalled();
  });

  it('400 for an invalid species (service rejects)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(chooseEgg).mockResolvedValue({ status: 'invalid_species' });
    const { POST } = await import('../route');
    const res = await POST(req({ species: 'unicorn' }));
    expect(res.status).toBe(400);
  });

  it('200 and persists the chosen egg', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(chooseEgg).mockResolvedValue({
      status: 'ok',
      companion: { species: 'owl', name: null, stage: 'egg', hatched_at: null },
    });
    const { POST } = await import('../route');
    const res = await POST(req({ species: 'owl' }));
    expect(res.status).toBe(200);
    expect((await res.json()).companion.species).toBe('owl');
    expect(chooseEgg).toHaveBeenCalledWith('user_1', 'owl');
  });

  it('409 when the egg has already hatched (no re-pick)', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(chooseEgg).mockResolvedValue({ status: 'already_hatched' });
    const { POST } = await import('../route');
    const res = await POST(req({ species: 'fox' }));
    expect(res.status).toBe(409);
  });
});
