/**
 * Tests for the Clerk `user.created` webhook — Phase 2 of the "robust
 * email ↔ CE student linking" arc.
 *
 * Covers:
 *   - happy path (JWT): verify → upsert member → create Clerk membership →
 *     consume JWT → log success attempt.
 *   - replay: JWT already consumed → jwt_replayed attempt logged, no writes,
 *     no email fallback.
 *   - non-CE signup: no inviteJwt → jwt_missing attempt, email fallback runs
 *     (no CE match → no_match attempt).
 *   - invalid JWT: jwt_invalid attempt + email fallback.
 *   - expired JWT: jwt_expired attempt + email fallback resolves (single
 *     student match writes pending_confirm).
 *   - email fallback single-match: pending_confirm upsert + success attempt.
 *   - email fallback zero-match: no writes, no_match attempt only.
 *   - email fallback multi-match: no writes, multiple_match attempt only.
 *   - Clerk 5xx: non-fatal — the DB link is already committed, so consumption
 *     + success attempt still run and the webhook returns 200.
 *   - Listmonk failure: swallowed.
 *
 * The JWT linking logic now lives in the shared `chess-empire-jwt-link` module
 * (reused by the client claim endpoint). Consumption is a duplicate-tolerant
 * upsert (not an insert) so the webhook + claim race stays idempotent.
 */
import { createHash } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// ---- shared supabase mock state ---------------------------------------------
type Payload = Record<string, unknown>;
type Insert = { table: string; payload: Payload };
type Upsert = { table: string; payload: Payload; onConflict?: string };

const state: {
  consumedHits: Payload[];
  tokenRow: Payload | null;
  orgRow: Payload | null;
  ceOrgRow: Payload | null;
  upserts: Upsert[];
  inserts: Insert[];
  selects: Array<{ table: string; columns: string; filters: Array<[string, unknown]> }>;
  fromCalls: string[];
  upsertError: string | null;
} = {
  consumedHits: [],
  tokenRow: null,
  orgRow: null,
  ceOrgRow: null,
  upserts: [],
  inserts: [],
  selects: [],
  fromCalls: [],
  upsertError: null,
};

