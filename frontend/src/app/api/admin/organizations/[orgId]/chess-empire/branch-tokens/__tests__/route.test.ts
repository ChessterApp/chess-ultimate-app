import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

vi.mock('@/lib/chess-empire-admin', async () => {
  const actual = await vi.importActual<typeof import('@/lib/chess-empire-admin')>(
    '@/lib/chess-empire-admin',
  );
  return {
    ...actual,
    listBranchTokens: vi.fn(),
    insertBranchToken: vi.fn(),
  };
});

import { auth } from '@clerk/nextjs/server';
import {
  listBranchTokens,
  insertBranchToken,
  ExistingActiveTokenError,
} from '@/lib/chess-empire-admin';

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

describe('GET /chess-empire/branch-tokens', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('401 unauthed', async () => {
    mockAuth(null);
    const { GET } = await import('../route');
    const r = await GET(new Request('http://localhost') as never, {
      params: Promise.resolve({ orgId: ORG }),
    });
    expect(r.status).toBe(401);
  });

  it('returns tokens for admin', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (listBranchTokens as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue([{ id: 't-1' }]);
    const { GET } = await import('../route');
    const r = await GET(new Request('http://localhost') as never, {
      params: Promise.resolve({ orgId: ORG }),
    });
    expect(r.status).toBe(200);
    const data = await r.json();
    expect(data.tokens).toEqual([{ id: 't-1' }]);
  });
});

describe('POST /chess-empire/branch-tokens', () => {
  const realFetch = global.fetch;
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => {
    global.fetch = realFetch;
  });

  it('400 when branchId/branchName missing', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', { method: 'POST', body: '{}' }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(400);
  });

  it('201 with created + url on success', async () => {
    mockAuth('user_1');
    mockBackendMembers('owner');
    (insertBranchToken as unknown as { mockResolvedValue: (v: unknown) => void })
      .mockResolvedValue({
        id: 't-new',
        organization_id: ORG,
        external_branch_id: 'br-1',
        branch_name: 'NIS',
        token: 'fresh',
      });
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', {
        method: 'POST',
        body: JSON.stringify({ branchId: 'br-1', branchName: 'NIS' }),
      }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(201);
    const data = await r.json();
    expect(data.created.id).toBe('t-new');
    expect(data.url).toContain('/welcome/fresh');
  });

  it('409 when an active token already exists', async () => {
    mockAuth('user_1');
    mockBackendMembers('admin');
    (insertBranchToken as unknown as { mockRejectedValue: (v: unknown) => void })
      .mockRejectedValue(new ExistingActiveTokenError());
    const { POST } = await import('../route');
    const r = await POST(
      new Request('http://localhost', {
        method: 'POST',
        body: JSON.stringify({ branchId: 'br-1', branchName: 'NIS' }),
      }) as never,
      { params: Promise.resolve({ orgId: ORG }) },
    );
    expect(r.status).toBe(409);
    const data = await r.json();
    expect(data.error).toBe('existing_active_token');
  });
});
