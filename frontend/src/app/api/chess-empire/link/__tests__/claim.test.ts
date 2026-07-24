/**
 * Tests for POST /api/chess-empire/link/claim.
 *
 * Covers: unauthenticated (401), missing/invalid body (400), valid claim
 * (200 verified), expired (410 terminal), replayed / already-linked (409
 * terminal), invalid (400 terminal), rate-limit (429). The shared linking
 * logic is mocked — its own behavior is covered in chess-empire-jwt-link.test.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { JwtLinkResult } from '@/lib/chess-empire-jwt-link';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
  clerkClient: async () => ({
    users: {
      getUser: async () => ({
        primaryEmailAddressId: 'e1',
        emailAddresses: [{ id: 'e1', emailAddress: 'a@b.com' }],
      }),
    },
  }),
}));

const linkResult: { current: JwtLinkResult } = {
  current: { ok: true, orgId: 'org-1', studentId: 'stu-1', memberType: 'student' },
};
const linkSpy = vi.fn(async () => linkResult.current);
vi.mock('@/lib/chess-empire-jwt-link', () => ({
  linkMemberViaInviteJwt: (...args: unknown[]) => linkSpy(...(args as [])),
}));

// The cookie→pending-row fallback is unit-tested separately; here it never
// finds a row (the test Request carries no cookie anyway).
const pendingSpy = vi.fn(async () => ({ ok: false, reason: 'not_found' }));
vi.mock('@/lib/pending-registration', () => ({
  CE_PENDING_COOKIE: 'ce_pending_jti',
  claimPendingByJwt: (...args: unknown[]) => pendingSpy(...(args as [])),
}));

import { POST } from '../claim/route';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';

function makeReq(body: unknown, ip = '1.1.1.1'): Request {
  return new Request('https://x/api/chess-empire/link/claim', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-forwarded-for': ip },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
}

beforeEach(() => {
  _resetRateLimitForTests();
  authStore.userId = 'user-1';
  linkResult.current = { ok: true, orgId: 'org-1', studentId: 'stu-1', memberType: 'student' };
  linkSpy.mockClear();
});

describe('POST /api/chess-empire/link/claim', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST(makeReq({ inviteJwt: 'x' }) as never);
    expect(res.status).toBe(401);
    expect(linkSpy).not.toHaveBeenCalled();
  });

  it('400 on invalid JSON body', async () => {
    const res = await POST(makeReq('not-json') as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'invalid_body' });
  });

  it('400 when inviteJwt is missing', async () => {
    const res = await POST(makeReq({}) as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'missing_jwt' });
  });

  it('200 verified on a valid claim', async () => {
    const res = await POST(makeReq({ inviteJwt: 'good.jwt.tok' }) as never);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, state: 'verified', studentId: 'stu-1' });
    // Now called with the claim-path grace window as a 4th arg.
    expect(linkSpy).toHaveBeenCalledWith(
      'good.jwt.tok',
      'user-1',
      'a@b.com',
      expect.objectContaining({ graceSeconds: expect.any(Number) }),
    );
  });

  it('410 terminal on expired JWT', async () => {
    linkResult.current = { ok: false, reason: 'jwt_expired', fallbackToEmail: true };
    const res = await POST(makeReq({ inviteJwt: 'x' }) as never);
    expect(res.status).toBe(410);
    expect(await res.json()).toEqual({ error: 'expired', terminal: true });
  });

  it('409 terminal on replayed / already-linked JWT', async () => {
    linkResult.current = { ok: false, reason: 'jwt_replayed', fallbackToEmail: false };
    const res = await POST(makeReq({ inviteJwt: 'x' }) as never);
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ error: 'replayed', terminal: true });
  });

  it('400 terminal on invalid JWT', async () => {
    linkResult.current = { ok: false, reason: 'jwt_invalid', fallbackToEmail: false };
    const res = await POST(makeReq({ inviteJwt: 'x' }) as never);
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'invalid', terminal: true });
  });

  it('500 on unexpected webhook_error', async () => {
    linkResult.current = { ok: false, reason: 'webhook_error', fallbackToEmail: false };
    const res = await POST(makeReq({ inviteJwt: 'x' }) as never);
    expect(res.status).toBe(500);
  });

  it('429 once the per-user rate limit is exhausted', async () => {
    // PER_USER_LIMIT is 5 — the 6th claim for the same user is throttled.
    for (let i = 0; i < 5; i++) {
      const ok = await POST(makeReq({ inviteJwt: 'x' }, `9.9.9.${i}`) as never);
      expect(ok.status).toBe(200);
    }
    const limited = await POST(makeReq({ inviteJwt: 'x' }, '9.9.9.99') as never);
    expect(limited.status).toBe(429);
  });
});
