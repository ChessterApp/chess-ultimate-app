/**
 * Tests for the Clerk `user.created` webhook — Phase 6 Chess Empire
 * onboarding completion (Node port of `backend/tests/test_webhooks_user_created.py`).
 *
 * Covers:
 *   - happy path: verify → upsert member → create Clerk membership → consume JWT
 *   - replay: JWT already consumed → short-circuit, no writes
 *   - non-CE signup: no inviteJwt in unsafe_metadata → Listmonk-only, no CE writes
 *   - invalid JWT: silent warning, no writes
 *   - revoked branch token: refuse, no writes
 *   - Clerk create membership 422: still succeed, consumption still recorded
 *   - Clerk create membership 5xx: throw so Svix retries; JWT stays unconsumed
 *   - Listmonk failure: swallowed, CE flow still runs
 */
import { createHash } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// ---- shared supabase mock state ---------------------------------------------
type Payload = Record<string, unknown>;
const state: {
  consumedHits: Payload[];
  tokenRow: Payload | null;
  orgRow: Payload | null;
  upserts: Array<{ table: string; payload: Payload; onConflict?: string }>;
  inserts: Array<{ table: string; payload: Payload }>;
  selects: Array<{ table: string; columns: string; filters: Array<[string, unknown]> }>;
  fromCalls: string[];
} = {
  consumedHits: [],
  tokenRow: null,
  orgRow: null,
  upserts: [],
  inserts: [],
  selects: [],
  fromCalls: [],
};

function resetState(overrides: Partial<typeof state> = {}) {
  state.consumedHits = overrides.consumedHits ?? [];
  state.tokenRow = overrides.tokenRow ?? null;
  state.orgRow = overrides.orgRow ?? null;
  state.upserts = [];
  state.inserts = [];
  state.selects = [];
  state.fromCalls = [];
}

function makeSelectResult(table: string): { data: Payload[]; error: null } {
  if (table === 'invite_jwts_consumed') return { data: state.consumedHits, error: null };
  if (table === 'branch_invite_tokens') {
    return { data: state.tokenRow ? [state.tokenRow] : [], error: null };
  }
  if (table === 'organizations') {
    return { data: state.orgRow ? [state.orgRow] : [], error: null };
  }
  return { data: [], error: null };
}

