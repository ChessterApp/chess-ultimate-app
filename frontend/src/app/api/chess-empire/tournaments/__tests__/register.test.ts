/**
 * Tests for POST/DELETE /api/chess-empire/tournaments/[id]/register.
 *
 * Covers the registration gate: unauthenticated → 401; signed-in but unverified
 * → 403; verified → CE register called with the MEMBER's studentId (a body
 * student_id can never override it); CE error mapping (full/deadline/duplicate/
 * level-gate); and self-cancel (none found → 404, found → deleted).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

const memberStore: {
  result: { state: string; studentId: string | null };
  throws: boolean;
} = { result: { state: 'verified', studentId: 'stu-verified' }, throws: false };
vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipStateForUser: vi.fn(async () => {
    if (memberStore.throws) throw new Error('boom');
    return memberStore.result;
  }),
}));

const registerMock = vi.fn();
const cancelMock = vi.fn();
const listRegsMock = vi.fn();
// The error class is defined INSIDE the factory (it is referenced eagerly in
// the returned object, so a hoisted top-level class would hit its TDZ). The
// test pulls the same class back via the mocked-module import below so its
// `instanceof` checks in the route hold.
vi.mock('@/lib/chess-empire-client', () => {
  class ChessEmpireAPIError extends Error {
    statusCode: number;
    body: unknown;
    constructor(statusCode: number, body: unknown) {
      super('ce');
      this.statusCode = statusCode;
      this.body = body;
      this.name = 'ChessEmpireAPIError';
    }
  }
  return {
    ChessEmpireAPIError,
    registerForTournament: (...args: unknown[]) => registerMock(...args),
    cancelTournamentRegistration: (...args: unknown[]) => cancelMock(...args),
    getStudentTournamentRegistrations: (...args: unknown[]) => listRegsMock(...args),
  };
});

import { POST, DELETE } from '../[id]/register/route';
import { ChessEmpireAPIError } from '@/lib/chess-empire-client';

function ctx(id = 't1') {
  return { params: Promise.resolve({ id }) };
}

/** POST request whose body tries (and must fail) to inject a student_id. */
function postReq(bodyStudentId?: string) {
  return new Request('http://x/api/chess-empire/tournaments/t1/register', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(bodyStudentId ? { student_id: bodyStudentId } : {}),
  });
}

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.result = { state: 'verified', studentId: 'stu-verified' };
  memberStore.throws = false;
  registerMock.mockReset();
  cancelMock.mockReset();
  listRegsMock.mockReset();
});

describe('POST /api/chess-empire/tournaments/[id]/register', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await POST(postReq(), ctx());
    expect(res.status).toBe(401);
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('403 when signed in but not a verified member', async () => {
    memberStore.result = { state: 'no_link', studentId: null };
    const res = await POST(postReq(), ctx());
    expect(res.status).toBe(403);
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('registers with the member studentId, ignoring a body student_id', async () => {
    registerMock.mockResolvedValue({ ok: true, registration_id: 'reg-9' });
    const res = await POST(postReq('attacker-student'), ctx('t1'));
    expect(res.status).toBe(200);
    expect(registerMock).toHaveBeenCalledWith('t1', 'stu-verified', 'web');
    const body = (await res.json()) as { ok: boolean; registration_id: string };
    expect(body.ok).toBe(true);
    expect(body.registration_id).toBe('reg-9');
  });

  it.each([
    ['full', 409],
    ['closed', 409],
    ['duplicate', 409],
    ['ineligible', 409],
    ['no_razryad', 409],
    ['not_found', 404],
  ])('maps CE reason %s → HTTP %i with a message', async (reason, status) => {
    registerMock.mockRejectedValue(
      new ChessEmpireAPIError(status, { ok: false, reason }),
    );
    const res = await POST(postReq(), ctx());
    expect(res.status).toBe(status);
    const body = (await res.json()) as { error: string; message: string };
    expect(body.error).toBe(reason);
    expect(typeof body.message).toBe('string');
  });

  it('maps CE reason no_razryad → 409 with the canonical razryad copy', async () => {
    registerMock.mockRejectedValue(
      new ChessEmpireAPIError(409, { ok: false, reason: 'no_razryad' }),
    );
    const res = await POST(postReq(), ctx());
    expect(res.status).toBe(409);
    const body = (await res.json()) as { error: string; message: string };
    expect(body.error).toBe('no_razryad');
    expect(body.message).toBe(
      'Registration is only available to students with a razryad (chess rating category).',
    );
  });

  it('500 when the membership lookup throws', async () => {
    memberStore.throws = true;
    const res = await POST(postReq(), ctx());
    expect(res.status).toBe(500);
  });
});

describe('DELETE /api/chess-empire/tournaments/[id]/register', () => {
  it('401 when unauthenticated', async () => {
    authStore.userId = null;
    const res = await DELETE(postReq(), ctx());
    expect(res.status).toBe(401);
  });

  it('403 when not a verified member', async () => {
    memberStore.result = { state: 'pending_confirm', studentId: 'stu-1' };
    const res = await DELETE(postReq(), ctx());
    expect(res.status).toBe(403);
  });

  it('404 when the member has no registration for this tournament', async () => {
    listRegsMock.mockResolvedValue([
      { id: 'reg-other', tournament_id: 'other', registered_at: 'x' },
    ]);
    const res = await DELETE(postReq(), ctx('t1'));
    expect(res.status).toBe(404);
    expect(cancelMock).not.toHaveBeenCalled();
  });

  it('cancels the matching registration when found', async () => {
    listRegsMock.mockResolvedValue([
      { id: 'reg-1', tournament_id: 't1', registered_at: 'x' },
    ]);
    cancelMock.mockResolvedValue(undefined);
    const res = await DELETE(postReq(), ctx('t1'));
    expect(res.status).toBe(200);
    expect(cancelMock).toHaveBeenCalledWith('reg-1');
  });
});
