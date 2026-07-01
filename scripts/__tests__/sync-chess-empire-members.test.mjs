/**
 * Tests for scripts/sync-chess-empire-members.mjs.
 *
 * Uses node:test — matches the placement + style of
 * generate-branch-invites.test.mjs. Mocks the supabase / CE / Clerk clients
 * so nothing hits the network. Every entry in the reconciliation matrix
 * gets a dedicated test.
 *
 * Run with: node --test scripts/__tests__/sync-chess-empire-members.test.mjs
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

import {
  buildSummaryMd,
  chunk,
  decideAction,
  reconcile,
  writeSummary,
} from '../sync-chess-empire-members.mjs';

function makeSupabase(members, updateRecorder) {
  return {
    from(table) {
      if (table === 'organization_members') {
        const chainState = { filters: {}, isSelect: true, updatePayload: null };
        const chain = {
          select() { chainState.isSelect = true; return chain; },
          eq(col, val) {
            chainState.filters[col] = val;
            // eq() is thenable when it's the terminal filter on a SELECT.
            // We only support: .from().select().eq('external_source', 'chess_empire') → then().
            if (chainState.isSelect) {
              return {
                then(resolve) {
                  const rows = members.filter((m) => {
                    if (m.external_source !== 'chess_empire') return false;
                    if (chainState.filters.organization_id
                      && m.organization_id !== chainState.filters.organization_id) return false;
                    return true;
                  });
                  resolve({ data: rows, error: null });
                },
                eq(col2, val2) {
                  chainState.filters[col2] = val2;
                  return this;
                },
              };
            }
            // UPDATE path: capture then resolve.
            updateRecorder.push({
              id: val,
              payload: chainState.updatePayload,
            });
            return {
              then(resolve) { resolve({ data: null, error: null }); },
            };
          },
          update(payload) {
            chainState.isSelect = false;
            chainState.updatePayload = payload;
            return chain;
          },
        };
        return chain;
      }
      throw new Error(`Unexpected table: ${table}`);
    },
  };
}

function makeClerk() {
  const calls = { create: [], delete: [] };
  return {
    calls,
    async createMembership(orgId, userId, role) {
      calls.create.push({ orgId, userId, role });
    },
    async deleteMembership(orgId, userId) {
      calls.delete.push({ orgId, userId });
    },
  };
}

function makeCe(profiles, opts = {}) {
  return {
    async getStudentsByIds(ids) {
      if (opts.throwOn) throw new Error(opts.throwOn);
      return ids
        .map((id) => profiles[id])
        .filter((p) => p !== undefined);
    },
  };
}

// ── decideAction matrix ──────────────────────────────────────────────────

test('decideAction: active + verified → none', () => {
  assert.equal(decideAction('active', 'verified').action, 'none');
});

test('decideAction: active + frozen → thaw', () => {
  assert.equal(decideAction('active', 'frozen').action, 'thaw');
});

test('decideAction: active + revoked → none (terminal)', () => {
  assert.equal(decideAction('active', 'revoked').action, 'none');
});

test('decideAction: active + pending → none (not signed up yet)', () => {
  assert.equal(decideAction('active', 'pending').action, 'none');
});

test('decideAction: frozen + verified → freeze', () => {
  assert.equal(decideAction('frozen', 'verified').action, 'freeze');
});

test('decideAction: frozen + frozen → none', () => {
  assert.equal(decideAction('frozen', 'frozen').action, 'none');
});

test('decideAction: left + verified → revoke', () => {
  assert.equal(decideAction('left', 'verified').action, 'revoke');
});

test('decideAction: left + frozen → revoke', () => {
  assert.equal(decideAction('left', 'frozen').action, 'revoke');
});

test('decideAction: left + revoked → none (already revoked)', () => {
  assert.equal(decideAction('left', 'revoked').action, 'none');
});

test('decideAction: missing CE profile → missing', () => {
  assert.equal(decideAction(null, 'verified').action, 'missing');
});

// ── chunk helper ─────────────────────────────────────────────────────────

test('chunk splits arrays into fixed-size slices', () => {
  assert.deepEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(chunk([], 5), []);
});

// ── reconcile: end-to-end mutations ─────────────────────────────────────

test('reconcile: frozen→verified thaws in Chesster + adds Clerk membership', async () => {
  const members = [{
    id: 'mem-1',
    organization_id: 'org-1',
    user_id: 'user_1',
    external_student_id: 'stu-1',
    external_source: 'chess_empire',
    link_status: 'frozen',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({ 'stu-1': { id: 'stu-1', status: 'active' } });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk });

  assert.equal(result.counts.thaw, 1);
  assert.equal(updates.length, 1);
  assert.equal(updates[0].id, 'mem-1');
  assert.equal(updates[0].payload.link_status, 'verified');
  assert.equal(clerk.calls.create.length, 1);
  assert.equal(clerk.calls.create[0].orgId, 'clerk-org-1');
  assert.equal(clerk.calls.create[0].userId, 'user_1');
});

test('reconcile: verified→frozen freezes + removes Clerk membership', async () => {
  const members = [{
    id: 'mem-2',
    organization_id: 'org-1',
    user_id: 'user_2',
    external_student_id: 'stu-2',
    external_source: 'chess_empire',
    link_status: 'verified',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({ 'stu-2': { id: 'stu-2', status: 'frozen' } });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk });

  assert.equal(result.counts.freeze, 1);
  assert.equal(updates[0].payload.link_status, 'frozen');
  assert.equal(clerk.calls.delete.length, 1);
  assert.equal(clerk.calls.delete[0].userId, 'user_2');
});

test('reconcile: left → revoked, delete membership, terminal', async () => {
  const members = [{
    id: 'mem-3',
    organization_id: 'org-1',
    user_id: 'user_3',
    external_student_id: 'stu-3',
    external_source: 'chess_empire',
    link_status: 'verified',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({ 'stu-3': { id: 'stu-3', status: 'left' } });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk });

  assert.equal(result.counts.revoke, 1);
  assert.equal(updates[0].payload.link_status, 'revoked');
  assert.ok(updates[0].payload.link_revoked_at);
  assert.equal(clerk.calls.delete.length, 1);
});

test('reconcile: no-op when statuses aligned', async () => {
  const members = [{
    id: 'mem-4',
    organization_id: 'org-1',
    user_id: 'user_4',
    external_student_id: 'stu-4',
    external_source: 'chess_empire',
    link_status: 'verified',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({ 'stu-4': { id: 'stu-4', status: 'active' } });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk });

  assert.equal(result.counts.none, 1);
  assert.equal(updates.length, 0);
  assert.equal(clerk.calls.create.length, 0);
  assert.equal(clerk.calls.delete.length, 0);
});

test('reconcile: missing CE profile → warning, no mutation', async () => {
  const members = [{
    id: 'mem-5',
    organization_id: 'org-1',
    user_id: 'user_5',
    external_student_id: 'stu-5',
    external_source: 'chess_empire',
    link_status: 'verified',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({}); // no profile returned
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk });

  assert.equal(result.warnings.length, 1);
  assert.equal(updates.length, 0);
  assert.equal(result.counts.missing, 1);
});

test('reconcile: --dry-run writes no mutations', async () => {
  const members = [{
    id: 'mem-6',
    organization_id: 'org-1',
    user_id: 'user_6',
    external_student_id: 'stu-6',
    external_source: 'chess_empire',
    link_status: 'frozen',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({ 'stu-6': { id: 'stu-6', status: 'active' } });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk, dryRun: true });

  assert.equal(result.counts.thaw, 1);
  assert.equal(updates.length, 0);
  assert.equal(clerk.calls.create.length, 0);
});

test('reconcile: --org filters to a single organization', async () => {
  const members = [
    {
      id: 'mem-a', organization_id: 'org-a', user_id: 'ua',
      external_student_id: 'stu-a', external_source: 'chess_empire',
      link_status: 'frozen',
      organizations: { id: 'org-a', clerk_org_id: 'clerk-a' },
    },
    {
      id: 'mem-b', organization_id: 'org-b', user_id: 'ub',
      external_student_id: 'stu-b', external_source: 'chess_empire',
      link_status: 'frozen',
      organizations: { id: 'org-b', clerk_org_id: 'clerk-b' },
    },
  ];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({
    'stu-a': { id: 'stu-a', status: 'active' },
    'stu-b': { id: 'stu-b', status: 'active' },
  });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk, orgFilter: 'org-a' });

  assert.equal(result.scanned, 1);
  assert.equal(result.counts.thaw, 1);
  assert.equal(updates.length, 1);
  assert.equal(updates[0].id, 'mem-a');
});

test('reconcile: CE batch failure records an error but keeps going', async () => {
  const members = [{
    id: 'mem-x',
    organization_id: 'org-1',
    user_id: 'user_x',
    external_student_id: 'stu-x',
    external_source: 'chess_empire',
    link_status: 'verified',
    organizations: { id: 'org-1', clerk_org_id: 'clerk-org-1' },
  }];
  const updates = [];
  const supabase = makeSupabase(members, updates);
  const ce = makeCe({}, { throwOn: 'CE 502: unreachable' });
  const clerk = makeClerk();
  const result = await reconcile({ supabase, ce, clerk });

  assert.equal(result.errors.length, 1);
  // No profile returned → treated as missing, no mutation.
  assert.equal(updates.length, 0);
});

// ── summary + writer ─────────────────────────────────────────────────────

test('buildSummaryMd emits counts + install-cron footer', () => {
  const result = {
    scanned: 3, fetched: 3, dryRun: false, durationSec: 1.23,
    counts: { none: 1, thaw: 1, freeze: 1, revoke: 0, missing: 0 },
    warnings: [], errors: [],
    details: [
      { memberId: 'm1', externalStudentId: 's1', before: 'frozen', after: 'verified', action: 'thaw', note: 'ok' },
      { memberId: 'm2', externalStudentId: 's2', before: 'verified', after: 'frozen', action: 'freeze', note: 'ok' },
    ],
  };
  const md = buildSummaryMd(result, '2026-07-01');
  assert.ok(md.includes('# Chess Empire lifecycle sync — 2026-07-01'));
  assert.ok(md.includes('verified→frozen: 1'));
  assert.ok(md.includes('frozen→verified: 1'));
  assert.ok(md.includes('anything→revoked: 0'));
  assert.ok(md.includes('Install cron:'));
  assert.ok(md.includes('| m1 | s1 | frozen | verified |'));
});

test('writeSummary drops the file at notes/cron/…', async () => {
  const tmp = await mkdtemp(path.join(os.tmpdir(), 'ce-sync-'));
  try {
    const result = {
      scanned: 0, fetched: 0, dryRun: true, durationSec: 0.01,
      counts: { none: 0, thaw: 0, freeze: 0, revoke: 0, missing: 0 },
      warnings: [], errors: [], details: [],
    };
    const outPath = await writeSummary(result, '2026-07-01', tmp);
    const contents = await readFile(outPath, 'utf8');
    assert.ok(contents.includes('2026-07-01'));
    assert.equal(path.basename(outPath), 'chess-empire-sync-2026-07-01.md');
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
});
