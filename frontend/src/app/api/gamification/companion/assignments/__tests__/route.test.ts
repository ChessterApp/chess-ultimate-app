import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/assessment-service', () => ({ createAssignment: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { createAssignment } from '@/lib/companion/assessment-service';

const mock = (fn: unknown) => fn as unknown as { mockResolvedValue: (v: unknown) => void };

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('POST /api/gamification/companion/assignments', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    const res = await POST(req({ competency: 'H_ROOK' }));
    expect(res.status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    expect((await POST(req({ competency: 'H_ROOK' }))).status).toBe(403);
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { POST } = await import('../route');
    const res = await POST(req({ competency: 'H_ROOK' }));
    expect(res.status).toBe(404);
    expect(createAssignment).not.toHaveBeenCalled();
  });

  it('400 when competency is missing', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    expect(createAssignment).not.toHaveBeenCalled();
  });

  it('404 when the competency has no task pool', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(createAssignment).mockResolvedValue({ status: 'no_tasks' });
    const { POST } = await import('../route');
    expect((await POST(req({ competency: 'H_NONE' }))).status).toBe(404);
  });

  it('200 with a solution-free task payload', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const task = {
      assignment_id: 'asg-9',
      competency: 'H_ROOK',
      family: 'H_ROOK_T1',
      fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1',
      prompt: { en: 'Move the rook.', ru: 'x', kk: 'y' },
      validator: 'move',
      hints_total: 1,
    };
    mock(createAssignment).mockResolvedValue({ status: 'ok', task });
    const { POST } = await import('../route');
    const res = await POST(req({ competency: 'H_ROOK' }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.assignment_id).toBe('asg-9');
    expect(JSON.stringify(body)).not.toContain('solution');
    expect(createAssignment).toHaveBeenCalledWith('user_1', 'H_ROOK');
  });
});
