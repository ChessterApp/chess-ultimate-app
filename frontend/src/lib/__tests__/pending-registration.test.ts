/**
 * Tests for the server-side pending-registration claim path
 * (pending-registration.ts).
 *
 * Covers: a pending row is claimed (verified member upsert + pending_row_success
 * audit + row marked claimed), a row already claimed by another Clerk user is
 * rejected (single-use), and an expired row is rejected. The Supabase admin
 * client and Clerk client are mocked with a per-table scripted query builder.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

// Per-table FIFO queues — the code touches each table in a fixed order, so any
// awaited terminal consumes the next scripted response for that table.
const scripts: Record<string, ScriptedResponse[]> = {};
const inserted: Array<{ table: string; payload: unknown }> = [];
const upserted: Array<{ table: string; payload: unknown; opts: unknown }> = [];
const updated: Array<{ table: string; payload: unknown }> = [];

function nextScript(table: string): ScriptedResponse {
  const queue = scripts[table];
  if (!queue || queue.length === 0) return { data: null, error: null };
  return queue.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const resolveNext = () => Promise.resolve(nextScript(table));
  const chain: Record<string, unknown> = {
    select() {
      return chain;
    },
    eq() {
      return chain;
    },
    limit() {
      return chain;
    },
    update(payload: unknown) {
      updated.push({ table, payload });
      return chain;
    },
    upsert(payload: unknown, opts: unknown) {
      upserted.push({ table, payload, opts });
      return resolveNext();
    },
    insert(payload: unknown) {
      inserted.push({ table, payload });
      return resolveNext();
    },
    maybeSingle() {
      return resolveNext();
    },
    then(onFulfilled: (v: ScriptedResponse) => unknown, onRejected?: (e: unknown) => unknown) {
      return resolveNext().then(onFulfilled, onRejected);
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

import { claimPendingByJwt } from '../pending-registration';

const ORG = '00000000-0000-0000-0000-000000000004';
const STUDENT = '00000000-0000-0000-0000-000000000001';
const RAW_JWT = 'header.payload.signature';

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  inserted.length = 0;
  upserted.length = 0;
  updated.length = 0;
  createMembershipSpy.mockClear();
});

describe('claimPendingByJwt', () => {
  it('claims a pending row: verified member upsert + pending_row_success audit + row marked claimed', async () => {
    scripts['pending_registrations'] = [
      // lookup
      {
        data: {
          id: 'pr1',
          student_id: STUDENT,
          org_id: ORG,
          member_type: 'student',
          status: 'pending',
          created_at: new Date().toISOString(),
          claimed_by_clerk_user_id: null,
        },
      },
      // atomic claim update → we win (one row returned)
      { data: [{ id: 'pr1' }] },
    ];
    scripts['organization_members'] = [{ error: null }]; // upsert
    scripts['organizations'] = [{ data: [{ clerk_org_id: 'clerk-org' }] }];
    scripts['link_attempts'] = [{ error: null }]; // audit insert

    const res = await claimPendingByJwt(RAW_JWT, 'clerk-user', 'a@b.com');

    expect(res).toEqual({
      ok: true,
      orgId: ORG,
      studentId: STUDENT,
      memberType: 'student',
    });

    const memberUpsert = upserted.find((u) => u.table === 'organization_members');
    expect(memberUpsert?.payload).toMatchObject({
      user_id: 'clerk-user',
      external_student_id: STUDENT,
      link_status: 'verified',
      link_source: 'jwt',
      role: 'student',
    });

    // Row flipped to claimed by this user.
    const claim = updated.find(
      (u) =>
        u.table === 'pending_registrations' &&
        (u.payload as { status?: string }).status === 'claimed',
    );
    expect(claim?.payload).toMatchObject({
      status: 'claimed',
      claimed_by_clerk_user_id: 'clerk-user',
    });

    // Clerk membership granted + distinct audit status.
    expect(createMembershipSpy).toHaveBeenCalledOnce();
    const audit = inserted.find((i) => i.table === 'link_attempts');
    expect((audit?.payload as { status: string }).status).toBe('pending_row_success');
    expect((audit?.payload as { chosen_student_id: string }).chosen_student_id).toBe(
      STUDENT,
    );
  });

  it('rejects a row already claimed by a different Clerk user (single-use)', async () => {
    scripts['pending_registrations'] = [
      {
        data: {
          id: 'pr1',
          student_id: STUDENT,
          org_id: ORG,
          member_type: 'student',
          status: 'claimed',
          created_at: new Date().toISOString(),
          claimed_by_clerk_user_id: 'other-user',
        },
      },
    ];

    const res = await claimPendingByJwt(RAW_JWT, 'clerk-user', null);
    expect(res).toEqual({ ok: false, reason: 'claimed_by_other' });
    // No link written.
    expect(upserted).toHaveLength(0);
    expect(createMembershipSpy).not.toHaveBeenCalled();
  });

  it('treats a re-claim by the same user as idempotent success', async () => {
    scripts['pending_registrations'] = [
      {
        data: {
          id: 'pr1',
          student_id: STUDENT,
          org_id: ORG,
          member_type: 'coach',
          status: 'claimed',
          created_at: new Date().toISOString(),
          claimed_by_clerk_user_id: 'clerk-user',
        },
      },
    ];

    const res = await claimPendingByJwt(RAW_JWT, 'clerk-user', null);
    expect(res).toEqual({
      ok: true,
      orgId: ORG,
      studentId: STUDENT,
      memberType: 'coach',
    });
    // Already claimed — no fresh upsert.
    expect(upserted).toHaveLength(0);
  });

  it('rejects an expired row (older than 7 days) and marks it expired', async () => {
    const eightDaysAgo = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
    scripts['pending_registrations'] = [
      {
        data: {
          id: 'pr1',
          student_id: STUDENT,
          org_id: ORG,
          member_type: 'student',
          status: 'pending',
          created_at: eightDaysAgo,
          claimed_by_clerk_user_id: null,
        },
      },
      { data: null }, // the expire update
    ];

    const res = await claimPendingByJwt(RAW_JWT, 'clerk-user', null);
    expect(res).toEqual({ ok: false, reason: 'expired' });
    expect(upserted).toHaveLength(0);
    const expire = updated.find(
      (u) =>
        u.table === 'pending_registrations' &&
        (u.payload as { status?: string }).status === 'expired',
    );
    expect(expire).toBeDefined();
  });

  it('returns not_found when no pending row matches the jti hash', async () => {
    scripts['pending_registrations'] = [{ data: null }];
    const res = await claimPendingByJwt(RAW_JWT, 'clerk-user', null);
    expect(res).toEqual({ ok: false, reason: 'not_found' });
  });

  it('rejects when the atomic claim is lost to another user (race)', async () => {
    scripts['pending_registrations'] = [
      // lookup: still pending
      {
        data: {
          id: 'pr1',
          student_id: STUDENT,
          org_id: ORG,
          member_type: 'student',
          status: 'pending',
          created_at: new Date().toISOString(),
          claimed_by_clerk_user_id: null,
        },
      },
      // claim update returns zero rows — we lost the race
      { data: [] },
      // re-read: someone else won
      { data: { claimed_by_clerk_user_id: 'other-user' } },
    ];

    const res = await claimPendingByJwt(RAW_JWT, 'clerk-user', null);
    expect(res).toEqual({ ok: false, reason: 'claimed_by_other' });
    expect(upserted).toHaveLength(0);
  });
});