function resetState(overrides: Partial<typeof state> = {}) {
  state.consumedHits = overrides.consumedHits ?? [];
  state.tokenRow = overrides.tokenRow ?? null;
  state.orgRow = overrides.orgRow ?? null;
  state.ceOrgRow =
    overrides.ceOrgRow ?? { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' };
  state.upserts = [];
  state.inserts = [];
  state.selects = [];
  state.fromCalls = [];
  state.upsertError = overrides.upsertError ?? null;
}

function makeBuilder(table: string) {
  const rec = { columns: '', filters: [] as Array<[string, unknown]> };
  const finalSelect = () => {
    state.selects.push({ table, columns: rec.columns, filters: rec.filters });
    if (table === 'invite_jwts_consumed') {
      return Promise.resolve({ data: state.consumedHits, error: null });
    }
    if (table === 'branch_invite_tokens') {
      return Promise.resolve({
        data: state.tokenRow ? [state.tokenRow] : [],
        error: null,
      });
    }
    if (table === 'organizations') {
      // Selecting by slug=chess-empire for the email-fallback path, or by
      // id for the JWT path. Discriminate via `filters`.
      const bySlug = rec.filters.some(
        ([col, val]) => col === 'slug' && val === 'chess-empire',
      );
      if (bySlug) {
        return Promise.resolve({
          data: state.ceOrgRow ? [state.ceOrgRow] : [],
          error: null,
        });
      }
      return Promise.resolve({
        data: state.orgRow ? [state.orgRow] : [],
        error: null,
      });
    }
    return Promise.resolve({ data: [], error: null });
  };

  const chain: Record<string, unknown> = {
    select(cols: string) {
      rec.columns = cols;
      return chain;
    },
    eq(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    limit(_n: number) {
      return finalSelect();
    },
    upsert(payload: Payload, opts?: { onConflict?: string }) {
      state.upserts.push({ table, payload, onConflict: opts?.onConflict });
      if (state.upsertError) {
        return Promise.resolve({ data: null, error: { message: state.upsertError } });
      }
      return Promise.resolve({ data: null, error: null });
    },
    insert(payload: Payload) {
      state.inserts.push({ table, payload });
      return Promise.resolve({ data: null, error: null });
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => {
      state.fromCalls.push(table);
      return makeBuilder(table);
    },
  },
}));

// ---- svix mock -------------------------------------------------------------
vi.mock('svix', () => ({
  Webhook: class {
    verify(body: string) {
      return JSON.parse(body);
    }
  },
}));

// ---- next/headers mock -----------------------------------------------------
vi.mock('next/headers', () => ({
  headers: async () => ({
    get(name: string) {
      const map: Record<string, string> = {
        'svix-id': 'msg_test_user_created',
        'svix-timestamp': String(Math.floor(Date.now() / 1000)),
        'svix-signature': 'v1,dummy',
      };
      return map[name] ?? null;
    },
  }),
}));

// ---- Clerk mock ------------------------------------------------------------
const createMembership = vi.fn();
vi.mock('@clerk/nextjs/server', () => ({
  clerkClient: async () => ({
    organizations: {
      createOrganizationMembership: createMembership,
    },
  }),
}));

// ---- Listmonk mock ---------------------------------------------------------
const createSubscriber = vi.fn();
const blocklistSubscriber = vi.fn();
vi.mock('@/lib/listmonk', () => ({
  createSubscriber: (...args: unknown[]) => createSubscriber(...args),
  blocklistSubscriber: (...args: unknown[]) => blocklistSubscriber(...args),
  LISTS: { ALL_USERS: 3, WELCOME_SEQUENCE: 4 },
}));

// ---- CE client mock --------------------------------------------------------
const findByEmail = vi.fn();
const findCoaches = vi.fn();
vi.mock('@/lib/chess-empire-client', () => ({
  findStudentsByParentEmail: (...args: unknown[]) => findByEmail(...args),
  findCoachesByEmail: (...args: unknown[]) => findCoaches(...args),
}));

// ---- imports under test (must come after mocks) ----------------------------
import { POST } from '../route';
import { signInviteJwt } from '@/lib/invite-jwt';

// ---- helpers ---------------------------------------------------------------
type UserCreatedOverrides = {
  inviteJwt?: string | null;
  userId?: string;
  email?: string;
};

function makeEvent(overrides: UserCreatedOverrides = {}) {
  const unsafe: Record<string, unknown> =
    overrides.inviteJwt === null || overrides.inviteJwt === undefined
      ? {}
      : { inviteJwt: overrides.inviteJwt };
  return {
    type: 'user.created',
    data: {
      id: overrides.userId ?? 'user_2test',
      email_addresses: [
        { id: 'em_1', email_address: overrides.email ?? 'parent@example.com' },
      ],
      primary_email_address_id: 'em_1',
      first_name: 'Kirill',
      last_name: 'Ivanov',
      unsafe_metadata: unsafe,
      created_at: 1_700_000_000,
    },
  };
}

function makeRequest(event: unknown): Request {
  return new Request('http://localhost/api/webhooks/clerk', {
    method: 'POST',
    body: JSON.stringify(event),
    headers: { 'content-type': 'application/json' },
  });
}

function signValidInvite(overrides: Partial<Record<string, string>> = {}): string {
  process.env.INVITE_JWT_SECRET = 'phase2-melodic-webhook-secret';
  return signInviteJwt({
    student_id: 'stu-xyz',
    branch_id: 'br-xyz',
    branch_token_id: 'tok-uuid',
    org_id: 'org-uuid',
    ...overrides,
  });
}

function signExpiredInvite(): string {
  process.env.INVITE_JWT_SECRET = 'phase2-melodic-webhook-secret';
  const nowSec = Math.floor(Date.now() / 1000);
  // TTL = 1 second, "now" = 60 min ago → produces a token that fails the exp check.
  return signInviteJwt(
    {
      student_id: 'stu-expired',
      branch_id: 'br-xyz',
      branch_token_id: 'tok-uuid',
      org_id: 'org-uuid',
    },
    1,
    nowSec - 3600,
  );
}

beforeEach(() => {
  process.env.CLERK_WEBHOOK_SECRET = 'whsec_test';
  process.env.INVITE_JWT_SECRET = 'phase2-melodic-webhook-secret';
  createMembership.mockReset();
  createSubscriber.mockReset();
  createSubscriber.mockResolvedValue({ id: 1, created: true });
  blocklistSubscriber.mockReset();
  findByEmail.mockReset();
  findByEmail.mockResolvedValue([]);
  findCoaches.mockReset();
  findCoaches.mockResolvedValue([]);
  resetState();
});

// Helper: filter the recorded link_attempts payloads.
function attemptsForStatus(status: string) {
  return state.inserts
    .filter((i) => i.table === 'link_attempts')
    .map((i) => i.payload)
    .filter((p) => p.status === status);
}

describe('POST /api/webhooks/clerk — user.created — JWT path', () => {
  it('happy path: links member, creates Clerk membership, records consumption + success attempt', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockResolvedValue({});

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);

    expect(createSubscriber).toHaveBeenCalledTimes(1);

    // Exactly one organization_members upsert with the expected linkage
    const memberUpserts = state.upserts.filter(
      (u) => u.table === 'organization_members',
    );
    expect(memberUpserts).toHaveLength(1);
    const up = memberUpserts[0];
    expect(up.onConflict).toBe(
      'organization_id,external_student_id,external_source',
    );
    expect(up.payload.user_id).toBe('user_2test');
    expect(up.payload.external_student_id).toBe('stu-xyz');
    expect(up.payload.external_source).toBe('chess_empire');
    expect(up.payload.link_status).toBe('verified');
    expect(up.payload.link_source).toBe('jwt');
    expect(up.payload.link_verified_at).toBeTruthy();

    // Clerk create membership called
    expect(createMembership).toHaveBeenCalledWith({
      organizationId: 'clerk-org-abc',
      userId: 'user_2test',
      role: 'org:member',
    });

    // Consumption row (duplicate-tolerant upsert) + success link_attempt row
    const consumed = state.upserts.filter(
      (u) => u.table === 'invite_jwts_consumed',
    );
    expect(consumed).toHaveLength(1);
    expect(consumed[0].payload.jti_hash).toBe(
      createHash('sha256').update(jwt).digest('hex'),
    );

    const successes = attemptsForStatus('success');
    expect(successes).toHaveLength(1);
    expect(successes[0].attempted_source).toBe('jwt');
    expect(successes[0].chosen_student_id).toBe('stu-xyz');

    // Fallback path must NOT have run on happy JWT
    expect(findByEmail).not.toHaveBeenCalled();
  });
});

