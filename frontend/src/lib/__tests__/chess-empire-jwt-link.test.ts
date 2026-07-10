/**
 * Tests for the shared invite-JWT linking logic (chess-empire-jwt-link.ts).
 *
 * Covers: happy path (verified upsert + consume + success audit), expired,
 * replayed, revoked branch token, tampered signature. The Supabase admin
 * client and Clerk client are mocked with a scripted query builder.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const scripts: Record<string, ScriptedResponse[]> = {};
const inserted: Array<{ table: string; payload: unknown }> = [];
const upserted: Array<{ table: string; payload: unknown; opts: unknown }> = [];

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
    limit() {
      return Promise.resolve(nextScript(table, 'select'));
    },
    maybeSingle() {
      return Promise.resolve(nextScript(table, 'maybeSingle'));
    },
    upsert(payload: unknown, opts: unknown) {
      upserted.push({ table, payload, opts });
      return Promise.resolve(nextScript(table, 'upsert'));
    },
    insert(payload: unknown) {
      inserted.push({ table, payload });
      return Promise.resolve(nextScript(table, 'insert'));
    },
    then(onFulfilled: (v: ScriptedResponse) => unknown) {
      return Promise.resolve(nextScript(table, 'select')).then(onFulfilled);
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: { from: (table: string) => makeBuilder(table) },
}));

const createMembershipSpy = vi.fn(async () => ({}));
vi.mock('@clerk/nextjs/server', () => ({
  clerkClient: async () => ({
    organizations: { createOrganizationMembership: createMembershipSpy },
  }),
}));

import { linkMemberViaInviteJwt } from '../chess-empire-jwt-link';
import { signInviteJwt } from '../invite-jwt';

const payload = {
  student_id: '00000000-0000-0000-0000-000000000001',
  branch_id: '00000000-0000-0000-0000-000000000002',
  branch_token_id: '00000000-0000-0000-0000-000000000003',
  org_id: '00000000-0000-0000-0000-000000000004',
};

function scriptHappyPath() {
  scripts['invite_jwts_consumed.select'] = [{ data: [] }]; // replay check: none
  scripts['branch_invite_tokens.select'] = [{ data: [{ id: 'bt', revoked_at: null }] }];
  scripts['organizations.select'] = [{ data: [{ id: payload.org_id, clerk_org_id: 'clerk-org' }] }];
  scripts['organization_members.upsert'] = [{ error: null }];
  scripts['invite_jwts_consumed.upsert'] = [{ error: null }];
}

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  inserted.length = 0;
  upserted.length = 0;
  createMembershipSpy.mockClear();
  process.env.INVITE_JWT_SECRET = 'unit-test-secret';
});

describe('linkMemberViaInviteJwt', () => {
  it('links a valid JWT: verified upsert + consume + Clerk membership + success audit', async () => {
    scriptHappyPath();
    const token = signInviteJwt(payload);
    const res = await linkMemberViaInviteJwt(token, 'clerk-user', 'a@b.com');

    expect(res).toEqual({
      ok: true,
      orgId: payload.org_id,
      studentId: payload.student_id,
      memberType: 'student',
    });

    const memberUpsert = upserted.find((u) => u.table === 'organization_members');
    expect(memberUpsert?.payload).toMatchObject({
      user_id: 'clerk-user',
      external_student_id: payload.student_id,
      link_status: 'verified',
      link_source: 'jwt',
      role: 'student',
    });
    // Idempotent consume with duplicate-tolerant upsert.
    const consume = upserted.find((u) => u.table === 'invite_jwts_consumed');
    expect(consume?.opts).toMatchObject({ onConflict: 'jti_hash', ignoreDuplicates: true });
    expect(createMembershipSpy).toHaveBeenCalledOnce();
    const success = inserted.find(
      (i) => i.table === 'link_attempts' && (i.payload as { status: string }).status === 'success',
    );
    expect(success).toBeDefined();
  });

  it('links a coach JWT with role=coach and skips a null clerk org', async () => {
    scripts['invite_jwts_consumed.select'] = [{ data: [] }];
    scripts['branch_invite_tokens.select'] = [{ data: [{ id: 'bt', revoked_at: null }] }];
    scripts['organizations.select'] = [{ data: [{ id: payload.org_id, clerk_org_id: null }] }];
    scripts['organization_members.upsert'] = [{ error: null }];
    scripts['invite_jwts_consumed.upsert'] = [{ error: null }];
    const token = signInviteJwt({ ...payload, member_type: 'coach' });
    const res = await linkMemberViaInviteJwt(token, 'coach-user', null);

    expect(res).toMatchObject({ ok: true, memberType: 'coach' });
    const memberUpsert = upserted.find((u) => u.table === 'organization_members');
    expect((memberUpsert?.payload as { role: string }).role).toBe('coach');
    expect(createMembershipSpy).not.toHaveBeenCalled();
  });

  it('rejects an expired token (soft failure, email fallback)', async () => {
    const now = 1_700_000_000;
    const token = signInviteJwt(payload, 60, now);
    const res = await linkMemberViaInviteJwt(token, 'clerk-user', 'a@b.com');
    expect(res).toEqual({ ok: false, reason: 'jwt_expired', fallbackToEmail: true });
    expect(upserted).toHaveLength(0);
  });

  it('rejects a tampered signature (soft failure, email fallback)', async () => {
    const token = signInviteJwt(payload).slice(0, -4) + 'AAAA';
    const res = await linkMemberViaInviteJwt(token, 'clerk-user', 'a@b.com');
    expect(res).toMatchObject({ ok: false, reason: 'jwt_invalid', fallbackToEmail: true });
    expect(upserted).toHaveLength(0);
  });

  it('rejects a replayed token (terminal, no fallback)', async () => {
    scripts['invite_jwts_consumed.select'] = [{ data: [{ jti_hash: 'seen' }] }];
    const token = signInviteJwt(payload);
    const res = await linkMemberViaInviteJwt(token, 'clerk-user', 'a@b.com');
    expect(res).toEqual({ ok: false, reason: 'jwt_replayed', fallbackToEmail: false });
    expect(upserted).toHaveLength(0);
  });

  it('rejects a revoked/missing branch token (terminal, no fallback)', async () => {
    scripts['invite_jwts_consumed.select'] = [{ data: [] }];
    scripts['branch_invite_tokens.select'] = [{ data: [{ id: 'bt', revoked_at: '2020-01-01' }] }];
    const token = signInviteJwt(payload);
    const res = await linkMemberViaInviteJwt(token, 'clerk-user', 'a@b.com');
    expect(res).toEqual({ ok: false, reason: 'jwt_invalid', fallbackToEmail: false });
    expect(upserted).toHaveLength(0);
  });
});
