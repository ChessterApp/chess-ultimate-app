import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/assessment-service', () => ({ recordAttempt: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { recordAttempt } from '@/lib/companion/assessment-service';

const mock = (fn: unknown) => fn as unknown as {
  mockResolvedValue: (v: unknown) => void;
  mock: { calls: unknown[][] };
};

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('POST /api/gamification/companion/attempts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    const res = await POST(req({ assignment_id: 'a', submission: { uci: 'a1a8' } }));
    expect(res.status).toBe(404);
    expect(resolveStudent).not.toHaveBeenCalled();
  });

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    expect((await POST(req({ assignment_id: 'a', submission: { uci: 'a1a8' } }))).status).toBe(403);
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { POST } = await import('../route');
    const res = await POST(req({ assignment_id: 'a', submission: { uci: 'a1a8' } }));
    expect(res.status).toBe(404);
    expect(recordAttempt).not.toHaveBeenCalled();
  });

  it('400 when assignment_id or submission is missing', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');
    expect((await POST(req({ submission: { uci: 'a1a8' } }))).status).toBe(400);
    expect((await POST(req({ assignment_id: 'a' }))).status).toBe(400);
    expect(recordAttempt).not.toHaveBeenCalled();
  });

  it('404 when the assignment is unknown / not owned', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(recordAttempt).mockResolvedValue({ status: 'not_found' });
    const { POST } = await import('../route');
    expect((await POST(req({ assignment_id: 'x', submission: { uci: 'a1a8' } }))).status).toBe(404);
  });

  it('409 for a non-assessment assignment', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(recordAttempt).mockResolvedValue({ status: 'invalid_mode' });
    const { POST } = await import('../route');
    expect((await POST(req({ assignment_id: 'a', submission: { uci: 'a1a8' } }))).status).toBe(409);
  });

  it('200 with the verdict + reward, and never echoes a solution', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(recordAttempt).mockResolvedValue({
      status: 'ok',
      correct: true,
      assistance_used: false,
      demonstrated: true,
      times_correct: 3,
      reward_granted: true,
      xp: 30,
      coins: 10,
    });
    const { POST } = await import('../route');
    const res = await POST(req({ assignment_id: 'asg-1', submission: { uci: 'a1a8' } }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.correct).toBe(true);
    expect(body.reward_granted).toBe(true);
    expect(body.xp).toBe(30);
    expect(JSON.stringify(body)).not.toContain('solution');
    // The route forwards identity from resolveStudent, not the client body.
    expect(mock(recordAttempt).mock.calls[0][0]).toMatchObject({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      assignmentId: 'asg-1',
    });
  });
});
