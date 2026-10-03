import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/assessment-service', () => ({ logHint: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { logHint } from '@/lib/companion/assessment-service';

const mock = (fn: unknown) => fn as unknown as {
  mockResolvedValue: (v: unknown) => void;
  mock: { calls: unknown[][] };
};

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('POST /api/gamification/companion/hints', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    const res = await POST(req({ assignment_id: 'a', hint_index: 0 }));
    expect(res.status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    expect((await POST(req({ assignment_id: 'a' }))).status).toBe(403);
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { POST } = await import('../route');
    expect((await POST(req({ assignment_id: 'a' }))).status).toBe(404);
    expect(logHint).not.toHaveBeenCalled();
  });

  it('400 when assignment_id is missing', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');
    expect((await POST(req({}))).status).toBe(400);
    expect(logHint).not.toHaveBeenCalled();
  });

  it('404 when the assignment is unknown / not owned', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(logHint).mockResolvedValue({ status: 'not_found' });
    const { POST } = await import('../route');
    expect((await POST(req({ assignment_id: 'x' }))).status).toBe(404);
  });

  it('200 reveals the hint and reports assistance was logged', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(logHint).mockResolvedValue({
      status: 'ok',
      assistance_used: true,
      hint_index: 0,
      hints_total: 2,
      hint: { en: 'Rooks slide in straight lines.', ru: 'x', kk: 'y' },
    });
    const { POST } = await import('../route');
    const res = await POST(req({ assignment_id: 'asg-1', hint_index: 0 }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.assistance_used).toBe(true);
    expect(body.hint.en).toContain('Rooks');
    expect(mock(logHint).mock.calls[0]).toEqual(['user_1', 'asg-1', 0]);
  });

  it('defaults hint_index to 0 when omitted', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(logHint).mockResolvedValue({ status: 'ok', assistance_used: true, hint_index: 0, hints_total: 1, hint: null });
    const { POST } = await import('../route');
    await POST(req({ assignment_id: 'asg-1' }));
    expect(mock(logHint).mock.calls[0]).toEqual(['user_1', 'asg-1', 0]);
  });
});
