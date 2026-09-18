/**
 * Tests for POST/DELETE /api/chess-empire/tournaments/[id]/register.
 *
 * Covers the family-registration gate: unauthenticated → 401; no verified
 * members → 403; a single-link account registers its one student with no body;
 * a multi-link account must name a student (400 student_required); a valid
 * `student_id` in the caller's allowlist registers that student; a `student_id`
 * NOT owned by the caller → 403 forbidden_student and CE is never called; CE
 * error mapping; and cancel by explicit / forbidden student_id.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

interface FakeMember {
  state: string;
  studentId: string | null;
  relationship?: string;
  source?: string;
}
const memberStore: { members: FakeMember[]; throws: boolean } = {
  members: [{ state: 'verified', studentId: 'stu-self', relationship: 'self' }],
  throws: false,
};
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => {
    if (memberStore.throws) throw new Error('boom');
    return memberStore.members;
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

/** POST request, optionally carrying a { student_id } body. */
function postReq(bodyStudentId?: string) {
  return new Request('http://x/api/chess-empire/tournaments/t1/register', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(bodyStudentId ? { student_id: bodyStudentId } : {}),
  });
}

/** DELETE request carrying student_id in the body, the query, or neither. */
function delReq(opts: { body?: string; query?: string } = {}) {
  const url = opts.query
    ? `http://x/api/chess-empire/tournaments/t1/register?student_id=${encodeURIComponent(opts.query)}`
    : 'http://x/api/chess-empire/tournaments/t1/register';
  return new Request(url, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json' },
    body: opts.body ? JSON.stringify({ student_id: opts.body }) : undefined,
  });
}