describe('POST /api/webhooks/clerk — user.created — coach JWT', () => {
  it('member_type=coach → writes role:coach on the member row', async () => {
    const jwt = signValidInvite({ student_id: 'coach-xyz', member_type: 'coach' });
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockResolvedValue({});

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);

    const memberUpserts = state.upserts.filter(
      (u) => u.table === 'organization_members',
    );
    expect(memberUpserts).toHaveLength(1);
    const up = memberUpserts[0];
    expect(up.payload.role).toBe('coach');
    expect(up.payload.external_student_id).toBe('coach-xyz');
    expect(up.payload.external_source).toBe('chess_empire');
    expect(up.payload.link_status).toBe('verified');

    expect(attemptsForStatus('success')).toHaveLength(1);
  });

  it('legacy JWT without member_type → writes role:student', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockResolvedValue({});

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    const memberUpsert = state.upserts.find(
      (u) => u.table === 'organization_members',
    );
    expect(memberUpsert?.payload.role).toBe('student');
  });
});

describe('POST /api/webhooks/clerk — user.created — replay', () => {
  it('JWT already consumed → jwt_replayed attempt, no writes, no email fallback', async () => {
    const jwt = signValidInvite();
    resetState({
      consumedHits: [{ jti_hash: 'existing' }],
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);

    expect(state.upserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
    expect(findByEmail).not.toHaveBeenCalled();

    const replayed = attemptsForStatus('jwt_replayed');
    expect(replayed).toHaveLength(1);
    expect(replayed[0].attempted_source).toBe('jwt');

    // Listmonk still runs
    expect(createSubscriber).toHaveBeenCalledTimes(1);
  });
});

describe('POST /api/webhooks/clerk — user.created — JWT missing / expired / invalid → email fallback', () => {
  it('JWT missing + email matches ZERO CE students → jwt_missing + no_match attempts, no writes', async () => {
    resetState();
    findByEmail.mockResolvedValue([]);
    const res = await POST(makeRequest(makeEvent({ inviteJwt: null })));
    expect(res.status).toBe(200);

    expect(attemptsForStatus('jwt_missing')).toHaveLength(1);
    expect(attemptsForStatus('no_match')).toHaveLength(1);
    expect(state.upserts).toEqual([]);
    expect(findByEmail).toHaveBeenCalledTimes(1);
  });

  it('JWT missing + email matches SINGLE CE student → jwt_missing + success attempts, pending_confirm upsert', async () => {
    resetState();
    findByEmail.mockResolvedValue([
      {
        id: 'stu-matched',
        first_name: 'Aiman',
        last_name: 'K',
        branch_id: 'br',
        status: 'active',
        date_of_birth: null,
      },
    ]);
    const res = await POST(makeRequest(makeEvent({ inviteJwt: null })));
    expect(res.status).toBe(200);

    expect(state.upserts).toHaveLength(1);
    const up = state.upserts[0];
    expect(up.table).toBe('organization_members');
    expect(up.payload.link_status).toBe('pending_confirm');
    expect(up.payload.link_source).toBe('email_auto');
    expect(up.payload.external_student_id).toBe('stu-matched');
    // No link_verified_at set for pending_confirm
    expect(up.payload.link_verified_at).toBeUndefined();

    const successes = attemptsForStatus('success');
    expect(successes).toHaveLength(1);
    expect(successes[0].attempted_source).toBe('email_auto');
    expect(successes[0].chosen_student_id).toBe('stu-matched');
    expect(attemptsForStatus('jwt_missing')).toHaveLength(1);
  });

  it('JWT missing + email matches MULTIPLE CE students → jwt_missing + multiple_match attempts, no writes', async () => {
    resetState();
    findByEmail.mockResolvedValue([
      { id: 'stu-a', first_name: 'A', last_name: '', branch_id: 'b', status: 'active', date_of_birth: null },
      { id: 'stu-b', first_name: 'B', last_name: '', branch_id: 'b', status: 'active', date_of_birth: null },
    ]);
    const res = await POST(makeRequest(makeEvent({ inviteJwt: null })));
    expect(res.status).toBe(200);

    expect(state.upserts).toEqual([]);
    const multi = attemptsForStatus('multiple_match');
    expect(multi).toHaveLength(1);
    expect(multi[0].candidate_student_ids).toEqual(['stu-a', 'stu-b']);
    expect(attemptsForStatus('jwt_missing')).toHaveLength(1);
  });

  it('invalid JWT: jwt_invalid attempt + email fallback runs', async () => {
    resetState();
    findByEmail.mockResolvedValue([]);
    const res = await POST(makeRequest(makeEvent({ inviteJwt: 'this.is.not-a-real-jwt' })));
    expect(res.status).toBe(200);

    expect(state.upserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
    expect(attemptsForStatus('jwt_invalid')).toHaveLength(1);
    expect(findByEmail).toHaveBeenCalledTimes(1);
  });

  it('expired JWT: jwt_expired attempt + email fallback single-match → pending_confirm upsert', async () => {
    resetState();
    const expiredJwt = signExpiredInvite();
    findByEmail.mockResolvedValue([
      {
        id: 'stu-vasco',
        first_name: 'Turabay',
        last_name: 'Ali',
        branch_id: 'br',
        status: 'active',
        date_of_birth: null,
      },
    ]);
    const res = await POST(makeRequest(makeEvent({ inviteJwt: expiredJwt })));
    expect(res.status).toBe(200);

    expect(attemptsForStatus('jwt_expired')).toHaveLength(1);
    expect(state.upserts).toHaveLength(1);
    expect(state.upserts[0].payload.link_status).toBe('pending_confirm');
    expect(state.upserts[0].payload.external_student_id).toBe('stu-vasco');
  });
});

describe('POST /api/webhooks/clerk — user.created — coach email fallback', () => {
  it('no student + SINGLE coach email match → links as coach (pending_confirm) + success attempt', async () => {
    resetState();
    findByEmail.mockResolvedValue([]);
    findCoaches.mockResolvedValue([
      {
        id: 'coach-shokan',
        first_name: 'Shokan',
        last_name: 'Karimov',
        branch_id: 'br',
        email: 'karimov.shokan@gmail.com',
      },
    ]);
    const res = await POST(
      makeRequest(makeEvent({ inviteJwt: null, email: 'karimov.shokan@gmail.com' })),
    );
    expect(res.status).toBe(200);

    expect(state.upserts).toHaveLength(1);
    const up = state.upserts[0];
    expect(up.table).toBe('organization_members');
    expect(up.payload.role).toBe('coach');
    expect(up.payload.link_status).toBe('pending_confirm');
    expect(up.payload.link_source).toBe('email_auto');
    expect(up.payload.external_student_id).toBe('coach-shokan');
    expect(up.payload.link_verified_at).toBeUndefined();

    const successes = attemptsForStatus('success');
    expect(successes).toHaveLength(1);
    expect(successes[0].attempted_source).toBe('email_auto');
    expect(successes[0].chosen_student_id).toBe('coach-shokan');
    expect(attemptsForStatus('no_match')).toHaveLength(0);
    // Student lookup ran first, then the coach fallback.
    expect(findByEmail).toHaveBeenCalledTimes(1);
    expect(findCoaches).toHaveBeenCalledTimes(1);
  });

  it('no student + MULTIPLE coach email matches → no_match, no writes', async () => {
    resetState();
    findByEmail.mockResolvedValue([]);
    findCoaches.mockResolvedValue([
      { id: 'coach-a', first_name: 'A', last_name: '', branch_id: 'b', email: 'dup@x.com' },
      { id: 'coach-b', first_name: 'B', last_name: '', branch_id: 'b', email: 'dup@x.com' },
    ]);
    const res = await POST(
      makeRequest(makeEvent({ inviteJwt: null, email: 'dup@x.com' })),
    );
    expect(res.status).toBe(200);

    expect(state.upserts).toEqual([]);
    expect(attemptsForStatus('no_match')).toHaveLength(1);
    expect(attemptsForStatus('success')).toHaveLength(0);
  });

  it('student match takes precedence — coach lookup never runs', async () => {
    resetState();
    findByEmail.mockResolvedValue([
      {
        id: 'stu-matched',
        first_name: 'Aiman',
        last_name: 'K',
        branch_id: 'br',
        status: 'active',
        date_of_birth: null,
      },
    ]);
    // Even if a coach shared the email, the single student wins.
    findCoaches.mockResolvedValue([
      { id: 'coach-x', first_name: 'X', last_name: '', branch_id: 'b', email: 'shared@x.com' },
    ]);
    const res = await POST(
      makeRequest(makeEvent({ inviteJwt: null, email: 'shared@x.com' })),
    );
    expect(res.status).toBe(200);

    expect(state.upserts).toHaveLength(1);
    expect(state.upserts[0].payload.role).toBe('student');
    expect(state.upserts[0].payload.external_student_id).toBe('stu-matched');
    expect(findCoaches).not.toHaveBeenCalled();
  });
});

describe('POST /api/webhooks/clerk — user.created — bubbling / retries', () => {
  it('revoked branch token: jwt_invalid attempt, no writes, no fallback', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: '2026-01-01T00:00:00Z' },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(state.upserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
    expect(findByEmail).not.toHaveBeenCalled();
    expect(attemptsForStatus('jwt_invalid')).toHaveLength(1);
  });

  it('Clerk 422 already-member: still records consumption + success attempt', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockRejectedValue(
      Object.assign(new Error('already a member'), { status: 422 }),
    );

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(
      state.upserts.filter((u) => u.table === 'organization_members'),
    ).toHaveLength(1);
    expect(
      state.upserts.filter((u) => u.table === 'invite_jwts_consumed'),
    ).toHaveLength(1);
    expect(attemptsForStatus('success')).toHaveLength(1);
  });

  it('Clerk 5xx: non-fatal — DB link committed, so consumption + success still run (200)', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 }),
    );

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    // The member row (source of truth for the dashboard) is written, so a
    // failed Clerk org-membership call must not strand the user or 500.
    expect(
      state.upserts.filter((u) => u.table === 'organization_members'),
    ).toHaveLength(1);
    expect(
      state.upserts.filter((u) => u.table === 'invite_jwts_consumed'),
    ).toHaveLength(1);
    expect(attemptsForStatus('success')).toHaveLength(1);
  });

  it('Listmonk failure does not block CE flow', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createSubscriber.mockRejectedValue(new Error('listmonk down'));
    createMembership.mockResolvedValue({});

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(
      state.upserts.filter((u) => u.table === 'organization_members'),
    ).toHaveLength(1);
    expect(
      state.upserts.filter((u) => u.table === 'invite_jwts_consumed'),
    ).toHaveLength(1);
    expect(attemptsForStatus('success')).toHaveLength(1);
    expect(createMembership).toHaveBeenCalledTimes(1);
  });
});

describe('POST /api/webhooks/clerk — user.deleted', () => {
  it('blocklists subscriber by email', async () => {
    const event = {
      type: 'user.deleted',
      data: {
        email_addresses: [{ email_address: 'gone@example.com' }],
      },
    };
    const res = await POST(makeRequest(event));
    expect(res.status).toBe(200);
    expect(blocklistSubscriber).toHaveBeenCalledWith('gone@example.com');
  });
});
