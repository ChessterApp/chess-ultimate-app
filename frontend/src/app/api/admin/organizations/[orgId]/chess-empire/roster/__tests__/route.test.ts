import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

vi.mock('@/lib/chess-empire-admin', () => ({
  listOrgCeMembers: vi.fn(),
}));

vi.mock('@/lib/chess-empire-client', () => ({
  listBranches: vi.fn(),
  listCoaches: vi.fn(),
  listActiveStudentsByBranch: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';
import { listOrgCeMembers } from '@/lib/chess-empire-admin';
import {
  listBranches,
  listCoaches,
  listActiveStudentsByBranch,
} from '@/lib/chess-empire-client';

const ORG = 'org-ce';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

function mockBackendMembers(role: string | null) {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          members: role ? [{ user_id: 'user_1', role }] : [],
        }),
    } as Response),
  ) as unknown as typeof fetch;
}

describe('GET /api/admin/organizations/[orgId]/chess-empire/roster', () => {
  const realFetch = global.fetch;
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 when not authed', async () => {
    mockAuth(null);
    const { GET } = await import('../route');
    const r = await GET(new Request('http://localhost') as never, {
      params: Promise.resolve({ orgId: ORG }),
    });
    expect(r.status).toBe(401);
  });

  it('403 when caller not admin/owner', async () => {
    mockAuth('user_1');
    mockBackendMembers('student');
    const { GET } = await import('../route');
    const r = await GET(new Request('http://localhost') as never, {
      params: Promise.resolve({ orgId: ORG }),
    });
    expect(r.status).toBe(403);
  });

  it('returns merged payload on happy path', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (listOrgCeMembers as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue([{ id: 'm-1', link_status: 'verified' }]);
    (listBranches as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue([{ id: 'br-1', name: 'Debut' }]);
    (listCoaches as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue([{ id: 'co-1', full_name: 'Yerkezhan' }]);
    (
      listActiveStudentsByBranch as unknown as {
        mockResolvedValue: (v: unknown) => void;
      }
    ).mockResolvedValue([{ id: 's-1', branch_id: 'br-1', status: 'active' }]);

    const { GET } = await import('../route');
    const r = await GET(new Request('http://localhost') as never, {
      params: Promise.resolve({ orgId: ORG }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.ceMembers).toHaveLength(1);
    expect(data.branches).toHaveLength(1);
    expect(data.coaches).toHaveLength(1);
    expect(data.ceActiveStudents).toHaveLength(1);
  });

  it('returns 200 with empty branches when CE branches call fails', async () => {
    mockAuth('user_1');
    mockBackendMembers('owner');
    (listOrgCeMembers as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue([]);
    (listBranches as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new Error('CE down'));
    (listCoaches as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue([]);
    (
      listActiveStudentsByBranch as unknown as {
        mockResolvedValue: (v: unknown) => void;
      }
    ).mockResolvedValue([]);

    const { GET } = await import('../route');
    const r = await GET(new Request('http://localhost') as never, {
      params: Promise.resolve({ orgId: ORG }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.branches).toEqual([]);
    expect(data.ceActiveStudents).toEqual([]);
  });
});
