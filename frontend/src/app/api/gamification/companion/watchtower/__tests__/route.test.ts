import { describe, it, expect, vi, beforeEach } from 'vitest';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));
vi.mock('@/lib/gamification/resolve-student', () => ({ resolveStudent: vi.fn() }));
vi.mock('@/lib/companion/service', () => ({ isCompanionEnabledForOrg: vi.fn() }));
vi.mock('@/lib/companion/watchtower-service', () => ({
  loadWatchtower: vi.fn(),
  recordLearningNode: vi.fn(),
}));

import { resolveStudent } from '@/lib/gamification/resolve-student';
import { isCompanionEnabledForOrg } from '@/lib/companion/service';
import { loadWatchtower, recordLearningNode } from '@/lib/companion/watchtower-service';

const mock = (fn: unknown) =>
  fn as unknown as { mockResolvedValue: (v: unknown) => void; mock: { calls: unknown[][] } };

function req(body: unknown) {
  return { json: async () => body } as unknown as import('next/server').NextRequest;
}
const LINKED = { ok: true, orgId: 'org-1', studentId: 'stu-1', ownerUserId: 'user_1' };

describe('GET /api/gamification/companion/watchtower', () => {
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

  it('403 for an unlinked student, 404 when the server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { GET } = await import('../route');
    expect((await GET()).status).toBe(403);

    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    expect((await GET()).status).toBe(404);
    expect(loadWatchtower).not.toHaveBeenCalled();
  });

  it('200 with the chapter view, never echoing a solution', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(loadWatchtower).mockResolvedValue({
      nodes: [{ node: 'W01', fen: '4k3/8/8/8/8/8/8/4K3 w - - 0 1', validator: 'squares', prompt: { en: 'p', ru: 'p', kk: 'p' }, hints_total: 1, completed: false }],
      completed_count: 0, total: 6, chapter_complete: false,
    });
    const { GET } = await import('../route');
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.total).toBe(6);
    expect(body.nodes[0].node).toBe('W01');
    expect(JSON.stringify(body)).not.toContain('solution');
  });
});

describe('POST /api/gamification/companion/watchtower', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    flags.on = true;
  });

  it('404 when the UI kill-switch is off', async () => {
    flags.on = false;
    const { POST } = await import('../route');
    expect((await POST(req({ node: 'W01', submission: { uci: 'a1a7' } }))).status).toBe(404);
  });

  it('403 for an unlinked student, 404 when the server flag is off', async () => {
    mock(resolveStudent).mockResolvedValue({ ok: false, status: 403, error: 'not_linked' });
    const { POST } = await import('../route');
    expect((await POST(req({ node: 'W01', submission: { uci: 'a1a7' } }))).status).toBe(403);

    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(false);
    expect((await POST(req({ node: 'W01', submission: { uci: 'a1a7' } }))).status).toBe(404);
    expect(recordLearningNode).not.toHaveBeenCalled();
  });

  it('400 when node or submission is missing', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    const { POST } = await import('../route');
    expect((await POST(req({ submission: { uci: 'a1a7' } }))).status).toBe(400);
    expect((await POST(req({ node: 'W01' }))).status).toBe(400);
    expect(recordLearningNode).not.toHaveBeenCalled();
  });

  it('404 for an unknown node family', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(recordLearningNode).mockResolvedValue({ status: 'not_found' });
    const { POST } = await import('../route');
    expect((await POST(req({ node: 'W99', submission: { uci: 'a1a7' } }))).status).toBe(404);
  });

  it('200 with the chapter-completion result, forwarding server identity', async () => {
    mock(resolveStudent).mockResolvedValue(LINKED);
    mock(isCompanionEnabledForOrg).mockResolvedValue(true);
    mock(recordLearningNode).mockResolvedValue({
      status: 'ok', correct: true, completed_count: 6, total: 6,
      chapter_complete: true, reward_granted: true, xp: 50, coins: 20,
    });
    const { POST } = await import('../route');
    const res = await POST(req({ node: 'W04', submission: { uci: 'a1a7' } }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.chapter_complete).toBe(true);
    expect(body.reward_granted).toBe(true);
    expect(JSON.stringify(body)).not.toContain('solution');
    expect(mock(recordLearningNode).mock.calls[0][0]).toMatchObject({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', node: 'W04',
    });
  });
});