const SINGLE: FakeMember[] = [
  { state: 'verified', studentId: 'stu-self', relationship: 'self' },
];
const FAMILY: FakeMember[] = [
  { state: 'verified', studentId: 'stu-self', relationship: 'self' },
  { state: 'verified', studentId: 'stu-child', relationship: 'child' },
];

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.members = [...SINGLE];
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

  it('403 when signed in but has no verified members', async () => {
    memberStore.members = [];
    const res = await POST(postReq(), ctx());
    expect(res.status).toBe(403);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe('forbidden');
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('(a) no body + exactly one member → registers that student', async () => {
    registerMock.mockResolvedValue({ ok: true, registration_id: 'reg-9' });
    const res = await POST(postReq(), ctx('t1'));
    expect(res.status).toBe(200);
    expect(registerMock).toHaveBeenCalledWith('t1', 'stu-self', 'web');
    const body = (await res.json()) as { ok: boolean; registration_id: string };
    expect(body.ok).toBe(true);
    expect(body.registration_id).toBe('reg-9');
  });

  it('(b) no body + 2 members → 400 student_required, CE never called', async () => {
    memberStore.members = [...FAMILY];
    const res = await POST(postReq(), ctx('t1'));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string; message: string };
    expect(body.error).toBe('student_required');
    expect(typeof body.message).toBe('string');
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('(c) valid student_id of the second child → registers that id', async () => {
    memberStore.members = [...FAMILY];
    registerMock.mockResolvedValue({ ok: true, registration_id: 'reg-child' });
    const res = await POST(postReq('stu-child'), ctx('t1'));
    expect(res.status).toBe(200);
    expect(registerMock).toHaveBeenCalledWith('t1', 'stu-child', 'web');
  });

  it('(d) student_id NOT in the caller set → 403 forbidden_student, CE never called', async () => {
    memberStore.members = [...FAMILY];
    const res = await POST(postReq('attacker-student'), ctx('t1'));
    expect(res.status).toBe(403);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe('forbidden_student');
    expect(registerMock).not.toHaveBeenCalled();
  });

  it('a single-link account may still name its own student explicitly', async () => {
    registerMock.mockResolvedValue({ ok: true });
    const res = await POST(postReq('stu-self'), ctx('t1'));
    expect(res.status).toBe(200);
    expect(registerMock).toHaveBeenCalledWith('t1', 'stu-self', 'web');
  });

  it('registers a minted online child (a verified online member) by id', async () => {
    // A Phase-4 online family member is just another verified allowlist member —
    // the register route is source-agnostic, so it Just Works with no changes.
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self', source: 'online' },
      { state: 'verified', studentId: 'stu-online-kid', relationship: 'child', source: 'online' },
    ];
    registerMock.mockResolvedValue({ ok: true, registration_id: 'reg-online' });
    const res = await POST(postReq('stu-online-kid'), ctx('t1'));
    expect(res.status).toBe(200);
    expect(registerMock).toHaveBeenCalledWith('t1', 'stu-online-kid', 'web');
  });

  it('403 forbidden_student for an id outside the online caller allowlist', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self', source: 'online' },
      { state: 'verified', studentId: 'stu-online-kid', relationship: 'child', source: 'online' },
    ];
    const res = await POST(postReq('someone-elses-kid'), ctx('t1'));
    expect(res.status).toBe(403);
    expect((await res.json()).error).toBe('forbidden_student');
    expect(registerMock).not.toHaveBeenCalled();
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
    const res = await DELETE(delReq(), ctx());
    expect(res.status).toBe(401);
  });

  it('403 when the caller has no verified members', async () => {
    memberStore.members = [];
    const res = await DELETE(delReq(), ctx());
    expect(res.status).toBe(403);
  });

  it('404 when the member has no registration for this tournament', async () => {
    listRegsMock.mockResolvedValue([
      { id: 'reg-other', tournament_id: 'other', registered_at: 'x' },
    ]);
    const res = await DELETE(delReq(), ctx('t1'));
    expect(res.status).toBe(404);
    expect(cancelMock).not.toHaveBeenCalled();
  });

  it('cancels the single member registration when found', async () => {
    listRegsMock.mockResolvedValue([
      { id: 'reg-1', tournament_id: 't1', registered_at: 'x' },
    ]);
    cancelMock.mockResolvedValue(undefined);
    const res = await DELETE(delReq(), ctx('t1'));
    expect(res.status).toBe(200);
    expect(cancelMock).toHaveBeenCalledWith('reg-1');
  });

  it('cancels by explicit student_id (body) for a family member', async () => {
    memberStore.members = [...FAMILY];
    listRegsMock.mockResolvedValue([
      { id: 'reg-child', tournament_id: 't1', registered_at: 'x' },
    ]);
    cancelMock.mockResolvedValue(undefined);
    const res = await DELETE(delReq({ body: 'stu-child' }), ctx('t1'));
    expect(res.status).toBe(200);
    expect(listRegsMock).toHaveBeenCalledWith('stu-child');
    expect(cancelMock).toHaveBeenCalledWith('reg-child');
  });

  it('cancels by explicit student_id (query param) for a family member', async () => {
    memberStore.members = [...FAMILY];
    listRegsMock.mockResolvedValue([
      { id: 'reg-child', tournament_id: 't1', registered_at: 'x' },
    ]);
    cancelMock.mockResolvedValue(undefined);
    const res = await DELETE(delReq({ query: 'stu-child' }), ctx('t1'));
    expect(res.status).toBe(200);
    expect(listRegsMock).toHaveBeenCalledWith('stu-child');
  });

  it('cancels a minted online child registration by explicit student_id', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self', source: 'online' },
      { state: 'verified', studentId: 'stu-online-kid', relationship: 'child', source: 'online' },
    ];
    listRegsMock.mockResolvedValue([
      { id: 'reg-online', tournament_id: 't1', registered_at: 'x' },
    ]);
    cancelMock.mockResolvedValue(undefined);
    const res = await DELETE(delReq({ body: 'stu-online-kid' }), ctx('t1'));
    expect(res.status).toBe(200);
    expect(listRegsMock).toHaveBeenCalledWith('stu-online-kid');
    expect(cancelMock).toHaveBeenCalledWith('reg-online');
  });

  it('403 forbidden_student when cancelling a student the caller does not own', async () => {
    memberStore.members = [...FAMILY];
    const res = await DELETE(delReq({ body: 'not-mine' }), ctx('t1'));
    expect(res.status).toBe(403);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe('forbidden_student');
    expect(listRegsMock).not.toHaveBeenCalled();
    expect(cancelMock).not.toHaveBeenCalled();
  });

  it('400 student_required when a family account cancels with no student_id', async () => {
    memberStore.members = [...FAMILY];
    const res = await DELETE(delReq(), ctx('t1'));
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe('student_required');
    expect(listRegsMock).not.toHaveBeenCalled();
  });
});
