import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/review-service', () => ({ loadDueReviews: vi.fn() }));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadDueReviews } from '@/lib/companion/review-service';

const mock = (fn: unknown) =>
  fn as unknown as { mockResolvedValue: (v: unknown) => void };

const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('GET /api/gamification/companion/reviews/due', () => {
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

  it('403 for an unlinked student (D-8)', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { GET } = await import('../route');
    expect((await GET()).status).toBe(403);
    expect(loadDueReviews).not.toHaveBeenCalled();
  });

  it('404 when the per-org server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    const { GET } = await import('../route');
    expect((await GET()).status).toBe(404);
    expect(loadDueReviews).not.toHaveBeenCalled();
  });

  it('200 with the due queue and NO solution fields', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(loadDueReviews).mockResolvedValue([
      { competency: 'H_ROOK', title_en: 'The Rook', title_ru: 'Ладья', title_kk: 'Тура', rung: 2, interval_days: 3, next_review_at: null },
    ]);
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.count).toBe(1);
    expect(body.due[0].competency).toBe('H_ROOK');
    expect(JSON.stringify(body)).not.toContain('solution');
    expect(JSON.stringify(body)).not.toContain('fen');
  });
});