function makeBuilder(table: string) {
  const rec = { columns: '', filters: [] as Array<[string, unknown]> };
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
      state.selects.push({ table, columns: rec.columns, filters: rec.filters });
      return Promise.resolve(makeSelectResult(table));
    },
    upsert(payload: Payload, opts?: { onConflict?: string }) {
      state.upserts.push({ table, payload, onConflict: opts?.onConflict });
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

// ---- imports under test (must come after mocks) ----------------------------
import { POST } from '../route';
import { signInviteJwt } from '@/lib/invite-jwt';

// ---- helpers ---------------------------------------------------------------
type UserCreatedOverrides = {
  inviteJwt?: string | null;
  userId?: string;
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
        { id: 'em_1', email_address: 'parent@example.com' },
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
  process.env.INVITE_JWT_SECRET = 'phase6-user-created-secret';
  return signInviteJwt({
    student_id: 'stu-xyz',
    branch_id: 'br-xyz',
    branch_token_id: 'tok-uuid',
    org_id: 'org-uuid',
    ...overrides,
  });
}

beforeEach(() => {
  process.env.CLERK_WEBHOOK_SECRET = 'whsec_test';
  process.env.INVITE_JWT_SECRET = 'phase6-user-created-secret';
  createMembership.mockReset();
  createSubscriber.mockReset();
  createSubscriber.mockResolvedValue({ id: 1, created: true });
  blocklistSubscriber.mockReset();
  resetState();
});

describe('POST /api/webhooks/clerk — user.created', () => {
  it('happy path: links member, creates Clerk membership, records consumption', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockResolvedValue({});

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);

    // Listmonk still called
    expect(createSubscriber).toHaveBeenCalledTimes(1);

    // Upsert to organization_members with the expected linkage
    expect(state.upserts).toHaveLength(1);
    const up = state.upserts[0];
    expect(up.table).toBe('organization_members');
    expect(up.onConflict).toBe(
      'organization_id,external_student_id,external_source',
    );
    expect(up.payload.user_id).toBe('user_2test');
    expect(up.payload.external_student_id).toBe('stu-xyz');
    expect(up.payload.external_source).toBe('chess_empire');
    expect(up.payload.link_status).toBe('verified');
    expect(up.payload.email).toBe('parent@example.com');
    expect(up.payload.name).toBe('Kirill Ivanov');

    // Clerk create membership called with correct args
    expect(createMembership).toHaveBeenCalledTimes(1);
    expect(createMembership).toHaveBeenCalledWith({
      organizationId: 'clerk-org-abc',
      userId: 'user_2test',
      role: 'org:member',
    });

    // Consumption row inserted with sha256 hash
    expect(state.inserts).toHaveLength(1);
    const ins = state.inserts[0];
    expect(ins.table).toBe('invite_jwts_consumed');
    expect(ins.payload.jti_hash).toBe(createHash('sha256').update(jwt).digest('hex'));
    expect(ins.payload.clerk_user_id).toBe('user_2test');
    expect(ins.payload.external_student_id).toBe('stu-xyz');
    expect(ins.payload.branch_token_id).toBe('tok-uuid');
    expect(ins.payload.organization_id).toBe('org-uuid');
  });

  it('replay: already-consumed JWT short-circuits, no writes, no Clerk call', async () => {
    const jwt = signValidInvite();
    resetState({
      consumedHits: [{ jti_hash: 'existing' }],
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(state.upserts).toEqual([]);
    expect(state.inserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
    // Listmonk still runs on replay signups
    expect(createSubscriber).toHaveBeenCalledTimes(1);
  });

  it('non-CE signup: no inviteJwt → Listmonk still called, no supabase writes', async () => {
    resetState();
    const res = await POST(makeRequest(makeEvent({ inviteJwt: null })));
    expect(res.status).toBe(200);
    expect(createSubscriber).toHaveBeenCalledTimes(1);
    expect(state.upserts).toEqual([]);
    expect(state.inserts).toEqual([]);
    expect(state.fromCalls).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
  });

  it('invalid JWT: silent skip, no writes, no Clerk call', async () => {
    resetState();
    const res = await POST(makeRequest(makeEvent({ inviteJwt: 'this.is.not-a-real-jwt' })));
    expect(res.status).toBe(200);
    expect(state.upserts).toEqual([]);
    expect(state.inserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
    // Listmonk still runs
    expect(createSubscriber).toHaveBeenCalledTimes(1);
  });

  it('revoked branch token: refuse, no writes', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: '2026-01-01T00:00:00Z' },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(state.upserts).toEqual([]);
    expect(state.inserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
  });

  it('missing org: refuse, no writes', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: null,
    });

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(state.upserts).toEqual([]);
    expect(state.inserts).toEqual([]);
    expect(createMembership).not.toHaveBeenCalled();
  });

  it('Clerk 422 already-member: still records consumption', async () => {
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
    expect(state.upserts).toHaveLength(1);
    expect(state.inserts).toHaveLength(1);
  });

  it('Clerk 422 detected via errors[].code=already_a_member_of_organization', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockRejectedValue(
      Object.assign(new Error('already member'), {
        errors: [{ code: 'already_a_member_of_organization' }],
      }),
    );

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(200);
    expect(state.inserts).toHaveLength(1);
  });

  it('Clerk 5xx: returns 500, upsert ran but consumption did NOT', async () => {
    const jwt = signValidInvite();
    resetState({
      tokenRow: { id: 'tok-uuid', revoked_at: null },
      orgRow: { id: 'org-uuid', clerk_org_id: 'clerk-org-abc' },
    });
    createMembership.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 }),
    );

    const res = await POST(makeRequest(makeEvent({ inviteJwt: jwt })));
    expect(res.status).toBe(500);
    // Upsert already ran (idempotent), but the JWT-consumed row did NOT
    expect(state.upserts).toHaveLength(1);
    expect(state.inserts).toEqual([]);
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
    expect(state.upserts).toHaveLength(1);
    expect(state.inserts).toHaveLength(1);
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
