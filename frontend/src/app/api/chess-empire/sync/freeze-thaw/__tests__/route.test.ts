/**
 * Tests for POST /api/chess-empire/sync/freeze-thaw.
 *
 * Focuses on the route contract: service-token auth (fail-closed), body
 * validation, success wiring, and error mapping. The freeze/thaw + Clerk logic
 * itself is exercised in ce-sync-freeze-thaw.test.ts, so here we mock
 * `syncFreezeThawByStudent` (keeping the real NotFoundError) and Clerk.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@clerk/nextjs/server', () => ({
  clerkClient: vi.fn(async () => ({ organizations: {} })),
}));

const syncMock = vi.fn();
vi.mock('@/lib/chess-empire-admin', async (orig) => {
  const actual = (await orig()) as Record<string, unknown>;
  return { ...actual, syncFreezeThawByStudent: syncMock };
});

const TOKEN = 'test-service-token-123';

function post(body: unknown, headers: Record<string, string> = {}) {
  return new NextRequest('https://chesster.io/api/chess-empire/sync/freeze-thaw', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });
}

function auth(token = TOKEN) {
  return { authorization: `Bearer ${token}` };
}

beforeEach(() => {
  syncMock.mockReset();
  process.env.CE_SYNC_SERVICE_TOKEN = TOKEN;
});

afterEach(() => {
  delete process.env.CE_SYNC_SERVICE_TOKEN;
  vi.restoreAllMocks();
});

describe('POST /api/chess-empire/sync/freeze-thaw', () => {
  it('401 when no token is provided', async () => {
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'stu-1', status: 'frozen' }));
    expect(res.status).toBe(401);
    expect(syncMock).not.toHaveBeenCalled();
  });

  it('401 on a wrong token', async () => {
    const { POST } = await import('../route');
    const res = await POST(
      post({ external_student_id: 'stu-1', status: 'frozen' }, auth('wrong-token-aaaa')),
    );
    expect(res.status).toBe(401);
    expect(syncMock).not.toHaveBeenCalled();
  });

  it('401 (fail closed) when CE_SYNC_SERVICE_TOKEN is unset', async () => {
    delete process.env.CE_SYNC_SERVICE_TOKEN;
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'stu-1', status: 'frozen' }, auth()));
    expect(res.status).toBe(401);
    expect(syncMock).not.toHaveBeenCalled();
  });

  it('400 on an invalid status', async () => {
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'stu-1', status: 'left' }, auth()));
    expect(res.status).toBe(400);
    expect(syncMock).not.toHaveBeenCalled();
  });

  it('400 on a missing external_student_id', async () => {
    const { POST } = await import('../route');
    const res = await POST(post({ status: 'frozen' }, auth()));
    expect(res.status).toBe(400);
    expect(syncMock).not.toHaveBeenCalled();
  });

  it('freezes on a valid request', async () => {
    syncMock.mockResolvedValue({ action: 'freeze', linkStatus: 'frozen', memberId: 'mem-1' });
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'stu-1', status: 'frozen' }, auth()));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toMatchObject({ ok: true, action: 'freeze', linkStatus: 'frozen' });
    expect(syncMock).toHaveBeenCalledWith(
      expect.objectContaining({ externalStudentId: 'stu-1', ceStatus: 'frozen' }),
    );
  });

  it('thaws on a valid request', async () => {
    syncMock.mockResolvedValue({ action: 'thaw', linkStatus: 'verified', memberId: 'mem-1' });
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'stu-1', status: 'active' }, auth()));
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toMatchObject({ ok: true, action: 'thaw', linkStatus: 'verified' });
  });

  it('404 for an unknown student', async () => {
    const { NotFoundError } = await import('@/lib/chess-empire-admin');
    syncMock.mockRejectedValue(new NotFoundError('student_not_found'));
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'ghost', status: 'frozen' }, auth()));
    expect(res.status).toBe(404);
    const json = await res.json();
    expect(json.error).toBe('student_not_found');
  });

  it('500 on an unexpected error', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    syncMock.mockRejectedValue(new Error('boom'));
    const { POST } = await import('../route');
    const res = await POST(post({ external_student_id: 'stu-1', status: 'frozen' }, auth()));
    expect(res.status).toBe(500);
  });
});
