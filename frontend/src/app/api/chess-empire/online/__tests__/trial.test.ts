/**
 * Tests for /api/chess-empire/online/trial.
 *
 * The online 3-day trial skips the CE roster search entirely: it resolves a
 * `kind='online'` invite token and mints a synthetic-student invite JWT that
 * carries `external_source='online'` + a HARDCODED 72h access TTL. Covers:
 * missing branchToken (400), non-online / invalid / revoked tokens (401), and
 * the happy path (200 → JWT verifies with the online marker + TTL=72 + a
 * synthetic student id). Critically: TTL is 72 even when the token row's
 * `access_ttl_hours` is NULL (the trap the trial route must not fall into).
 * `name` is optional: present → JWT carries a `first_name` claim; absent → none.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const scripts: Record<string, ScriptedResponse[]> = {};

function nextScript(table: string, op: string): ScriptedResponse {
  const queue = scripts[`${table}.${op}`];
  if (!queue || queue.length === 0) return { data: null, error: null };
  return queue.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const chain: Record<string, unknown> = {
    select() {
      return chain;
    },
    eq() {
      return chain;
    },
    maybeSingle() {
      return Promise.resolve(nextScript(table, 'maybeSingle'));
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => makeBuilder(table),
  },
}));

import { POST } from '../trial/route';
import { verifyInviteJwt } from '@/lib/invite-jwt';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';
import { NextRequest } from 'next/server';

// TTL is NULL on the real token (nulled on purpose so roster students are
// permanent) — the trial route must ignore it and hardcode 72h.
const ONLINE_TOKEN = {
  id: 'token-online-1',
  organization_id: 'org-1',
  external_branch_id: 'br-online',
  kind: 'online',
  access_ttl_hours: null,
  expires_at: null,
  revoked_at: null,
};

function makeReq(body: unknown): NextRequest {
  return new NextRequest('http://x/api/chess-empire/online/trial', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  _resetRateLimitForTests();
  process.env.INVITE_JWT_SECRET = 'unit-test-secret';
});

describe('POST /api/chess-empire/online/trial', () => {
  it('400 when branchToken is missing (name alone is not enough)', async () => {
    expect((await POST(makeReq({}))).status).toBe(400);
    expect((await POST(makeReq({ name: 'Sam' }))).status).toBe(400);
  });

  it('401 when the token does not exist', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [{ data: null, error: null }];
    const res = await POST(makeReq({ branchToken: 'bad', name: 'Sam' }));
    expect(res.status).toBe(401);
  });

  it('401 for a branch token (trial endpoint rejects kind=branch)', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: { ...ONLINE_TOKEN, kind: 'branch' }, error: null },
    ];
    const res = await POST(makeReq({ branchToken: 't', name: 'Sam' }));
    expect(res.status).toBe(401);
  });

  it('401 for a revoked online token', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: { ...ONLINE_TOKEN, revoked_at: '2020-01-01T00:00:00Z' }, error: null },
    ];
    const res = await POST(makeReq({ branchToken: 't', name: 'Sam' }));
    expect(res.status).toBe(401);
  });

  it('mints a JWT carrying the online marker, TTL=72, and a synthetic student id', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: ONLINE_TOKEN, error: null },
    ];
    const res = await POST(makeReq({ branchToken: 't', name: 'Sam' }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { inviteJwt?: string };
    expect(typeof body.inviteJwt).toBe('string');

    const claims = verifyInviteJwt(body.inviteJwt!);
    expect(claims.external_source).toBe('online');
    expect(claims.member_type).toBe('student');
    expect(claims.access_ttl_hours).toBe(72);
    expect(claims.branch_id).toBe('br-online');
    expect(claims.org_id).toBe('org-1');
    expect(claims.branch_token_id).toBe('token-online-1');
    // Synthetic student id — a non-empty UUID, not a real CE record.
    expect(claims.student_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('hardcodes TTL=72 even when the token row has TTL set to a different value', async () => {
    // The trial route must NEVER read access_ttl_hours from the token. Even if a
    // stray non-null value is present, the minted JWT is 72h.
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: { ...ONLINE_TOKEN, access_ttl_hours: 9999 }, error: null },
    ];
    const res = await POST(makeReq({ branchToken: 't' }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { inviteJwt: string };
    expect(verifyInviteJwt(body.inviteJwt).access_ttl_hours).toBe(72);
  });

  it('mints without a first_name claim when no name is provided', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: ONLINE_TOKEN, error: null },
    ];
    const res = await POST(makeReq({ branchToken: 't' }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { inviteJwt: string };
    const claims = verifyInviteJwt(body.inviteJwt);
    expect(claims.first_name).toBeUndefined();
    // Still a valid online token otherwise.
    expect(claims.external_source).toBe('online');
    expect(claims.access_ttl_hours).toBe(72);
  });

  it('carries the provided name as the first_name claim', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: ONLINE_TOKEN, error: null },
    ];
    const res = await POST(makeReq({ branchToken: 't', name: '  Sam  ' }));
    expect(res.status).toBe(200);
    const body = (await res.json()) as { inviteJwt: string };
    const claims = verifyInviteJwt(body.inviteJwt);
    expect(claims.first_name).toBe('Sam');
  });

  it('gives each online trial a distinct synthetic student id', async () => {
    scripts['branch_invite_tokens.maybeSingle'] = [
      { data: ONLINE_TOKEN, error: null },
      { data: ONLINE_TOKEN, error: null },
    ];
    const a = (await (await POST(makeReq({ branchToken: 't', name: 'A' }))).json()) as {
      inviteJwt: string;
    };
    const b = (await (await POST(makeReq({ branchToken: 't', name: 'B' }))).json()) as {
      inviteJwt: string;
    };
    expect(verifyInviteJwt(a.inviteJwt).student_id).not.toBe(
      verifyInviteJwt(b.inviteJwt).student_id,
    );
  });
});
